"""Semantic search.

    Question -> Embedding -> Vector retrieval -> Filtering -> Ranking

Two behaviours are load-bearing:

**Chunk results collapse to record results.** The store holds one vector per
chunk; a user wants one hit per record. Each record scores as its best chunk,
and that chunk's snippet is what gets shown and cited.

**Weak evidence is reported, not dressed up.** When nothing clears the
confidence threshold the response is `NO_RELIABLE_MATCH` with an explanation and
*no results*. Returning the least-bad vector would hand the AI layer something
to explain that the corpus does not actually support, which is the failure mode
this whole design exists to prevent.

Hybrid ranking is available and on by default when a keyword index is supplied.
Lexical and vector retrieval fail differently — the first misses paraphrases,
the second misses exact identifiers — so fusing them is more robust than either.
"""

import time
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

from contracts.search import (
    MatchType,
    SearchEntityType,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchStatus,
)

from ..embeddings.service import EmbeddingService
from ..embeddings.vectors import TrustLevel
from ..indexing.documents import SearchDocument
from ..vector_store.base import VectorFilter, VectorMatch, VectorStore

__all__ = ["SemanticSearch", "RetrievalCandidate", "RRF_K"]

#: Reciprocal-rank-fusion constant. 60 is the value from the original RRF work
#: and is not sensitive: it flattens the difference between ranks 1 and 2 just
#: enough that one ranker cannot dominate on a single confident guess.
RRF_K = 60.0


class RetrievalCandidate(BaseModel):
    """One record surviving retrieval, before it becomes a `SearchResult`."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    #: Best cosine similarity across the record's chunks.
    similarity: float
    #: Fused rank score when hybrid ranking ran, otherwise the similarity.
    score: float
    #: The chunk that matched best — what gets quoted and cited.
    best_chunk_id: Optional[str] = None
    snippet: Optional[str] = None
    trust_level: TrustLevel = TrustLevel.LOW
    #: Which retrievers found it, for explainability.
    found_by: List[str] = Field(default_factory=list)
    vector_rank: Optional[int] = None
    keyword_rank: Optional[int] = None


class SemanticSearch:
    """Question-answering retrieval over the vector store."""

    def __init__(
        self,
        store: VectorStore,
        embeddings: EmbeddingService,
        documents: Optional[Any] = None,
        keyword_index: Optional[Any] = None,
        min_similarity: float = 0.10,
        confident_similarity: float = 0.18,
        margin: float = 0.0,
        candidate_multiplier: int = 4,
    ):
        """
        `documents` is anything with `.get(id) -> SearchDocument`; the keyword
        index satisfies it. It supplies the provenance a result must carry —
        without it, scientific results cannot be constructed at all, which is
        the correct outcome rather than an inconvenience.

        `min_similarity` is the confidence floor below which a match is not
        treated as evidence. The default is calibrated against the evaluation
        set in `search/evaluation`; see its report for the separation between
        answerable and unanswerable queries.
        """
        self.store = store
        self.embeddings = embeddings
        self.keyword_index = keyword_index
        self.documents = documents if documents is not None else keyword_index
        self.min_similarity = min_similarity
        #: Above this, a match is strong enough to answer on even when the
        #: question names something the corpus does not contain — the evidence
        #: speaks for itself.
        self.confident_similarity = confident_similarity
        self.margin = margin
        self.candidate_multiplier = max(1, candidate_multiplier)

    def _unknown_subjects(self, query_text: str) -> List[str]:
        """Named subjects in the query that the index has never seen."""
        if not query_text or self.keyword_index is None:
            return []
        finder = getattr(self.keyword_index, "unknown_proper_nouns", None)
        return finder(query_text) if finder else []

    # -- filtering ---------------------------------------------------------
    def _filter_from_query(self, query: SearchQuery) -> VectorFilter:
        """Translate the shared `SearchQuery` filters into a vector filter."""
        return VectorFilter(
            entity_types=list(query.entity_types),
            object_types=list(query.object_types),
            sources=list(query.sources),
            source_types=[item.value for item in query.source_types],
            missions=list(query.missions),
            topics=list(query.topics),
            start_date=query.start_date,
            end_date=query.end_date,
        )

    # -- retrieval ---------------------------------------------------------
    def retrieve(
        self, query: SearchQuery, top_k: Optional[int] = None
    ) -> List[RetrievalCandidate]:
        """Run the pipeline and return ranked candidates."""
        limit = top_k or query.limit
        #: Over-fetch: several chunks of one record can occupy the top slots,
        #: so asking for exactly `limit` vectors would under-fill the page.
        fetch = max(limit * self.candidate_multiplier, limit + 5)

        vector = self.embeddings.embed_query(query.text)
        matches = self.store.search(
            vector,
            top_k=fetch,
            filters=self._filter_from_query(query),
            #: Retrieve below the confidence floor so the caller can see how
            #: weak the best evidence was, then decide.
            min_similarity=-1.0,
        )

        by_record = self._collapse_chunks(matches)
        if self.keyword_index is not None:
            self._fuse_keyword_ranks(query, by_record, fetch)

        candidates = sorted(
            by_record.values(), key=lambda item: (-item.score, item.canonical_id)
        )
        return candidates[:limit]

    def _collapse_chunks(
        self, matches: Sequence[VectorMatch]
    ) -> Dict[str, RetrievalCandidate]:
        """One candidate per record, scored by its best chunk."""
        by_record: Dict[str, RetrievalCandidate] = {}
        for rank, match in enumerate(matches, start=1):
            existing = by_record.get(match.canonical_id)
            if existing is not None and existing.similarity >= match.similarity:
                continue
            by_record[match.canonical_id] = RetrievalCandidate(
                canonical_id=match.canonical_id,
                similarity=match.similarity,
                score=match.similarity,
                best_chunk_id=match.id,
                snippet=match.snippet,
                trust_level=match.trust_level,
                found_by=["vector"],
                vector_rank=rank,
            )
        return by_record

    def _fuse_keyword_ranks(
        self, query: SearchQuery, by_record: Dict[str, RetrievalCandidate], fetch: int
    ) -> None:
        """Blend lexical ranks into the vector ranking using RRF.

        Reciprocal rank fusion combines *ranks* rather than scores, which is
        what makes it safe here: the keyword index's scores and cosine
        similarities are on different scales and would not be comparable if
        added directly.
        """
        lexical = self.keyword_index.search(
            query.model_copy(update={"limit": fetch, "offset": 0, "min_score": 0.0})
        )
        keyword_ranks = {
            result.id: rank for rank, result in enumerate(lexical.results, start=1)
        }

        for canonical_id, candidate in by_record.items():
            fused = 0.0
            if candidate.vector_rank:
                fused += 1.0 / (RRF_K + candidate.vector_rank)
            rank = keyword_ranks.get(canonical_id)
            if rank:
                fused += 1.0 / (RRF_K + rank)
                candidate.keyword_rank = rank
                if "keyword" not in candidate.found_by:
                    candidate.found_by.append("keyword")
            candidate.score = fused

        #: Records the lexical ranker found but the vector ranker did not are
        #: still real matches — an exact identifier, typically. They enter with
        #: their similarity unknown rather than assumed.
        for canonical_id, rank in keyword_ranks.items():
            if canonical_id in by_record:
                continue
            document = self._document(canonical_id)
            by_record[canonical_id] = RetrievalCandidate(
                canonical_id=canonical_id,
                similarity=0.0,
                score=1.0 / (RRF_K + rank),
                snippet=document.summary if document else None,
                found_by=["keyword"],
                keyword_rank=rank,
            )

    def _document(self, canonical_id: str) -> Optional[SearchDocument]:
        if self.documents is None:
            return None
        getter = getattr(self.documents, "get", None)
        return getter(canonical_id) if getter else None

    # -- confidence --------------------------------------------------------
    def assess_confidence(
        self,
        candidates: Sequence[RetrievalCandidate],
        query_text: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """Decide whether the evidence supports answering at all.

        Returns `(is_reliable, explanation)`. A candidate found only by exact
        lexical match counts as evidence even at zero similarity — a user who
        pasted a catalogue number has given unambiguous intent.
        """
        if not candidates:
            return (False, "no record matched this question")

        best = candidates[0]

        #: A named subject the corpus has never heard of. Checked before the
        #: similarity floor, because this is exactly the case similarity gets
        #: wrong: a question about an absent mission still overlaps strongly
        #: with every present mission on its generic words.
        unknown = self._unknown_subjects(query_text)
        if unknown and best.similarity < self.confident_similarity:
            return (
                False,
                "the question refers to {0}, which does not appear anywhere in "
                "the indexed corpus; the nearby records are about related "
                "subjects, not this one".format(
                    ", ".join(repr(term) for term in unknown)
                ),
            )

        if "keyword" in best.found_by and best.keyword_rank == 1:
            return (True, None)

        if best.similarity < self.min_similarity:
            return (
                False,
                "the closest record scored {0:.3f}, below the confidence "
                "threshold of {1:.2f}; the indexed corpus does not appear to "
                "cover this question".format(best.similarity, self.min_similarity),
            )

        if self.margin > 0.0 and len(candidates) > 1:
            runner_up = candidates[1].similarity
            if best.similarity - runner_up < self.margin:
                return (
                    False,
                    "the top two matches are within {0:.3f} of each other, so no "
                    "single record is clearly the answer".format(
                        best.similarity - runner_up
                    ),
                )
        return (True, None)

    # -- public API --------------------------------------------------------
    def search(self, query: SearchQuery) -> SearchResponse:
        """Answer a question, or say why it cannot be answered."""
        started = time.time()
        candidates = self.retrieve(query, top_k=query.limit + query.offset)
        reliable, explanation = self.assess_confidence(candidates, query.text)

        if not reliable:
            return SearchResponse(
                query=query,
                status=SearchStatus.NO_RELIABLE_MATCH
                if candidates
                else SearchStatus.EMPTY,
                results=[],
                total=0,
                offset=query.offset,
                limit=query.limit,
                took_ms=(time.time() - started) * 1000.0,
                explanation=explanation,
            )

        above_floor = [
            candidate
            for candidate in candidates
            if candidate.similarity >= self.min_similarity
            or "keyword" in candidate.found_by
        ]
        page = above_floor[query.offset:query.offset + query.limit]

        results: List[SearchResult] = []
        for candidate in page:
            result = self._to_result(candidate)
            if result is not None:
                results.append(result)

        return SearchResponse(
            query=query,
            status=SearchStatus.OK if results else SearchStatus.NO_RELIABLE_MATCH,
            results=results,
            total=len(above_floor),
            offset=query.offset,
            limit=query.limit,
            took_ms=(time.time() - started) * 1000.0,
            explanation=None if results else "no result could be attributed",
        )

    def _to_result(self, candidate: RetrievalCandidate) -> Optional[SearchResult]:
        document = self._document(candidate.canonical_id)
        if document is None:
            #: Without the document there is no provenance, and an unattributed
            #: scientific result must not be shown. Dropping it is correct.
            return None
        return SearchResult(
            id=document.id,
            entity_type=document.entity_type,
            title=document.title,
            summary=candidate.snippet or document.summary,
            #: Similarity is the interpretable number; the fused rank score is
            #: an internal ordering device and would confuse a caller.
            score=max(0.0, min(1.0, candidate.similarity)),
            match_type=MatchType.SEMANTIC,
            matched_fields=list(candidate.found_by),
            provenance=document.provenance,
            object_type=document.object_type,
            topics=document.topics,
            mission_ids=document.mission_ids,
            date=document.date,
            url=document.url,
            metadata=dict(
                document.metadata,
                best_chunk=candidate.best_chunk_id,
                vector_rank=candidate.vector_rank,
                keyword_rank=candidate.keyword_rank,
                trust_level=candidate.trust_level.value,
            ),
        )
