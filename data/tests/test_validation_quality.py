"""The data-quality engine, exercised against deliberately conflicting data."""

from datetime import datetime, timedelta, timezone

import pytest

from contracts.provenance import SourceReference, SourceType
from data.models import (
    Asteroid,
    CoordinateSystem,
    ElementTheory,
    FrameContext,
    ObjectType,
    OrbitalElements,
    OrbitRecord,
    OriginType,
    PhysicalProperties,
    Planet,
    Quantity,
    ReferenceFrame,
    Satellite,
    Star,
    TimeScale,
)
from data.validation import (
    AuthorityPolicy,
    DataQualityEngine,
    IssueCode,
    RecommendedAction,
    Severity,
    range_for,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)


def reference(source_name, source_type=SourceType.PRIMARY_SCIENTIFIC):
    return SourceReference(
        source_name=source_name, source_type=source_type, retrieved_at=NOW
    )


JPL = reference("jpl_sbdb")
MPC = reference("mpc_orbits")
CELESTRAK = reference("celestrak_gp", SourceType.SECONDARY_OPERATIONAL)
ARCHIVE = reference("nasa_exoplanet_archive")


def engine(**kwargs) -> DataQualityEngine:
    return DataQualityEngine(now=NOW, **kwargs)


def ceres(source=JPL, **overrides):
    physical = overrides.pop(
        "physical",
        PhysicalProperties(
            mass=Quantity(value=9.3839e20, unit="kg", uncertainty=1e16, source=source),
            radius_mean=Quantity(value=469.7, unit="km", source=source),
            density=Quantity(value=2.162, unit="g/cm3", uncertainty=0.008, source=source),
            geometric_albedo=Quantity(value=0.09, source=source),
        ),
    )
    payload = dict(
        canonical_id="asteroid:1",
        name="1 Ceres",
        designation="1",
        spk_id="20000001",
        physical=physical,
        retrieved_at=NOW,
        valid_at=NOW - timedelta(days=1),
        source_references=[source],
    )
    payload.update(overrides)
    return Asteroid(**payload)


def heliocentric_orbit(source=JPL, semi_major_axis=2.7655526, sigma=1e-11, **overrides):
    payload = dict(
        canonical_id="asteroid:1:orbit:{0}".format(source.source_name),
        object_canonical_id="asteroid:1",
        epoch=NOW - timedelta(days=30),
        frame=FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            reference_frame=ReferenceFrame.ECLIPJ2000,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.TDB,
        ),
        element_theory=ElementTheory.OSCULATING_KEPLERIAN,
        elements=OrbitalElements(
            semi_major_axis=Quantity(
                value=semi_major_axis, unit="au", uncertainty=sigma, source=source
            ),
            eccentricity=Quantity(value=0.0797, uncertainty=1e-9, source=source),
            inclination=Quantity(value=10.588, unit="deg", source=source),
        ),
        retrieved_at=NOW,
        source_references=[source],
    )
    payload.update(overrides)
    return OrbitRecord(**payload)


class TestCleanRecord:
    def test_good_record_is_accepted(self):
        report = engine().check_record(ceres())
        assert report.errors == []
        assert report.recommended_action in (
            RecommendedAction.ACCEPT,
            RecommendedAction.ACCEPT_WITH_CAVEAT,
        )
        assert report.confidence > 0.8

    def test_summary_is_readable(self):
        report = engine().check_record(ceres())
        assert "asteroid:1" in report.summary()
        assert "confidence" in report.summary()


class TestProvenanceChecks:
    def test_missing_provenance_is_an_error(self):
        record = ceres()
        record.source_references = []
        report = engine().check_record(record)
        assert report.has(IssueCode.MISSING_PROVENANCE)
        assert report.recommended_action is RecommendedAction.REVIEW

    def test_unknown_authority_class_warns(self):
        record = ceres(source=reference("mystery_feed", SourceType.UNKNOWN))
        report = engine().check_record(record)
        issues = [i for i in report.issues if i.code is IssueCode.MISSING_PROVENANCE]
        assert issues and issues[0].severity is Severity.WARNING


class TestRangeChecks:
    def test_negative_mass_is_rejected_by_range(self):
        record = ceres(
            physical=PhysicalProperties(mass=Quantity(value=1.0, unit="kg", source=JPL))
        )
        report = engine().check_record(record)
        assert report.has(IssueCode.VALUE_OUT_OF_RANGE) or report.has(
            IssueCode.SUSPECT_UNIT_SCALE
        )

    def test_absurd_density_is_an_error(self):
        record = ceres(
            physical=PhysicalProperties(
                density=Quantity(value=1e9, unit="kg/m3", source=JPL)
            )
        )
        report = engine().check_record(record)
        assert report.has(IssueCode.VALUE_OUT_OF_RANGE)
        assert report.errors

    def test_high_albedo_warns_but_is_not_rejected(self):
        record = ceres(
            physical=PhysicalProperties(
                geometric_albedo=Quantity(value=1.4, source=JPL)
            )
        )
        report = engine().check_record(record)
        codes = [i.code for i in report.warnings]
        assert IssueCode.VALUE_OUT_OF_RANGE in codes
        assert report.errors == []

    def test_unit_scale_slip_is_identified_as_such(self):
        """A value out by a clean factor of 1000 reads as a unit slip."""
        record = ceres(
            #: 1000x the largest plausible mass — the signature of a g/kg or
            #: kg/tonne confusion upstream, not a wrong measurement.
            physical=PhysicalProperties(
                mass=Quantity(value=1e38, unit="kg", source=JPL)
            )
        )
        report = engine().check_record(record)
        assert report.has(IssueCode.SUSPECT_UNIT_SCALE)
        message = report.issues_for("physical.mass")[0].message
        assert "check the unit" in message

    def test_object_type_specific_range_applies(self):
        """A stellar mass on a planet record is wrong even though it is a mass."""
        planet = Planet(
            canonical_id="planet:x",
            name="X",
            physical=PhysicalProperties(mass=Quantity(value=2e30, unit="kg", source=JPL)),
            retrieved_at=NOW,
            source_references=[JPL],
        )
        report = engine().check_record(planet)
        assert report.has(IssueCode.VALUE_OUT_OF_RANGE)

    def test_same_mass_on_a_star_is_fine(self):
        star = Star(
            canonical_id="star:x",
            name="X",
            physical=PhysicalProperties(mass=Quantity(value=2e30, unit="kg", source=JPL)),
            retrieved_at=NOW,
            source_references=[JPL],
        )
        report = engine().check_record(star)
        assert not report.has(IssueCode.VALUE_OUT_OF_RANGE)

    def test_range_lookup_prefers_the_type_specific_rule(self):
        generic = range_for("physical.mass")
        stellar = range_for("physical.mass", "STAR")
        assert stellar is not generic
        assert stellar.error_min > generic.error_min


class TestDateChecks:
    def test_prehistoric_epoch_is_an_error(self):
        orbit = heliocentric_orbit(epoch=datetime(1500, 1, 1, tzinfo=timezone.utc))
        report = engine().check_record(orbit)
        assert report.has(IssueCode.IMPOSSIBLE_DATE)

    def test_absurdly_future_epoch_is_an_error(self):
        orbit = heliocentric_orbit(epoch=datetime(2600, 1, 1, tzinfo=timezone.utc))
        report = engine().check_record(orbit)
        assert report.has(IssueCode.IMPOSSIBLE_DATE)

    def test_predictive_ephemeris_epoch_is_allowed(self):
        """Ephemerides are legitimately about the future."""
        orbit = heliocentric_orbit(epoch=NOW + timedelta(days=365 * 5))
        report = engine().check_record(orbit)
        assert not report.has(IssueCode.IMPOSSIBLE_DATE)

    def test_future_retrieval_time_warns_about_the_clock(self):
        record = ceres(retrieved_at=NOW + timedelta(days=2))
        report = engine().check_record(record)
        issues = [i for i in report.issues if i.field == "retrieved_at"]
        assert issues and "system clock" in issues[0].message


class TestInternalConsistency:
    def test_density_inconsistent_with_mass_and_radius_is_flagged(self):
        record = ceres(
            physical=PhysicalProperties(
                mass=Quantity(value=9.3839e20, unit="kg", source=JPL),
                radius_mean=Quantity(value=469.7, unit="km", source=JPL),
                #: An order of magnitude off the implied ~2160 kg/m3.
                density=Quantity(value=21.6, unit="g/cm3", source=JPL),
            )
        )
        report = engine().check_record(record)
        assert report.has(IssueCode.INCONSISTENT_DERIVED_VALUE)

    def test_consistent_density_is_not_flagged(self):
        report = engine().check_record(ceres())
        assert not report.has(IssueCode.INCONSISTENT_DERIVED_VALUE)

    def test_unknown_origin_type_warns(self):
        orbit = heliocentric_orbit(
            frame=FrameContext(origin_type=OriginType.UNKNOWN, center_body="unknown")
        )
        report = engine().check_record(orbit)
        assert report.has(IssueCode.MISSING_REQUIRED_FIELD)

    def test_unstated_element_theory_warns(self):
        orbit = heliocentric_orbit(element_theory=ElementTheory.UNKNOWN)
        report = engine().check_record(orbit)
        assert any(
            "dynamical theory" in issue.message for issue in report.warnings
        )

    def test_unbound_orbit_warns(self):
        orbit = heliocentric_orbit(
            elements=OrbitalElements(eccentricity=Quantity(value=1.2, source=JPL))
        )
        report = engine().check_record(orbit)
        assert any("unbound orbit" in issue.message for issue in report.warnings)

    def test_missing_uncertainty_is_informational_only(self):
        orbit = heliocentric_orbit(sigma=None)
        report = engine().check_record(orbit)
        assert report.has(IssueCode.MISSING_UNCERTAINTY)
        assert not any(
            issue.code is IssueCode.MISSING_UNCERTAINTY for issue in report.errors
        )


class TestFreshnessChecks:
    def test_stale_operational_record_is_flagged_for_refresh(self):
        orbit = heliocentric_orbit(
            source=CELESTRAK,
            canonical_id="satellite:25544:orbit:old",
            object_canonical_id="satellite:25544",
            epoch=NOW - timedelta(days=30),
            frame=FrameContext(
                origin_type=OriginType.GEOCENTRIC,
                center_body="earth",
                reference_frame=ReferenceFrame.TEME,
                coordinate_system=CoordinateSystem.KEPLERIAN,
                time_scale=TimeScale.UTC,
            ),
            element_theory=ElementTheory.SGP4_MEAN,
            source_references=[CELESTRAK],
        )
        report = engine().check_record(orbit)
        assert report.has(IssueCode.STALE_RECORD)
        assert orbit.canonical_id in report.stale_records
        assert report.recommended_action in (
            RecommendedAction.REFRESH,
            RecommendedAction.ACCEPT_WITH_CAVEAT,
        )

    def test_fresh_record_is_not_flagged(self):
        report = engine().check_record(ceres())
        assert not report.has(IssueCode.STALE_RECORD)

    def test_record_without_an_anchor_is_noted(self):
        record = ceres(valid_at=None)
        report = engine().check_record(record)
        assert report.has(IssueCode.NO_TEMPORAL_ANCHOR)


class TestDatasetChecks:
    def test_duplicate_canonical_id_is_an_error(self):
        report = engine().check_dataset([ceres(), ceres()])
        assert report.has(IssueCode.DUPLICATE_IDENTIFIER)
        assert report.recommended_action is RecommendedAction.REVIEW

    def test_same_strong_identifier_on_two_entities_is_an_error(self):
        first = ceres()
        second = ceres(canonical_id="asteroid:1-duplicate", name="Ceres duplicate")
        report = engine().check_dataset([first, second])
        issues = [i for i in report.issues if i.code is IssueCode.DUPLICATE_IDENTIFIER]
        assert any("spk_id" in issue.message for issue in issues)

    def test_inconsistent_object_type_for_one_entity(self):
        asteroid = ceres()
        satellite = Satellite(
            canonical_id="asteroid:1", name="1 Ceres", retrieved_at=NOW,
            source_references=[CELESTRAK],
        )
        report = engine().check_dataset([asteroid, satellite])
        assert report.has(IssueCode.INCONSISTENT_OBJECT_TYPE)

    def test_inconsistent_naming_warns(self):
        first = ceres()
        second = ceres(name="Ceres (the dwarf planet)")
        report = engine().check_dataset([first, second])
        assert report.has(IssueCode.INCONSISTENT_NAMING)

    def test_clean_dataset_passes(self):
        other = ceres(
            canonical_id="asteroid:101955", name="101955 Bennu",
            designation="101955", spk_id="20101955",
        )
        report = engine().check_dataset([ceres(), other])
        assert report.records_checked == 2
        assert not report.has(IssueCode.DUPLICATE_IDENTIFIER)
        assert not report.has(IssueCode.INCONSISTENT_OBJECT_TYPE)


class TestConflictingDatasets:
    def test_agreement_within_uncertainty_is_not_a_conflict(self):
        """Two archives quoting the same value at different precision agree."""
        first = ceres(source=JPL)
        second = ceres(
            source=MPC,
            physical=PhysicalProperties(
                mass=Quantity(value=9.3840e20, unit="kg", uncertainty=1e17, source=MPC),
            ),
        )
        report = engine().compare_records(first, second)
        conflicts = report.conflicts
        assert conflicts
        assert all(conflict.within_uncertainty for conflict in conflicts)
        assert report.has(IssueCode.DISAGREEMENT_WITHIN_UNCERTAINTY)
        assert not report.has(IssueCode.CONFLICTING_VALUE)

    def test_real_disagreement_is_a_conflict(self):
        first = ceres(source=JPL)
        second = ceres(
            source=MPC,
            physical=PhysicalProperties(
                #: 20% heavier, with a tight uncertainty: a genuine disagreement.
                mass=Quantity(value=1.13e21, unit="kg", uncertainty=1e16, source=MPC),
            ),
        )
        report = engine().compare_records(first, second)
        assert report.has(IssueCode.CONFLICTING_VALUE)
        assert report.recommended_action is RecommendedAction.REVIEW
        assert report.confidence < 1.0

    def test_conflict_names_the_preferred_source_per_field(self):
        first = ceres(source=JPL)
        second = ceres(
            source=MPC,
            physical=PhysicalProperties(
                mass=Quantity(value=1.13e21, unit="kg", uncertainty=1e16, source=MPC),
            ),
        )
        report = engine().compare_records(first, second)
        conflict = [c for c in report.conflicts if c.field == "physical.mass"][0]
        assert conflict.preferred_source == "jpl_sbdb"
        assert conflict.preferred_value == pytest.approx(9.3839e20)

    def test_covariance_authority_differs_from_element_authority(self):
        """The engine must not pick one global winner."""
        policy = AuthorityPolicy()
        assert policy.preferred(["jpl_sbdb", "mpc_orbits"], "orbits.elements") == (
            "jpl_sbdb"
        )
        assert policy.preferred(["jpl_sbdb", "mpc_orbits"], "orbits.covariance") == (
            "mpc_orbits"
        )

    def test_exoplanet_radius_prefers_the_archive_over_jpl(self):
        policy = AuthorityPolicy()
        assert policy.preferred(
            ["jpl_sbdb", "nasa_exoplanet_archive"], "physical.radius_mean"
        ) == "nasa_exoplanet_archive"

    def test_ephemeris_authority_is_horizons(self):
        policy = AuthorityPolicy()
        assert policy.preferred(["jpl_sbdb", "jpl_horizons"], "states") == "jpl_horizons"

    def test_celestrak_loses_to_jpl_on_elements(self):
        policy = AuthorityPolicy()
        assert policy.preferred(
            ["celestrak_gp", "jpl_sbdb"], "orbits.elements"
        ) == "jpl_sbdb"

    def test_derived_values_never_outrank_published_ones(self):
        policy = AuthorityPolicy()
        assert policy.outranks("jpl_sbdb", "derived", "physical.mass")
        assert not policy.outranks("derived", "bundled_reference", "physical.mass")

    def test_unknown_source_ranks_last_but_is_usable(self):
        policy = AuthorityPolicy()
        assert policy.preferred(["brand_new_feed", "jpl_sbdb"], "orbits") == "jpl_sbdb"
        assert policy.preferred(["brand_new_feed"], "orbits") == "brand_new_feed"

    def test_authority_can_be_reconfigured(self):
        policy = AuthorityPolicy(
            field_authority={"physical.mass": ("mpc_orbits", "jpl_sbdb")}
        )
        assert policy.preferred(["jpl_sbdb", "mpc_orbits"], "physical.mass") == (
            "mpc_orbits"
        )

    def test_explanation_states_the_ordering_used(self):
        policy = AuthorityPolicy()
        text = policy.explain(["jpl_sbdb", "mpc_orbits"], "orbits.covariance")
        assert "preferred mpc_orbits" in text
        assert "orbits.covariance" in text

    def test_different_dimensions_are_always_a_conflict(self):
        first = ceres(
            source=JPL,
            physical=PhysicalProperties(
                radius_mean=Quantity(value=469.7, unit="km", source=JPL)
            ),
        )
        second = ceres(
            source=MPC,
            physical=PhysicalProperties(
                radius_mean=Quantity(value=469.7, unit="R_earth", source=MPC)
            ),
        )
        report = engine().compare_records(first, second)
        assert report.has(IssueCode.CONFLICTING_VALUE)


class TestFrameAndTheoryConflicts:
    def _with_orbit(self, orbit, canonical_id="asteroid:1"):
        return Asteroid(
            canonical_id=canonical_id,
            name="1 Ceres",
            orbits=[orbit],
            retrieved_at=NOW,
            source_references=orbit.source_references,
        )

    def test_incomparable_frames_are_flagged(self):
        heliocentric = self._with_orbit(heliocentric_orbit(source=JPL))
        geocentric_frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.TEME,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.UTC,
        )
        sgp4 = self._with_orbit(
            heliocentric_orbit(
                source=CELESTRAK,
                frame=geocentric_frame,
                element_theory=ElementTheory.SGP4_MEAN,
                elements=OrbitalElements(
                    eccentricity=Quantity(value=0.0008, source=CELESTRAK),
                    inclination=Quantity(value=51.6, unit="deg", source=CELESTRAK),
                ),
                source_references=[CELESTRAK],
            )
        )
        report = engine().compare_records(heliocentric, sgp4)
        assert report.has(IssueCode.INCOMPARABLE_FRAMES)

    def test_mixed_element_theories_are_an_error(self):
        """SGP4 mean elements and osculating elements are not interchangeable."""
        heliocentric = self._with_orbit(heliocentric_orbit(source=JPL))
        geocentric_frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.TEME,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.UTC,
        )
        sgp4 = self._with_orbit(
            heliocentric_orbit(
                source=CELESTRAK,
                frame=geocentric_frame,
                element_theory=ElementTheory.SGP4_MEAN,
                elements=OrbitalElements(
                    eccentricity=Quantity(value=0.0008, source=CELESTRAK)
                ),
                source_references=[CELESTRAK],
            )
        )
        report = engine().compare_records(heliocentric, sgp4)
        assert report.has(IssueCode.INCOMPATIBLE_ELEMENT_THEORY)
        assert report.recommended_action is RecommendedAction.REVIEW

    def test_same_frame_and_theory_is_comparable(self):
        first = self._with_orbit(heliocentric_orbit(source=JPL))
        second = self._with_orbit(heliocentric_orbit(source=MPC))
        report = engine().compare_records(first, second)
        assert not report.has(IssueCode.INCOMPARABLE_FRAMES)
        assert not report.has(IssueCode.INCOMPATIBLE_ELEMENT_THEORY)


class TestReportShape:
    def test_report_separates_errors_warnings_and_info(self):
        record = ceres()
        record.source_references = []
        record.physical = PhysicalProperties(
            geometric_albedo=Quantity(value=1.5, source=JPL)
        )
        report = engine().check_record(record)
        assert report.errors
        assert report.warnings
        assert report.codes()

    def test_confidence_falls_with_findings(self):
        clean = engine().check_record(ceres()).confidence
        broken = ceres()
        broken.source_references = []
        assert engine().check_record(broken).confidence < clean

    def test_confidence_is_bounded(self):
        record = ceres()
        record.source_references = []
        record.physical = PhysicalProperties(
            mass=Quantity(value=1e40, unit="kg", source=JPL),
            density=Quantity(value=1e12, unit="kg/m3", source=JPL),
        )
        report = engine().check_record(record)
        assert 0.0 <= report.confidence <= 1.0

    def test_describe_renders_issues_and_conflicts(self):
        first = ceres(source=JPL)
        second = ceres(
            source=MPC,
            physical=PhysicalProperties(
                mass=Quantity(value=1.13e21, unit="kg", uncertainty=1e16, source=MPC)
            ),
        )
        text = engine().compare_records(first, second).describe()
        assert "CONFLICT" in text
        assert "preferring jpl_sbdb" in text

    def test_reports_can_be_merged(self):
        a = engine().check_record(ceres())
        b = engine().check_record(ceres(canonical_id="asteroid:2", name="2 Pallas",
                                        designation="2", spk_id="20000002"))
        a.extend(b)
        assert a.records_checked == 2
