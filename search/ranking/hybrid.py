"""Hybrid search.

    Candidate fusion -> Score normalization -> Reranking -> Final results

Runs the lexical and semantic retrievers independently, fuses their *ranks*,
normalizes the fused scores, reranks a small top slice with metadata and source
quality, and returns the page.

Why both retrievers: they fail differently. Lexical search misses paraphrases
("why do rockets throttle down" for Max-Q) and semantic search misses exact
identifiers ("25544"). Neither weakness overlaps, so fusing covers both.
"""

import time
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.search import (
    MatchType,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchStatus,
)

from ..indexing.documents import SearchDocument
from .fusion import (
    FusedCandidate,
    NormalizationMethod,
    RetrieverResult,
    normalize_scores,
    reciprocal_rank_fusion,
    weighted_score_fusion,
)
from .intent import IntentAssessment, QueryIntent, classify_intent
from .reranker import (
    DEFAULT_RERANK_TOP_N,
    HeuristicReranker,
    RerankCandidate,
    RerankedCandidate,
    Reranker,
)

__all__ = ["HybridSearch", "HybridTrace"]


class HybridTrace(BaseModel):
    """What each stage did. Returned alongside results for debugging.

    Kept because a hybrid pipeline is otherwise opaque: when a result ranks
    oddly, the only way to find out why is to see the candidate set at each
    stage.
    """

    model_config = ConfigDict(extra="forbid")

    intent: Optional[IntentAssessment] = None
    keyword_candidates: int = 0
    vector_candidates: int = 0
    fused_candidates: int = 0
    reranked_candidates: int = 0
    fusion_method: str = "rrf"
    reranker: str = "none"
    #: Ids that changed position during reranking, and by how much.
    rerank_movements: Dict[str, int] = Field(default_factory=dict)
    stage_ms: Dict[str, float] = Field(default_factory=dict)


class HybridSearch:
    """Lexical plus semantic retrieval, fused and reranked."""

    def __init__(
        self,
        keyword_index: Any,
        semantic: Any,
        reranker: Optional[Reranker] = None,
        rerank_top_n: int = DEFAULT_RERANK_TOP_N,
        keyword_weight: float = 1.0,
        vector_weight: float = 1.0,
        fusion_method: str = "rrf",
        normalization: NormalizationMethod = NormalizationMethod.MIN_MAX,
        min_similarity: float = 0.10,
    ):
        self.keyword_index = keyword_index
        self.semantic = semantic
        self.reranker = reranker if reranker is not None else HeuristicReranker()
        #: Reranking is the expensive stage; it sees a small slice only.
        self.rerank_top_n = max(1, rerank_top_n)
        self.keyword_weight = keyword_weight
        self.vector_weight = vector_weight
        self.fusion_method = fusion_method
        self.normalization = normalization
        self.min_similarity = min_similarity
        self._last_trace: Optional[HybridTrace] = None

    @property
    def last_trace(self) -> Optional[HybridTrace]:
        return self._last_trace

    # -- stages ------------------------------------------------------------
    def _retrieve(self, query: SearchQuery, fetch: int) -> List[RetrieverResult]:
        """Run both retrievers independently. Neither sees the other's output."""
        results: List[RetrieverResult] = []

        wide = query.model_copy(
            update={"limit": fetch, "offset": 0, "min_score": 0.0}
        )
        lexical = self.keyword_index.search(wide)
        results.append(
            RetrieverResult(
                retriever="keyword",
                ids=[item.id for item in lexical.results],
                scores=[item.score for item in lexical.results],
                weight=self.keyword_weight,
            )
        )

        candidates = self.semantic.retrieve(wide, top_k=fetch)
        results.append(
            RetrieverResult(
                retriever="vector",
                ids=[item.canonical_id for item in candidates],
                scores=[item.similarity for item in candidates],
                weight=self.vector_weight,
            )
        )
        self._vector_similarity = {
            item.canonical_id: item.similarity for item in candidates
        }
        self._vector_snippet = {
            item.canonical_id: item.snippet for item in candidates
        }
        return results

    def _fuse(self, results: Sequence[RetrieverResult]) -> List[FusedCandidate]:
        if self.fusion_method == "weighted":
            return weighted_score_fusion(results, self.normalization)
        return reciprocal_rank_fusion(results)

    def _to_rerank_candidates(
        self, fused: Sequence[FusedCandidate]
    ) -> List[RerankCandidate]:
        """Normalize fused scores to 0..1, then attach metadata.

        Normalization happens here, before reranking, so the reranker's
        `relevance` term is on the same scale as its other bounded signals.
        Feeding it a raw RRF score — which for two retrievers tops out around
        0.033 — would make relevance effectively weightless.
        """
        scores = normalize_scores(
            [item.fused_score for item in fused], NormalizationMethod.MIN_MAX
        )
        candidates: List[RerankCandidate] = []
        for item, relevance in zip(fused, scores):
            document = self._document(item.id)
            if document is None:
                continue
            candidates.append(
                RerankCandidate(
                    id=item.id,
                    title=document.title,
                    text=self._vector_snippet.get(item.id) or document.summary or "",
                    relevance=relevance,
                    entity_type=document.entity_type,
                    object_type=document.object_type,
                    trust_level=_trust_for(document),
                    source_names=list(document.source_names),
                    freshness_class=document.freshness_class,
                    date=document.date,
                    topics=list(document.topics),
                    is_stale=document.is_stale,
                    metadata={
                        "found_by": item.found_by,
                        "ranks": item.ranks,
                        "fused_score": item.fused_score,
                        "similarity": self._vector_similarity.get(item.id, 0.0),
                    },
                )
            )
        return candidates

    def _document(self, document_id: str) -> Optional[SearchDocument]:
        getter = getattr(self.keyword_index, "get", None)
        return getter(document_id) if getter else None

    # -- public API --------------------------------------------------------
    def search(self, query: SearchQuery) -> SearchResponse:
        """Run the full pipeline."""
        started = time.time()
        trace = HybridTrace(fusion_method=self.fusion_method, reranker=self.reranker.name)

        intent = classify_intent(query.text)
        trace.intent = intent

        #: Fetch wider than the page: fusion and reranking both need headroom,
        #: and a document ranked 20th by one retriever can rank 1st overall.
        fetch = max(self.rerank_top_n, (query.limit + query.offset) * 3, 30)

        mark = time.time()
        retriever_results = self._retrieve(query, fetch)
        trace.keyword_candidates = len(retriever_results[0].ids)
        trace.vector_candidates = len(retriever_results[1].ids)
        trace.stage_ms["retrieve"] = (time.time() - mark) * 1000.0

        mark = time.time()
        fused = self._fuse(retriever_results)
        trace.fused_candidates = len(fused)
        trace.stage_ms["fuse"] = (time.time() - mark) * 1000.0

        if not fused:
            self._last_trace = trace
            return SearchResponse(
                query=query,
                status=SearchStatus.EMPTY,
                results=[],
                total=0,
                offset=query.offset,
                limit=query.limit,
                took_ms=(time.time() - started) * 1000.0,
                explanation="no indexed record matched this query",
            )

        mark = time.time()
        #: Only the top slice is reranked. This is the cost control.
        head = self._to_rerank_candidates(fused[: self.rerank_top_n])
        reranked = self.reranker.rerank(
            query.text, head, top_k=query.limit + query.offset, intent=intent
        )
        trace.reranked_candidates = len(head)
        trace.rerank_movements = {
            item.id: item.moved for item in reranked if item.moved
        }
        trace.stage_ms["rerank"] = (time.time() - mark) * 1000.0

        confident, explanation = self._assess(query, intent, fused, reranked)
        if not confident:
            self._last_trace = trace
            return SearchResponse(
                query=query,
                status=SearchStatus.NO_RELIABLE_MATCH,
                results=[],
                total=0,
                offset=query.offset,
                limit=query.limit,
                took_ms=(time.time() - started) * 1000.0,
                explanation=explanation,
            )

        by_id = {candidate.id: candidate for candidate in head}
        page = reranked[query.offset:query.offset + query.limit]
        results = []
        for item in page:
            result = self._to_result(item, by_id.get(item.id))
            if result is not None:
                results.append(result)

        self._last_trace = trace
        return SearchResponse(
            query=query,
            status=SearchStatus.OK if results else SearchStatus.NO_RELIABLE_MATCH,
            results=results,
            total=len(reranked),
            offset=query.offset,
            limit=query.limit,
            took_ms=(time.time() - started) * 1000.0,
            explanation=None if results else "no result could be attributed",
        )

    def _assess(self, query, intent, fused, reranked):
        """Delegate the abstention decision to the semantic layer.

        The confidence rules — similarity floor, unknown named subjects — live
        there and are measured there. Duplicating them here would let the two
        paths disagree about what counts as evidence.
        """
        candidates = self.semantic.retrieve(
            query.model_copy(update={"limit": max(query.limit, 10)})
        )
        return self.semantic.assess_confidence(candidates, query.text)

    def _to_result(
        self, item: RerankedCandidate, candidate: Optional[RerankCandidate]
    ) -> Optional[SearchResult]:
        document = self._document(item.id)
        if document is None:
            #: No document means no provenance, and an unattributed scientific
            #: result must not be shown.
            return None
        similarity = 0.0
        found_by: List[str] = []
        if candidate is not None:
            similarity = float(candidate.metadata.get("similarity", 0.0))
            found_by = list(candidate.metadata.get("found_by", []))

        return SearchResult(
            id=document.id,
            entity_type=document.entity_type,
            title=document.title,
            summary=(candidate.text if candidate else None) or document.summary,
            #: The reported score is the reranker's, clamped — it is the number
            #: that actually determined this position.
            score=max(0.0, min(1.0, item.score / 2.0)),
            match_type=MatchType.SEMANTIC if "vector" in found_by else MatchType.PARTIAL,
            matched_fields=found_by,
            provenance=document.provenance,
            object_type=document.object_type,
            topics=document.topics,
            mission_ids=document.mission_ids,
            date=document.date,
            url=document.url,
            metadata=dict(
                document.metadata,
                similarity=similarity,
                found_by=found_by,
                rerank_score=item.score,
                rerank_components=item.components,
                rerank_explanation=item.explanation,
                moved=item.moved,
            ),
        )


def _trust_for(document: SearchDocument):
    from ..embeddings.vectors import trust_for_source_type

    return trust_for_source_type(document.source_types)
