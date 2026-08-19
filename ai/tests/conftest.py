"""Shared fixtures: a real retrieval stack behind a scriptable AI provider."""

import sys
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from search.embeddings import EmbeddingService, HashedLexicalProvider
from search.indexing import extract_document
from search.keyword import KeywordIndex
from search.ranking import HybridSearch
from search.retrieval import SemanticSearch
from search.tests.conftest import build_corpus
from search.vector_store import InMemoryVectorStore


@pytest.fixture(scope="session")
def corpus():
    return build_corpus()


@pytest.fixture(scope="session")
def keyword(corpus):
    index = KeywordIndex()
    index.add_records(corpus)
    return index


@pytest.fixture(scope="session")
def embeddings():
    return EmbeddingService(HashedLexicalProvider())


@pytest.fixture(scope="session")
def retriever(corpus, keyword, embeddings):
    """The production retrieval stack: hybrid search with reranking."""
    store = InMemoryVectorStore()
    store.upsert(
        embeddings.embed_documents([extract_document(r) for r in corpus]).records
    )
    semantic = SemanticSearch(store, embeddings, keyword_index=keyword)
    return HybridSearch(keyword, semantic)
