"""The embedding service.

Turns `SearchDocument`s into `EmbeddingRecord`s, and — the part that matters
operationally — **does not recompute what has not changed**. Every document
carries a content hash covering exactly the text and metadata that affect its
vector; a document whose hash matches the stored one is skipped.

Failure handling mirrors the ingestion pipeline: a provider error fails the
batch it occurred in and is recorded, rather than aborting the run. A dimension
mismatch is the exception — it is fatal, because mixing vector sizes in one
store silently corrupts every later similarity computation.
"""

import logging
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts._time import utc_now

from ..indexing.documents import SearchDocument
from .provider import (
    DimensionMismatchError,
    EmbeddingProvider,
    EmbeddingProviderError,
    HashedLexicalProvider,
)
from .vectors import (
    EmbeddingRecord,
    TrustLevel,
    VectorMetadata,
    content_hash,
    trust_for_source_type,
)

__all__ = ["EmbeddingBatchResult", "EmbeddingService", "chunk_text"]

logger = logging.getLogger("search.embeddings")

#: Characters per chunk. Long documents are split so a retrieved passage is
#: specific enough to cite, rather than "somewhere in this 20-page report".
DEFAULT_CHUNK_SIZE = 1200
DEFAULT_CHUNK_OVERLAP = 150


def chunk_text(
    text: str,
    size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Split text into overlapping chunks, preferring paragraph boundaries.

    Overlap exists so a sentence spanning a boundary is still retrievable
    whole from at least one chunk.
    """
    body = (text or "").strip()
    if not body:
        return []
    if len(body) <= size:
        return [body]
    if overlap >= size:
        raise ValueError("overlap must be smaller than the chunk size")

    chunks: List[str] = []
    start = 0
    while start < len(body):
        end = min(len(body), start + size)
        if end < len(body):
            #: Prefer to break at a paragraph, then a sentence, then anywhere.
            for separator in ("\n\n", ". ", "\n", " "):
                cut = body.rfind(separator, start + size // 2, end)
                if cut != -1:
                    end = cut + len(separator)
                    break
        chunk = body[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(body):
            break
        start = max(start + 1, end - overlap)
    return chunks


class EmbeddingBatchResult(BaseModel):
    """What one embedding run did."""

    model_config = ConfigDict(extra="forbid")

    created: int = 0
    updated: int = 0
    #: Documents whose content hash was unchanged, so nothing was recomputed.
    skipped: int = 0
    failed: int = 0
    #: Vectors produced by this run.
    records: List[EmbeddingRecord] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    #: Documents the provider was actually asked about.
    embedded_documents: int = 0

    @property
    def total(self) -> int:
        return self.created + self.updated + self.skipped + self.failed

    def summary(self) -> str:
        return (
            "embeddings: {0} created, {1} updated, {2} unchanged, {3} failed "
            "({4} vector(s))".format(
                self.created, self.updated, self.skipped, self.failed,
                len(self.records),
            )
        )


class EmbeddingService:
    """Embeds documents, skipping the ones that have not changed."""

    def __init__(
        self,
        provider: Optional[EmbeddingProvider] = None,
        batch_size: int = 32,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ):
        self.provider = provider or HashedLexicalProvider()
        self.batch_size = max(1, int(batch_size))
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        #: canonical_id -> content hash of the last successful embedding.
        self._hashes: Dict[str, str] = {}

    # -- change detection --------------------------------------------------
    def content_hash_for(self, document: SearchDocument) -> str:
        """Hash of exactly the content that determines this document's vectors."""
        return content_hash(
            document.title,
            document.text(),
            document.topics,
            document.aliases,
            #: The model is part of the identity: changing models must
            #: invalidate every vector, not silently mix old and new.
            self.provider.model_id,
            self.provider.dimensions,
        )

    def is_unchanged(self, document: SearchDocument) -> bool:
        known = self._hashes.get(document.id)
        return known is not None and known == self.content_hash_for(document)

    def forget(self, canonical_id: str) -> None:
        """Drop a remembered hash, forcing the next pass to re-embed."""
        self._hashes.pop(canonical_id, None)

    @property
    def known_documents(self) -> int:
        return len(self._hashes)

    # -- embedding ---------------------------------------------------------
    def embed_documents(
        self,
        documents: Iterable[SearchDocument],
        force: bool = False,
    ) -> EmbeddingBatchResult:
        """Embed documents, skipping unchanged ones unless `force` is set."""
        result = EmbeddingBatchResult()

        pending: List[SearchDocument] = []
        for document in documents:
            if not force and self.is_unchanged(document):
                result.skipped += 1
                continue
            pending.append(document)

        for start in range(0, len(pending), self.batch_size):
            batch = pending[start:start + self.batch_size]
            self._embed_batch(batch, result)

        return result

    def _embed_batch(
        self, batch: Sequence[SearchDocument], result: EmbeddingBatchResult
    ) -> None:
        #: Expand documents into chunks first, so one provider call covers the
        #: whole batch rather than one call per document.
        chunked: List[Any] = []
        for document in batch:
            text = document.text()
            chunks = chunk_text(text, self.chunk_size, self.chunk_overlap) or [
                document.title
            ]
            for index, chunk in enumerate(chunks):
                chunked.append((document, index, len(chunks), chunk))

        if not chunked:
            return

        texts = [item[3] for item in chunked]
        try:
            vectors = self.provider.embed(texts)
            self.provider.validate_batch(vectors, len(texts))
        except DimensionMismatchError:
            #: Fatal on purpose. A store containing two vector sizes produces
            #: wrong answers rather than obvious errors.
            raise
        except EmbeddingProviderError as exc:
            result.failed += len(batch)
            result.errors.append("{0}: {1}".format(exc.__class__.__name__, exc))
            logger.warning("embedding batch failed: %s", exc)
            return
        except Exception as exc:  # noqa: BLE001 - one batch must not kill a run
            result.failed += len(batch)
            result.errors.append(
                "unexpected {0}: {1}".format(exc.__class__.__name__, exc)
            )
            logger.exception("embedding batch raised unexpectedly")
            return

        seen_documents = set()
        for (document, index, count, chunk), vector in zip(chunked, vectors):
            record = self._build_record(document, index, count, chunk, vector)
            result.records.append(record)
            if document.id not in seen_documents:
                seen_documents.add(document.id)
                if document.id in self._hashes:
                    result.updated += 1
                else:
                    result.created += 1
                result.embedded_documents += 1

        for document in batch:
            if document.id in seen_documents:
                self._hashes[document.id] = self.content_hash_for(document)

    def _build_record(
        self, document: SearchDocument, index: int, count: int, chunk: str, vector
    ) -> EmbeddingRecord:
        metadata = VectorMetadata(
            canonical_id=document.id,
            entity_type=document.entity_type,
            title=document.title,
            snippet=chunk[:400],
            source_names=list(document.source_names),
            source_types=list(document.source_types),
            trust_level=trust_for_source_type(document.source_types),
            mission_ids=list(document.mission_ids),
            topics=list(document.topics),
            object_type=document.object_type,
            timestamp=document.date,
            freshness_class=document.freshness_class,
            indexed_at=utc_now(),
            model_id=self.provider.model_id,
            dimensions=self.provider.dimensions,
            content_hash=self.content_hash_for(document),
            chunk_index=index,
            chunk_count=count,
        )
        return EmbeddingRecord(
            id="{0}#{1}".format(document.id, index),
            vector=list(vector),
            metadata=metadata,
        )

    def embed_query(self, text: str) -> List[float]:
        """Embed a search query. Never chunked, never cached."""
        vectors = self.provider.embed([text or ""])
        self.provider.validate_batch(vectors, 1)
        return list(vectors[0])
