"""Data lineage, derived values, attribution and missing provenance."""

from datetime import datetime, timedelta, timezone

import pytest

from contracts.provenance import SourceReference, SourceType
from data.models import (
    CanonicalRecord,
    PhysicalProperties,
    Planet,
    Quantity,
    RotationProperties,
)
from data.provenance import (
    POLICIES,
    DataLineage,
    LineageBuilder,
    ProvenanceError,
    TransformationType,
    apply_freshness,
    assess_freshness,
    attribution_block,
    collect_citations,
    derive_quantity,
    freshness_caveat,
    require_provenance,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def sbdb_ref():
    return SourceReference(
        source_name="jpl_sbdb",
        source_type=SourceType.PRIMARY_SCIENTIFIC,
        source_record_id="2000001",
        source_version="sbdb-1.3",
        retrieved_at=NOW,
        attribution="NASA/JPL Small-Body Database",
    )


@pytest.fixture
def mpc_ref():
    return SourceReference(
        source_name="mpc_orbits",
        source_type=SourceType.PRIMARY_SCIENTIFIC,
        source_record_id="00001",
        retrieved_at=NOW,
        attribution="IAU Minor Planet Center",
    )


class TestLineageChain:
    def test_full_pipeline_chain_is_recorded_in_order(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref, module="data.sources.jpl.sbdb")
        builder.parsed("extracted phys_par block", module="data.sources.jpl.sbdb")
        builder.normalized(
            TransformationType.UNIT_CONVERSION,
            "diameter km -> m",
            inputs=["phys_par.diameter"],
            output="physical.diameter",
            input_value=939.4,
            output_value=939400.0,
        )
        builder.validated("dimension check passed")
        builder.finalized()
        lineage = builder.build()

        assert [step.sequence for step in lineage.steps] == [0, 1, 2, 3, 4]
        assert lineage.steps[0].transformation is TransformationType.FETCH
        assert lineage.steps[-1].transformation is TransformationType.FINALIZATION
        assert lineage.has_origin()
        assert lineage.origin_sources()[0].source_name == "jpl_sbdb"

    def test_transformation_chain_is_queryable_by_field(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        builder.normalized(
            TransformationType.UNIT_CONVERSION,
            "diameter km -> m",
            inputs=["phys_par.diameter"],
            output="physical.diameter",
        )
        lineage = builder.build()
        steps = lineage.steps_for("physical.diameter")
        assert len(steps) == 1
        assert "km -> m" in steps[0].description
        assert lineage.steps_for("physical.mass") == []

    def test_multiple_sources_are_all_tracked(self, sbdb_ref, mpc_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        builder.fetched(mpc_ref)
        builder.merged(
            "combined JPL physical parameters with MPC orbit",
            inputs=["jpl_sbdb", "mpc_orbits"],
        )
        lineage = builder.build()
        assert [ref.source_name for ref in lineage.source_references()] == [
            "jpl_sbdb",
            "mpc_orbits",
        ]
        assert len(lineage.origin_sources()) == 2

    def test_conflict_resolution_is_recorded(self, sbdb_ref, mpc_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        builder.fetched(mpc_ref)
        builder.resolved_conflict(
            "semi-major axis differed by 3e-7 au; kept JPL as higher authority",
            inputs=["jpl_sbdb.a", "mpc_orbits.a"],
            output="orbits[0].elements.semi_major_axis",
            parameters={"winner": "jpl_sbdb", "delta_au": 3e-7},
        )
        lineage = builder.build()
        conflicts = [
            step
            for step in lineage.steps
            if step.transformation is TransformationType.CONFLICT_RESOLUTION
        ]
        assert conflicts[0].parameters["winner"] == "jpl_sbdb"

    def test_fetch_without_source_is_rejected(self):
        with pytest.raises(ProvenanceError, match="must carry a SourceReference"):
            LineageBuilder("x").fetched(None)

    def test_non_normalization_step_rejected_by_normalized(self):
        with pytest.raises(ValueError, match="not a normalization"):
            LineageBuilder("x").normalized(TransformationType.MERGE, "nope")

    def test_describe_renders_the_chain(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        builder.normalized(
            TransformationType.EPOCH_CONVERSION,
            "JD TDB -> UTC datetime",
            inputs=["orbit.epoch"],
            output="orbits[0].epoch",
        )
        text = builder.build().describe()
        assert "0. fetched from jpl_sbdb" in text
        assert "-> orbits[0].epoch" in text

    def test_lineage_roundtrips_as_json(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        builder.validated("ok")
        original = builder.build()
        restored = DataLineage.model_validate_json(original.model_dump_json())
        assert restored.record_id == "asteroid:1-ceres"
        assert restored.origin_sources()[0].source_record_id == "2000001"


class TestDerivedValues:
    def test_derived_value_is_marked_calculated(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        mass = Quantity(value=9.3839e20, unit="kg", source=sbdb_ref)
        radius = Quantity(value=469.7, unit="km", source=sbdb_ref)
        volume = (4.0 / 3.0) * 3.141592653589793 * radius.si_value() ** 3
        density = derive_quantity(
            Quantity(value=mass.si_value() / volume, unit="kg/m3"),
            inputs={"physical.mass": mass, "physical.radius_mean": radius},
            description="density = mass / ((4/3)*pi*r^3)",
            output_field="physical.density",
            builder=builder,
            module="data.provenance.tests",
        )
        assert density.source.source_type is SourceType.CALCULATED
        assert "jpl_sbdb" in density.source.attribution
        assert density.value == pytest.approx(2162.0, rel=1e-3)

        lineage = builder.build()
        assert lineage.derived_fields() == ["physical.density"]
        assert lineage.is_derived("physical.density")
        assert not lineage.is_derived("physical.mass")

    def test_explain_field_flags_derived_values(self, sbdb_ref):
        builder = LineageBuilder("asteroid:1-ceres")
        builder.fetched(sbdb_ref)
        derive_quantity(
            Quantity(value=2162.0, unit="kg/m3"),
            inputs={"physical.mass": Quantity(value=1.0, unit="kg", source=sbdb_ref)},
            description="density from mass and radius",
            output_field="physical.density",
            builder=builder,
        )
        explanation = builder.build().explain_field("physical.density")
        assert "computed by this project" in explanation

    def test_explain_unknown_field(self):
        assert "No lineage recorded" in DataLineage(record_id="x").explain_field("a.b")

    def test_derivation_requires_inputs(self):
        with pytest.raises(ProvenanceError, match="must name the inputs"):
            LineageBuilder("x").derived("no inputs", inputs=[], output="y")

    def test_derive_quantity_requires_inputs(self):
        with pytest.raises(ProvenanceError, match="must name the inputs"):
            derive_quantity(
                Quantity(value=1.0), inputs={}, description="d", output_field="f"
            )

    def test_derive_quantity_rejects_non_quantity(self):
        with pytest.raises(TypeError):
            derive_quantity(42.0, inputs={"a": 1}, description="d", output_field="f")

    def test_derived_source_never_outranks_published(self, sbdb_ref):
        derived = derive_quantity(
            Quantity(value=1.0, unit="kg/m3"),
            inputs={"physical.mass": Quantity(value=1.0, unit="kg", source=sbdb_ref)},
            description="d",
            output_field="physical.density",
        )
        record = CanonicalRecord(
            canonical_id="asteroid:1-ceres",
            source_references=[derived.source, sbdb_ref],
        )
        assert record.primary_source.source_name == "jpl_sbdb"


class TestMissingProvenance:
    def test_record_without_sources_is_rejected(self):
        record = CanonicalRecord(canonical_id="planet:mars")
        with pytest.raises(ProvenanceError, match="no source_references"):
            require_provenance(record)

    def test_record_with_sources_passes(self, sbdb_ref):
        record = CanonicalRecord(canonical_id="planet:mars", source_references=[sbdb_ref])
        require_provenance(record)  # must not raise

    def test_lineage_without_fetch_step_is_rejected(self, sbdb_ref):
        record = CanonicalRecord(canonical_id="planet:mars", source_references=[sbdb_ref])
        lineage = LineageBuilder("planet:mars").validated("checked").build()
        with pytest.raises(ProvenanceError, match="no FETCH step"):
            require_provenance(record, lineage)

    def test_lineage_with_fetch_step_passes(self, sbdb_ref):
        record = CanonicalRecord(canonical_id="planet:mars", source_references=[sbdb_ref])
        lineage = LineageBuilder("planet:mars").fetched(sbdb_ref).build()
        require_provenance(record, lineage)


class TestAttribution:
    def _mars(self, ref, other):
        return Planet(
            canonical_id="planet:mars",
            name="Mars",
            retrieved_at=NOW,
            source_references=[ref],
            physical=PhysicalProperties(
                mass=Quantity(value=6.4171e23, unit="kg", source=ref),
                # Deliberately from a different archive than the record itself.
                surface_gravity=Quantity(value=3.72076, unit="m/s2", source=other),
                rotation=RotationProperties(
                    axial_tilt=Quantity(value=25.19, unit="deg", source=other)
                ),
            ),
        )

    def test_citations_cover_record_and_per_value_sources(self, sbdb_ref, mpc_ref):
        citations = collect_citations(self._mars(sbdb_ref, mpc_ref))
        names = [citation.source.source_name for citation in citations]
        assert "jpl_sbdb" in names
        assert "mpc_orbits" in names

    def test_nested_quantity_sources_are_discovered(self, sbdb_ref, mpc_ref):
        citations = collect_citations(self._mars(sbdb_ref, mpc_ref))
        fields = [citation.field_path for citation in citations if citation.field_path]
        assert "physical.rotation.axial_tilt" in fields

    def test_citation_text_includes_version_and_retrieval_date(self, sbdb_ref):
        citations = collect_citations(
            CanonicalRecord(canonical_id="planet:mars", source_references=[sbdb_ref])
        )
        text = citations[0].to_text()
        assert "NASA/JPL Small-Body Database" in text
        assert "version sbdb-1.3" in text
        assert "retrieved 2026-08-18" in text

    def test_citation_dict_is_api_ready(self, sbdb_ref):
        assessment = assess_freshness(POLICIES["jpl_sbdb"], retrieved_at=NOW, valid_at=NOW,
                                      now=NOW)
        payload = collect_citations(
            CanonicalRecord(canonical_id="planet:mars", source_references=[sbdb_ref]),
            assessment,
        )[0].to_dict()
        assert payload["source_type"] == "PRIMARY_SCIENTIFIC"
        assert payload["may_present_as_live"] is False
        assert payload["freshness_class"] == "REAL_TIME"

    def test_attribution_block_for_unattributed_record(self):
        text = attribution_block(CanonicalRecord(canonical_id="planet:mars"))
        assert "No source attribution" in text

    def test_attribution_block_lists_each_source(self, sbdb_ref, mpc_ref):
        text = attribution_block(self._mars(sbdb_ref, mpc_ref))
        assert "Sources:" in text
        assert "IAU Minor Planet Center" in text

    def test_caveat_present_for_stale_data(self):
        assessment = assess_freshness(
            POLICIES["celestrak_gp"],
            retrieved_at=NOW,
            valid_at=NOW - timedelta(days=30),
            now=NOW,
        )
        assert "stale" in freshness_caveat(assessment)

    def test_caveat_absent_for_genuinely_live_data(self):
        assessment = assess_freshness(
            POLICIES["celestrak_gp"],
            retrieved_at=NOW,
            valid_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert freshness_caveat(assessment) is None

    def test_caveat_names_the_freshness_class(self):
        assessment = assess_freshness(
            POLICIES["jpl_sbdb"],
            retrieved_at=NOW,
            valid_at=NOW - timedelta(days=2),
            now=NOW,
        )
        assert freshness_caveat(assessment) == "recent data, not a current measurement"

    def test_citation_carries_the_caveat_inline(self, sbdb_ref):
        record = CanonicalRecord(canonical_id="x:y", source_references=[sbdb_ref],
                                 retrieved_at=NOW, valid_at=NOW - timedelta(days=400))
        assessment = apply_freshness(record, POLICIES["jpl_sbdb"], now=NOW)
        text = collect_citations(record, assessment)[0].to_text()
        assert "stale" in text
