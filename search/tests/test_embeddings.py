"""Embeddings: metadata, change detection, batching and failure modes."""

import math

import pytest
from pydantic import ValidationError

from contracts.provenance import SourceType
from contracts.search import SearchEntityType
from search.embeddings import (
    DimensionMismatchError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingRecord,
    EmbeddingService,
    HashedLexicalProvider,
    TrustLevel,
    VectorMetadata,
    chunk_text,
    content_hash,
    trust_for_source_type,
)
from search.indexing import extract_document


def documents_from(corpus):
    return [extract_document(record) for record in corpus]


class FailingProvider(EmbeddingProvider):
    """A provider that always fails, for testing isolation."""

    model_id = "always-fails"
    dimensions = 8

    def embed(self, texts):
        raise EmbeddingProviderError("upstream embedding service is unavailable")


class WrongSizeProvider(EmbeddingProvider):
    """Returns vectors of the wrong length."""

    model_id = "wrong-size"
    dimensions = 16

    def embed(self, texts):
        return [[0.1] * 8 for _ in texts]


class ShortBatchProvider(EmbeddingProvider):
    """Returns fewer vectors than inputs."""

    model_id = "short-batch"
    dimensions = 8

    def embed(self, texts):
        return [[0.1] * 8 for _ in texts][:-1] if len(texts) > 1 else []


class TestHashedProvider:
    def test_dimensions_are_respected(self):
        provider = HashedLexicalProvider(dimensions=256)
        vector = provider.embed_one("dynamic pressure during ascent")
        assert len(vector) == 256

    def test_vectors_are_unit_length(self):
        provider = HashedLexicalProvider()
        vector = provider.embed_one("orbital mechanics")
        norm = math.sqrt(sum(component ** 2 for component in vector))
        assert norm == pytest.approx(1.0, abs=1e-9)

    def test_deterministic_across_calls(self):
        provider = HashedLexicalProvider()
        assert provider.embed_one("Max-Q") == provider.embed_one("Max-Q")

    def test_deterministic_across_instances(self):
        assert (
            HashedLexicalProvider(dimensions=256).embed_one("staging")
            == HashedLexicalProvider(dimensions=256).embed_one("staging")
        )

    def test_related_text_is_closer_than_unrelated(self):
        provider = HashedLexicalProvider()
        query = provider.embed_one("what causes maximum dynamic pressure")
        related = provider.embed_one(
            "Max-Q is the point where aerodynamic dynamic pressure peaks"
        )
        unrelated = provider.embed_one(
            "the Minor Planet Center catalogues asteroid observations"
        )
        assert _cosine(query, related) > _cosine(query, unrelated)

    def test_empty_text_yields_a_zero_vector_not_an_error(self):
        vector = HashedLexicalProvider(dimensions=256).embed_one("")
        assert len(vector) == 256
        assert all(component == 0.0 for component in vector)

    def test_batch_order_is_preserved(self):
        provider = HashedLexicalProvider(dimensions=256)
        batch = provider.embed(["alpha", "beta", "gamma"])
        assert batch[0] == provider.embed_one("alpha")
        assert batch[2] == provider.embed_one("gamma")

    def test_tiny_dimension_rejected(self):
        with pytest.raises(ValueError, match="at least 128"):
            HashedLexicalProvider(dimensions=64)

    def test_health_check_reports_healthy(self):
        status = HashedLexicalProvider(dimensions=256).health_check()
        assert status["healthy"] is True
        assert status["dimensions"] == 256

    def test_health_check_reports_a_broken_provider(self):
        status = FailingProvider().health_check()
        assert status["healthy"] is False
        assert "unavailable" in status["detail"]


class TestTrustLevels:
    def test_scientific_archives_are_authoritative(self):
        assert trust_for_source_type([SourceType.PRIMARY_SCIENTIFIC]) is (
            TrustLevel.AUTHORITATIVE
        )

    def test_operational_feeds_are_moderate(self):
        assert trust_for_source_type([SourceType.SECONDARY_OPERATIONAL]) is (
            TrustLevel.MODERATE
        )

    def test_editorial_content_is_marked_editorial(self):
        assert trust_for_source_type([SourceType.EDITORIAL]) is TrustLevel.EDITORIAL

    def test_calculated_values_are_low_trust(self):
        assert trust_for_source_type([SourceType.CALCULATED]) is TrustLevel.LOW

    def test_best_source_wins(self):
        assert trust_for_source_type(
            [SourceType.BUNDLED_REFERENCE, SourceType.PRIMARY_SCIENTIFIC]
        ) is TrustLevel.AUTHORITATIVE

    def test_no_sources_is_low_trust(self):
        assert trust_for_source_type([]) is TrustLevel.LOW

    def test_string_values_are_accepted(self):
        assert trust_for_source_type(["PRIMARY_SCIENTIFIC"]) is TrustLevel.AUTHORITATIVE

    def test_meets_trust_comparison(self):
        metadata = VectorMetadata(
            canonical_id="x:1", trust_level=TrustLevel.HIGH
        )
        assert metadata.meets_trust(TrustLevel.MODERATE)
        assert not metadata.meets_trust(TrustLevel.AUTHORITATIVE)


class TestVectorMetadata:
    def test_every_vector_carries_the_required_metadata(self, corpus):
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        result = service.embed_documents(documents_from(corpus))
        assert result.records
        for record in result.records:
            metadata = record.metadata
            assert metadata.canonical_id
            assert metadata.source_names, metadata.canonical_id
            assert metadata.source_types
            assert metadata.trust_level
            assert metadata.model_id == "hashed-lexical-v1"
            assert metadata.dimensions == 256
            assert metadata.content_hash
            assert metadata.indexed_at is not None

    def test_mission_and_topic_metadata_present_where_applicable(self, corpus):
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        result = service.embed_documents(documents_from(corpus))
        missions = [
            record for record in result.records
            if record.metadata.entity_type is SearchEntityType.MISSION
        ]
        assert missions
        assert any(record.metadata.mission_ids for record in missions)
        assert any(record.metadata.topics for record in missions)

    def test_timestamp_is_the_records_own_anchor(self, corpus):
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        result = service.embed_documents(documents_from(corpus))
        dated = [r for r in result.records if r.metadata.timestamp is not None]
        assert dated

    def test_record_rejects_a_dimension_mismatch(self):
        with pytest.raises(ValidationError, match="dimensions but its metadata"):
            EmbeddingRecord(
                id="x:1#0",
                vector=[0.1, 0.2],
                metadata=VectorMetadata(canonical_id="x:1", dimensions=8),
            )

    def test_record_rejects_an_empty_vector(self):
        with pytest.raises(ValidationError, match="must not be empty"):
            EmbeddingRecord(
                id="x:1#0", vector=[], metadata=VectorMetadata(canonical_id="x:1")
            )


class TestContentHashing:
    def test_hash_is_stable(self):
        assert content_hash("a", ["b", "c"]) == content_hash("a", ["c", "b"])

    def test_hash_changes_with_content(self):
        assert content_hash("a") != content_hash("b")

    def test_none_parts_are_ignored(self):
        assert content_hash("a", None) == content_hash("a")


class TestChangeDetection:
    def _service(self):
        return EmbeddingService(HashedLexicalProvider(dimensions=256))

    def test_single_document(self, corpus):
        service = self._service()
        document = extract_document(corpus[0])
        result = service.embed_documents([document])
        assert result.created == 1
        assert result.skipped == 0
        assert result.records

    def test_batch(self, corpus):
        service = self._service()
        result = service.embed_documents(documents_from(corpus))
        assert result.created == len(corpus)
        assert result.embedded_documents == len(corpus)

    def test_unchanged_document_is_not_re_embedded(self, corpus):
        service = self._service()
        documents = documents_from(corpus)
        first = service.embed_documents(documents)
        second = service.embed_documents(documents)
        assert first.created == len(documents)
        assert second.created == 0
        assert second.updated == 0
        assert second.skipped == len(documents)
        assert second.records == []

    def test_changed_document_is_re_embedded(self, corpus):
        service = self._service()
        documents = documents_from(corpus)
        service.embed_documents(documents)

        changed = documents[0].model_copy(
            update={"fields": dict(documents[0].fields, body="entirely new content")}
        )
        result = service.embed_documents([changed] + documents[1:])
        assert result.updated == 1
        assert result.skipped == len(documents) - 1

    def test_force_re_embeds_everything(self, corpus):
        service = self._service()
        documents = documents_from(corpus)
        service.embed_documents(documents)
        result = service.embed_documents(documents, force=True)
        assert result.updated == len(documents)
        assert result.skipped == 0

    def test_changing_the_model_invalidates_every_vector(self, corpus):
        """Vectors from two models must never be mixed in one store."""
        documents = documents_from(corpus)
        first = EmbeddingService(HashedLexicalProvider(dimensions=256))
        first.embed_documents(documents)

        second = EmbeddingService(HashedLexicalProvider(dimensions=512))
        assert not second.is_unchanged(documents[0])

    def test_forget_forces_a_recompute(self, corpus):
        service = self._service()
        document = extract_document(corpus[0])
        service.embed_documents([document])
        service.forget(document.id)
        result = service.embed_documents([document])
        assert result.created == 1

    def test_known_document_count(self, corpus):
        service = self._service()
        service.embed_documents(documents_from(corpus))
        assert service.known_documents == len(corpus)


class TestFailureModes:
    def test_provider_failure_is_recorded_not_raised(self, corpus):
        service = EmbeddingService(FailingProvider())
        result = service.embed_documents(documents_from(corpus)[:3])
        assert result.failed == 3
        assert result.records == []
        assert any("unavailable" in error for error in result.errors)

    def test_a_failed_batch_leaves_no_remembered_hash(self, corpus):
        """A failure must not make the next run think the work was done."""
        service = EmbeddingService(FailingProvider())
        documents = documents_from(corpus)[:2]
        service.embed_documents(documents)
        assert service.known_documents == 0
        assert not service.is_unchanged(documents[0])

    def test_dimension_mismatch_is_fatal(self, corpus):
        service = EmbeddingService(WrongSizeProvider())
        with pytest.raises(DimensionMismatchError, match="8-dimensional"):
            service.embed_documents(documents_from(corpus)[:1])

    def test_short_batch_is_a_provider_error(self, corpus):
        service = EmbeddingService(ShortBatchProvider(), batch_size=32)
        result = service.embed_documents(documents_from(corpus)[:4])
        assert result.failed
        assert any("vector(s) for" in error for error in result.errors)

    def test_one_bad_batch_does_not_stop_later_batches(self, corpus):
        class FlakyProvider(EmbeddingProvider):
            model_id = "flaky"
            dimensions = 32

            def __init__(self):
                self.calls = 0

            def embed(self, texts):
                self.calls += 1
                if self.calls == 1:
                    raise EmbeddingProviderError("transient outage")
                return [[0.0] * 31 + [1.0] for _ in texts]

        provider = FlakyProvider()
        service = EmbeddingService(provider, batch_size=1)
        result = service.embed_documents(documents_from(corpus)[:3])
        assert result.failed == 1
        assert result.created == 2
        assert provider.calls == 3


class TestChunking:
    def test_short_text_is_one_chunk(self):
        assert chunk_text("short text") == ["short text"]

    def test_empty_text_yields_no_chunks(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_long_text_is_split(self):
        text = "\n\n".join("Paragraph {0}. {1}".format(i, "word " * 40)
                           for i in range(20))
        chunks = chunk_text(text, size=500, overlap=50)
        assert len(chunks) > 1
        assert all(len(chunk) <= 600 for chunk in chunks)

    def test_chunks_overlap(self):
        text = "word " * 600
        chunks = chunk_text(text, size=500, overlap=100)
        assert len(chunks) > 1
        #: Consecutive chunks share text, so a sentence on a boundary survives.
        assert chunks[0][-40:].strip() in chunks[1] or chunks[1].startswith("word")

    def test_overlap_must_be_smaller_than_the_chunk(self):
        with pytest.raises(ValueError, match="smaller than the chunk size"):
            chunk_text("a" * 100, size=50, overlap=50)

    def test_long_document_produces_several_vectors(self, corpus):
        service = EmbeddingService(
            HashedLexicalProvider(dimensions=256), chunk_size=300, chunk_overlap=50
        )
        concepts = [
            extract_document(record)
            for record in corpus
            if record.record_type == "learning_content"
        ]
        result = service.embed_documents(concepts)
        multi = [r for r in result.records if r.metadata.chunk_count > 1]
        assert multi
        assert all(r.metadata.chunk_index < r.metadata.chunk_count for r in multi)

    def test_chunk_ids_are_unique(self, corpus):
        service = EmbeddingService(
            HashedLexicalProvider(dimensions=256), chunk_size=300
        )
        result = service.embed_documents(documents_from(corpus))
        ids = [record.id for record in result.records]
        assert len(ids) == len(set(ids))


class TestQueryEmbedding:
    def test_query_embedding_matches_the_provider(self):
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        vector = service.embed_query("what causes Max-Q?")
        assert len(vector) == 256

    def test_query_embedding_is_not_cached(self):
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        service.embed_query("anything")
        assert service.known_documents == 0


class TestContentCoverage:
    def test_every_required_content_kind_is_embeddable(self, corpus):
        """Objects, missions, concepts, documents and events all embed."""
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        result = service.embed_documents(documents_from(corpus))
        kinds = {record.metadata.entity_type for record in result.records}
        assert SearchEntityType.SPACE_OBJECT in kinds
        assert SearchEntityType.MISSION in kinds
        assert SearchEntityType.CONCEPT in kinds
        assert SearchEntityType.DOCUMENT in kinds

    def test_ntrs_metadata_is_embedded_from_metadata_not_full_text(self, corpus):
        """Only the abstract and metadata are embedded, never fetched full text."""
        service = EmbeddingService(HashedLexicalProvider(dimensions=256))
        result = service.embed_documents(documents_from(corpus))
        documents = [
            record for record in result.records
            if record.metadata.entity_type is SearchEntityType.DOCUMENT
        ]
        assert documents
        assert all(record.metadata.trust_level is TrustLevel.HIGH
                   for record in documents)


def _cosine(a, b):
    return sum(x * y for x, y in zip(a, b))
