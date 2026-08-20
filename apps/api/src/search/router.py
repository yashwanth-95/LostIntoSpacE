"""Platform search routes.

Public: search is how a visitor finds anything, and it must work before they
have an account.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import BaseModel

from src.core.engines import ensure_engine_paths
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse
from src.search.service import MAX_LIMIT, run_search

router = APIRouter()


def _search_envelope_model() -> Any:
    """Publish P4's own ``SearchResponse`` as the response model.

    As with the simulation endpoint, the engine's contract is reused rather
    than mirrored: OpenAPI then describes the real shape, provenance included,
    and the frontend's types can be generated from it.
    """
    try:
        ensure_engine_paths()
        from contracts.search import SearchResponse
    except ImportError:  # pragma: no cover - depends on the install
        return None

    class PlatformSearchResponse(BaseModel):
        """`{"status": "success", "data": <SearchResponse>}`."""

        status: str = "success"
        data: SearchResponse

    return PlatformSearchResponse


_SEARCH_RESPONSES: dict = {
    503: {"model": ErrorResponse, "description": "The search engine is unavailable"},
}


@router.get(
    "",
    response_model=_search_envelope_model(),
    responses=_SEARCH_RESPONSES,
    tags=["search"],
)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=300, description="The query")],
    entity_type: Annotated[
        list[str] | None, Query(description="Restrict to these entity kinds")
    ] = None,
    topic: Annotated[list[str] | None, Query(description="Restrict to these topics")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0, le=1000)] = 0,
) -> dict:
    """Search missions, learning concepts, and catalogued objects at once.

    Hybrid retrieval: a keyword index and a vector index are queried
    independently, fused, and reranked. Every result carries its source
    attribution, and the response includes the engine's own explanation of how
    the query was interpreted.
    """
    return success_envelope(
        run_search(
            text=q,
            entity_types=entity_type,
            topics=topic,
            limit=limit,
            offset=offset,
        )
    )
