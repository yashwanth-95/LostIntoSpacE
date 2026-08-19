"""Vector store: CRUD, metadata filtering, ranking quality and health."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.provenance import FreshnessClass
from contracts.search import SearchEntityType
from search.embeddings import (
    EmbeddingRecord,
    EmbeddingService,
    HashedLexicalProvider,
    TrustLevel,
    VectorMetadata,
)
from search.indexing import extract_document
from search.vector_store import (
    InMemoryVectorStore,
    VectorFilter,
    VectorMatch,
    VectorStore,
)

DIMENSIONS = 2048


@pytest.fixture(scope="module")
def service():
    return EmbeddingService(HashedLexicalProvider(dimensions=DIMENSIONS))


@pytest.fixture(scope="module")
def populated(corpus, service):
    store = InMemoryVectorStore()
    result = service.embed_documents([extract_document(r) for r in corpus])
    store.upsert(result.records)
    return store


def vector(seed: float = 0.0):
    """A unit vector pointing mostly along one axis."""
    values = [0.0] * DIMENSIONS
    values[int(seed) % DIMENSIONS] = 1.0
    return values


def record(vector_id="x:1#0", canonical_id="x:1", axis=0, **metadata_kwargs):
    payload = dict(
        canonical_id=canonical_id,
        title="Test record",
        dimensions=DIMENSIONS,
        model_id="hashed-lexical-v1",
    )
    payload.update(metadata_kwargs)
    return EmbeddingRecord(
        id=vector_id, vector=vector(axis), metadata=VectorMetadata(**payload)
    )


class TestCrud:
    def test_upsert_and_get(self):
        store = InMemoryVectorStore()
        assert store.upsert([record()]) == 1
        fetched = store.get("x:1#0")
        assert fetched is not None
        assert fetched.metadata.canonical_id == "x:1"

    def test_get_missing_returns_none(self):
        assert InMemoryVectorStore().get("nope") is None

    def test_upsert_replaces_rather_than_duplicates(self):
        store = InMemoryVectorStore()
        store.upsert([record(axis=1)])
        store.upsert([record(axis=2)])
        assert store.count() == 1
        assert store.get("x:1#0").vector == vector(2)

    def test_delete_by_id(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        assert store.delete(["x:1#0"]) == 1
        assert store.count() == 0

    def test_delete_missing_id_is_not_an_error(self):
        assert InMemoryVectorStore().delete(["nope"]) == 0

    def test_delete_all_chunks_of_a_record(self):
        store = InMemoryVectorStore()
        store.upsert([
            record("doc:1#0", "doc:1", axis=1),
            record("doc:1#1", "doc:1", axis=2),
            record("doc:2#0", "doc:2", axis=3),
        ])
        assert store.delete_by_canonical_id("doc:1") == 2
        assert store.count() == 1
        assert store.canonical_ids() == ["doc:2"]

    def test_get_by_canonical_id(self):
        store = InMemoryVectorStore()
        store.upsert([record("doc:1#0", "doc:1"), record("doc:1#1", "doc:1", axis=2)])
        assert len(store.get_by_canonical_id("doc:1")) == 2

    def test_len(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        assert len(store) == 1

    def test_clear(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        store.clear()
        assert store.count() == 0

    def test_implements_the_interface(self):
        assert isinstance(InMemoryVectorStore(), VectorStore)


class TestSearch:
    def test_identical_vector_scores_one(self):
        store = InMemoryVectorStore()
        store.upsert([record(axis=3)])
        matches = store.search(vector(3), top_k=1)
        assert matches[0].similarity == pytest.approx(1.0)

    def test_orthogonal_vector_scores_zero(self):
        store = InMemoryVectorStore()
        store.upsert([record(axis=3)])
        matches = store.search(vector(7), top_k=1, min_similarity=-1.0)
        assert matches[0].similarity == pytest.approx(0.0)

    def test_results_are_ordered_by_similarity(self, populated, service):
        query = service.embed_query("what causes maximum dynamic pressure")
        matches = populated.search(query, top_k=5)
        similarities = [match.similarity for match in matches]
        assert similarities == sorted(similarities, reverse=True)

    def test_top_k_is_respected(self, populated, service):
        query = service.embed_query("Mars rover")
        assert len(populated.search(query, top_k=3)) == 3

    def test_min_similarity_filters_weak_matches(self, populated, service):
        query = service.embed_query("Mars rover")
        strict = populated.search(query, top_k=20, min_similarity=0.9)
        loose = populated.search(query, top_k=20, min_similarity=0.0)
        assert len(strict) <= len(loose)

    def test_empty_store_returns_nothing(self, service):
        assert InMemoryVectorStore().search(service.embed_query("anything")) == []

    def test_invalid_top_k_rejected(self, populated, service):
        with pytest.raises(ValueError, match="top_k must be at least 1"):
            populated.search(service.embed_query("x"), top_k=0)

    def test_dimension_mismatch_is_detected(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        with pytest.raises(ValueError, match="more than one model"):
            store.search([0.1, 0.2, 0.3])

    def test_match_exposes_everything_needed_to_cite(self, populated, service):
        query = service.embed_query("what causes Max-Q")
        match = populated.search(query, top_k=1)[0]
        assert match.id
        assert match.canonical_id
        assert 0.0 <= match.similarity <= 1.0
        assert match.metadata.source_names
        assert match.trust_level
        assert match.snippet
        assert "via" in match.describe()


class TestFiltering:
    def test_filter_by_entity_type(self, populated, service):
        query = service.embed_query("Mars")
        matches = populated.search(
            query, top_k=20,
            filters=VectorFilter(entity_types=[SearchEntityType.MISSION]),
        )
        assert matches
        assert all(
            match.metadata.entity_type is SearchEntityType.MISSION
            for match in matches
        )

    def test_filter_by_source(self, populated, service):
        query = service.embed_query("Ceres asteroid")
        matches = populated.search(
            query, top_k=20, filters=VectorFilter(sources=["jpl_sbdb"])
        )
        assert matches
        assert all("jpl_sbdb" in match.source_names for match in matches)

    def test_filter_by_source_type(self, populated, service):
        query = service.embed_query("space station")
        matches = populated.search(
            query, top_k=20,
            filters=VectorFilter(source_types=["SECONDARY_OPERATIONAL"]),
        )
        assert matches
        for match in matches:
            assert "SECONDARY_OPERATIONAL" in match.metadata.source_types

    def test_filter_by_object_type(self, populated, service):
        query = service.embed_query("asteroid")
        matches = populated.search(
            query, top_k=20, filters=VectorFilter(object_types=["ASTEROID"])
        )
        assert matches
        assert all(match.metadata.object_type == "ASTEROID" for match in matches)

    def test_filter_by_mission(self, populated, service):
        query = service.embed_query("lunar landing")
        matches = populated.search(
            query, top_k=20, filters=VectorFilter(missions=["mission:apollo-11"])
        )
        assert matches
        assert all(
            "mission:apollo-11" in match.metadata.mission_ids for match in matches
        )

    def test_filter_by_topic(self, populated, service):
        query = service.embed_query("engines")
        matches = populated.search(
            query, top_k=20, filters=VectorFilter(topics=["propulsion"])
        )
        assert matches
        for match in matches:
            assert any(
                topic.lower() == "propulsion" for topic in match.metadata.topics
            )

    def test_filter_by_date_range(self, populated, service):
        query = service.embed_query("mission")
        matches = populated.search(
            query, top_k=50,
            filters=VectorFilter(
                start_date=datetime(1960, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(1975, 1, 1, tzinfo=timezone.utc),
            ),
        )
        assert matches
        for match in matches:
            assert match.metadata.timestamp is not None
            assert 1960 <= match.metadata.timestamp.year <= 1975

    def test_filter_by_trust_level(self, populated, service):
        query = service.embed_query("orbital elements")
        matches = populated.search(
            query, top_k=50, filters=VectorFilter(min_trust=TrustLevel.AUTHORITATIVE)
        )
        assert matches
        assert all(
            match.trust_level is TrustLevel.AUTHORITATIVE for match in matches
        )

    def test_filter_by_canonical_ids(self, populated, service):
        query = service.embed_query("anything")
        matches = populated.search(
            query, top_k=10, min_similarity=-1.0,
            filters=VectorFilter(canonical_ids=["concept:max-q"]),
        )
        assert matches
        assert all(match.canonical_id == "concept:max-q" for match in matches)

    def test_filters_combine_with_and(self, populated, service):
        query = service.embed_query("rocket")
        matches = populated.search(
            query, top_k=20,
            filters=VectorFilter(
                entity_types=[SearchEntityType.CONCEPT], topics=["propulsion"]
            ),
        )
        for match in matches:
            assert match.metadata.entity_type is SearchEntityType.CONCEPT
            assert any(t.lower() == "propulsion" for t in match.metadata.topics)

    def test_filter_applied_before_ranking(self, populated, service):
        """top_k must mean 'k allowed matches', not 'k candidates then filter'."""
        query = service.embed_query("Mars")
        filters = VectorFilter(entity_types=[SearchEntityType.CONCEPT])
        matches = populated.search(query, top_k=5, filters=filters)
        assert len(matches) == 5
        assert all(
            match.metadata.entity_type is SearchEntityType.CONCEPT
            for match in matches
        )

    def test_impossible_filter_returns_nothing(self, populated, service):
        matches = populated.search(
            service.embed_query("x"), filters=VectorFilter(sources=["no_such_source"])
        )
        assert matches == []

    def test_empty_filter_is_a_no_op(self, populated, service):
        query = service.embed_query("Mars")
        assert VectorFilter().is_empty
        assert populated.search(query, top_k=5) == populated.search(
            query, top_k=5, filters=VectorFilter()
        )

    def test_reversed_date_window_rejected(self):
        with pytest.raises(ValidationError, match="after end_date"):
            VectorFilter(
                start_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
                end_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )

    def test_exclude_historical(self):
        store = InMemoryVectorStore()
        store.upsert([
            record("a#0", "a", axis=1, freshness_class=FreshnessClass.RECENT),
            record("b#0", "b", axis=1, freshness_class=FreshnessClass.HISTORICAL),
        ])
        matches = store.search(
            vector(1), top_k=10, filters=VectorFilter(exclude_historical=True)
        )
        assert [match.canonical_id for match in matches] == ["a"]


class TestRetrievalQuality:
    """The store must actually find the right thing, not merely run."""

    def _top_id(self, populated, service, text):
        query = service.embed_query(text)
        matches = populated.search(query, top_k=1)
        return matches[0].canonical_id if matches else None

    def test_max_q_question(self, populated, service):
        assert self._top_id(populated, service, "What causes Max-Q?") == "concept:max-q"

    def test_staging_question(self, populated, service):
        assert self._top_id(
            populated, service, "How does staging improve rocket performance?"
        ) == "concept:staging"

    def test_orbital_decay_question(self, populated, service):
        assert self._top_id(
            populated, service, "What causes orbital decay?"
        ) == "concept:orbital-decay"

    def test_gravity_assist_question(self, populated, service):
        """Several records are legitimately relevant here.

        The concept explains the manoeuvre; Cassini and Voyager 2 are the
        canonical examples and their descriptions say so. Insisting on one
        "correct" answer would be a labelling opinion, not a quality bar, so
        the assertion is that a relevant record is retrieved.
        """
        query = service.embed_query("How does a gravity assist work?")
        ids = [match.canonical_id for match in populated.search(query, top_k=3)]
        assert ids
        assert set(ids) & {
            "concept:gravity-assist", "mission:cassini", "mission:voyager-2",
        }

    def test_jupiter_spacecraft_question(self, populated, service):
        query = service.embed_query("Which spacecraft explored Jupiter?")
        ids = {match.canonical_id for match in populated.search(query, top_k=5)}
        assert ids & {"mission:galileo", "mission:juno", "mission:voyager-2"}


class TestHealth:
    def test_healthy_store(self, populated):
        health = populated.health_check()
        assert health.healthy is True
        assert health.backend == "in-memory"
        assert health.vector_count > 0
        assert health.dimensions == DIMENSIONS

    def test_empty_store_is_healthy(self):
        health = InMemoryVectorStore().health_check()
        assert health.healthy is True
        assert health.vector_count == 0

    def test_mixed_dimensions_are_reported_as_unhealthy(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        store.upsert([
            EmbeddingRecord(
                id="y:1#0",
                vector=[0.0] * 8,
                metadata=VectorMetadata(canonical_id="y:1", dimensions=8,
                                        model_id="hashed-lexical-v1"),
            )
        ])
        health = store.health_check()
        assert health.healthy is False
        assert "different sizes" in health.detail

    def test_mixed_models_are_reported(self):
        store = InMemoryVectorStore()
        store.upsert([record()])
        store.upsert([
            EmbeddingRecord(
                id="y:1#0",
                vector=vector(5),
                metadata=VectorMetadata(canonical_id="y:1", dimensions=DIMENSIONS,
                                        model_id="some-other-model"),
            )
        ])
        health = store.health_check()
        assert health.healthy is False
        assert health.mixed_models == ["hashed-lexical-v1", "some-other-model"]


class TestNoSecondDatabase:
    def test_store_is_swappable_behind_the_interface(self):
        """Retrieval depends on the interface, never on the backend."""
        assert hasattr(VectorStore, "upsert")
        assert hasattr(VectorStore, "search")
        assert hasattr(VectorStore, "health_check")
        for method in ("upsert", "delete", "get", "search", "health_check"):
            assert getattr(VectorStore, method).__isabstractmethod__

    def test_backend_is_named_so_deployments_can_be_audited(self, populated):
        assert populated.health_check().backend == "in-memory"


class TestLargeStore:
    def test_numpy_path_agrees_with_the_python_path(self, service):
        """The batched path must return exactly what the plain path returns.

        Above the batching threshold the store computes similarities through
        NumPy. That is an optimisation, so it has to be answer-preserving.
        """
        records = [
            record("d{0}#0".format(index), "d{0}".format(index), axis=index)
            #: Fewer records than dimensions, so every axis is distinct and the
            #: expected answer is unambiguous.
            for index in range(300)
        ]
        assert len(records) < DIMENSIONS

        batched_store = InMemoryVectorStore()
        batched_store.upsert(records)
        assert batched_store.count() == 300

        query = vector(17)
        batched = batched_store.search(query, top_k=3)
        assert batched[0].canonical_id == "d17"
        assert batched[0].similarity == pytest.approx(1.0)

        #: The same query below the threshold takes the plain-Python path.
        small_store = InMemoryVectorStore()
        small_store.upsert(records[:20])
        plain = small_store.search(query, top_k=3)
        assert plain[0].canonical_id == "d17"
        assert plain[0].similarity == pytest.approx(1.0)
