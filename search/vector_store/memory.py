"""In-memory vector store.

The reference implementation of `VectorStore`. Exact nearest-neighbour search
by brute force, which is the right choice at this corpus size: it is exact, has
no index to rebuild, no tuning parameters, and no approximation error to
confuse a retrieval-quality measurement with.

It uses NumPy when the store is large enough for that to pay off, and plain
Python otherwise — for a few hundred vectors the array conversion costs more
than it saves.
"""

from typing import Dict, Iterable, List, Optional, Sequence

from ..embeddings.vectors import EmbeddingRecord
from .base import VectorFilter, VectorMatch, VectorStore, VectorStoreHealth

__all__ = ["InMemoryVectorStore"]

#: Above this many vectors, batch the similarity computation through NumPy.
_NUMPY_THRESHOLD = 256


class InMemoryVectorStore(VectorStore):
    """Exact brute-force vector store."""

    backend = "in-memory"

    def __init__(self):
        self._records: Dict[str, EmbeddingRecord] = {}
        #: canonical_id -> chunk ids, so a record's vectors can be replaced or
        #: deleted as a unit.
        self._by_canonical: Dict[str, List[str]] = {}
        self._matrix = None
        self._matrix_ids: List[str] = []
        self._dirty = True

    # -- writes ------------------------------------------------------------
    def upsert(self, records: Iterable[EmbeddingRecord]) -> int:
        written = 0
        for record in records:
            existing = self._records.get(record.id)
            if existing is not None:
                self._detach(existing)
            self._records[record.id] = record
            self._by_canonical.setdefault(record.metadata.canonical_id, [])
            if record.id not in self._by_canonical[record.metadata.canonical_id]:
                self._by_canonical[record.metadata.canonical_id].append(record.id)
            written += 1
        if written:
            self._dirty = True
        return written

    def delete(self, ids: Iterable[str]) -> int:
        removed = 0
        for vector_id in list(ids):
            record = self._records.pop(vector_id, None)
            if record is None:
                continue
            self._detach(record)
            removed += 1
        if removed:
            self._dirty = True
        return removed

    def delete_by_canonical_id(self, canonical_id: str) -> int:
        return self.delete(list(self._by_canonical.get(canonical_id, [])))

    def _detach(self, record: EmbeddingRecord) -> None:
        chunk_ids = self._by_canonical.get(record.metadata.canonical_id)
        if not chunk_ids:
            return
        if record.id in chunk_ids:
            chunk_ids.remove(record.id)
        if not chunk_ids:
            self._by_canonical.pop(record.metadata.canonical_id, None)

    def clear(self) -> None:
        self._records.clear()
        self._by_canonical.clear()
        self._dirty = True

    # -- reads -------------------------------------------------------------
    def get(self, vector_id: str) -> Optional[EmbeddingRecord]:
        return self._records.get(vector_id)

    def get_by_canonical_id(self, canonical_id: str) -> List[EmbeddingRecord]:
        return [
            self._records[chunk_id]
            for chunk_id in self._by_canonical.get(canonical_id, [])
            if chunk_id in self._records
        ]

    def count(self) -> int:
        return len(self._records)

    def canonical_ids(self) -> List[str]:
        return sorted(self._by_canonical)

    # -- search ------------------------------------------------------------
    def _rebuild(self) -> None:
        self._matrix_ids = list(self._records)
        self._matrix = None
        if len(self._matrix_ids) >= _NUMPY_THRESHOLD:
            try:
                import numpy

                self._matrix = numpy.array(
                    [self._records[key].vector for key in self._matrix_ids],
                    dtype="float64",
                )
            except Exception:  # pragma: no cover - numpy is optional here
                self._matrix = None
        self._dirty = False

    def search(
        self,
        vector: Sequence[float],
        top_k: int = 10,
        filters: Optional[VectorFilter] = None,
        min_similarity: float = 0.0,
    ) -> List[VectorMatch]:
        if top_k < 1:
            raise ValueError("top_k must be at least 1")
        if not self._records:
            return []
        query = list(float(component) for component in vector)

        #: Filter first: `top_k` should mean "the k best allowed matches", not
        #: "k candidates, some of which will be thrown away".
        if filters is not None and not filters.is_empty:
            candidates = [
                record
                for record in self._records.values()
                if filters.matches(record.metadata)
            ]
        else:
            candidates = list(self._records.values())

        if not candidates:
            return []

        expected = len(query)
        scored: List[VectorMatch] = []

        if self._dirty:
            self._rebuild()

        use_numpy = (
            self._matrix is not None
            and len(candidates) == len(self._matrix_ids)
            and expected == self._matrix.shape[1]
        )

        if use_numpy:
            import numpy

            similarities = self._matrix.dot(numpy.array(query, dtype="float64"))
            for index, key in enumerate(self._matrix_ids):
                similarity = float(similarities[index])
                if similarity < min_similarity:
                    continue
                scored.append(self._match(self._records[key], similarity))
        else:
            for record in candidates:
                if len(record.vector) != expected:
                    raise ValueError(
                        "stored vector {0} has {1} dimensions but the query has "
                        "{2}; the store holds vectors from more than one model".format(
                            record.id, len(record.vector), expected
                        )
                    )
                similarity = _dot(record.vector, query)
                if similarity < min_similarity:
                    continue
                scored.append(self._match(record, similarity))

        scored.sort(key=lambda match: (-match.similarity, match.id))
        return scored[:top_k]

    def _match(self, record: EmbeddingRecord, similarity: float) -> VectorMatch:
        return VectorMatch(
            id=record.id,
            canonical_id=record.metadata.canonical_id,
            similarity=round(similarity, 6),
            metadata=record.metadata,
        )

    # -- health ------------------------------------------------------------
    def health_check(self) -> VectorStoreHealth:
        models = sorted({
            record.metadata.model_id
            for record in self._records.values()
            if record.metadata.model_id
        })
        sizes = sorted({len(record.vector) for record in self._records.values()})

        healthy = len(models) <= 1 and len(sizes) <= 1
        detail = None
        if len(sizes) > 1:
            detail = (
                "store holds vectors of {0} different sizes ({1}); similarity "
                "results are not meaningful".format(len(sizes), sizes)
            )
        elif len(models) > 1:
            detail = (
                "store holds vectors from {0} different models ({1}); they are not "
                "comparable".format(len(models), models)
            )

        return VectorStoreHealth(
            healthy=healthy,
            backend=self.backend,
            vector_count=len(self._records),
            dimensions=sizes[0] if len(sizes) == 1 else None,
            mixed_models=models if len(models) > 1 else [],
            detail=detail or "ok",
        )


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    """Dot product. Vectors are L2-normalized, so this is cosine similarity."""
    return sum(x * y for x, y in zip(a, b))
