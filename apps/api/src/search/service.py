"""Platform-wide search.

Two search systems exist in this repository and they are not competitors:

- **This one** — P4's hybrid keyword + semantic engine over the bundled
  knowledge corpus (missions, learning concepts, catalogued objects). It is
  what the global search bar and the AI assistant's retrieval use, it ranks
  across entity types, and it carries provenance on every hit.
- **PostgreSQL full-text** on `/space-objects?q=` — a filter *within* one
  resource, backed by a generated `tsvector` column. It stays where it is.

The split is deliberate: cross-corpus ranked retrieval and "narrow this list"
are different problems, and collapsing them would make both worse. What the
audit warned against was two *incompatible* systems for the same job.

The corpus
----------
Built once per process from `data.seeds` — bundled, offline-safe records that
carry real source attribution. No network call is made to serve a search, so
the feature works during a demo with no connectivity, which is the same
property `data/offline/` exists to provide.

Embeddings are `HashedLexicalProvider`: deterministic, local, no API key. It is
a hashed lexical projection rather than a learned model, and the engine's own
documentation says so — the ranking is genuinely hybrid, but "semantic" here
means term-overlap in a projected space, not learned meaning.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from src.core.engines import EngineUnavailableError, ensure_engine_paths, get_search
from src.core.exceptions import AppError

logger = logging.getLogger("api.search")

#: Hard ceiling on results per request, independent of what the caller asks.
MAX_LIMIT = 50


@lru_cache(maxsize=1)
def _engine() -> Any:
    """Build the index once per process.

    Indexing the bundled corpus takes a moment and the corpus never changes at
    runtime, so it is cached. The cache is on this private function rather than
    the endpoint so tests can clear it.
    """
    ensure_engine_paths()
    search = get_search()

    from data.seeds import build_concepts, build_missions
    from search.embeddings.provider import HashedLexicalProvider
    from search.embeddings.service import EmbeddingService
    from search.indexing.documents import extract_document
    from search.retrieval.semantic import SemanticSearch
    from search.vector_store.memory import InMemoryVectorStore

    records = list(build_concepts()) + list(build_missions())

    index = search.KeywordIndex()
    index.add_records(records)

    embeddings = EmbeddingService(HashedLexicalProvider())
    store = InMemoryVectorStore()
    store.upsert(embeddings.embed_documents([extract_document(r) for r in records]).records)
    semantic = SemanticSearch(store, embeddings, keyword_index=index)

    logger.info("search index built: %d documents", len(index))
    return search.HybridSearch(index, semantic)


def search_available() -> bool:
    """Whether search can serve a request, without raising."""
    try:
        _engine()
    except Exception:  # noqa: BLE001 - availability probe must never raise
        return False
    return True


def run_search(
    *,
    text: str,
    entity_types: list[str] | None = None,
    topics: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
    include_facets: bool = True,
) -> dict[str, Any]:
    """
    Run one platform search.

    Args:
        text: The query. An empty query returns nothing rather than everything.
        entity_types: Restrict to these entity kinds.
        topics: Restrict to these topic tags.
        limit: Results to return, capped at ``MAX_LIMIT``.
        offset: Results to skip, for paging.
        include_facets: Ask the engine for facet counts.

    Returns:
        The engine's ``SearchResponse`` as a JSON-safe dict.

    Raises:
        AppError: 503 when the search engine is unavailable.
    """
    try:
        engine = _engine()
    except EngineUnavailableError as exc:
        raise AppError(
            503, "SEARCH_ENGINE_UNAVAILABLE", "Search is not available on this server"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - a corpus build failure is a 503, not a 500
        logger.exception("search index build failed")
        raise AppError(
            503, "SEARCH_ENGINE_UNAVAILABLE", "Search is not available on this server"
        ) from exc

    from contracts.search import SearchQuery

    query = SearchQuery(
        text=text,
        entity_types=entity_types or [],
        topics=topics or [],
        limit=min(limit, MAX_LIMIT),
        offset=offset,
        include_facets=include_facets,
    )
    return engine.search(query).model_dump(mode="json")
