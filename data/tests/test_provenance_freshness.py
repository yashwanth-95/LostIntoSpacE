"""Freshness policy, staleness and the 'never call it live' rules."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from contracts.provenance import FreshnessClass
from data.models import (
    CoordinateSystem,
    ElementTheory,
    FrameContext,
    Observation,
    ObservationType,
    OrbitalElements,
    OrbitRecord,
    OriginType,
    Planet,
    Quantity,
    ReferenceFrame,
    TimeScale,
)
from data.provenance import (
    DEFAULT_POLICY,
    POLICIES,
    FreshnessPolicy,
    SourceCategory,
    apply_freshness,
    assess_freshness,
    policy_for,
)

NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


class TestFreshnessPolicy:
    def test_every_registered_source_has_a_policy(self):
        for name in ("celestrak_gp", "jpl_horizons", "jpl_sbdb", "mpc_orbits",
                     "nasa_exoplanet_archive", "nasa_eonet", "bundled_reference"):
            assert name in POLICIES

    def test_unknown_source_gets_conservative_default(self):
        policy = policy_for("some_new_feed")
        assert policy is DEFAULT_POLICY
        assert policy.allows_live_presentation is False

    def test_static_reference_cannot_allow_live_presentation(self):
        with pytest.raises(ValidationError, match="never be presented as live"):
            FreshnessPolicy(
                source_category=SourceCategory.STATIC_REFERENCE,
                allows_live_presentation=True,
            )

    def test_cache_ttl_requires_cacheable(self):
        with pytest.raises(ValidationError, match="meaningless"):
            FreshnessPolicy(
                source_category=SourceCategory.DAILY,
                cacheable=False,
                cache_ttl=timedelta(hours=1),
            )

    def test_thresholds_must_be_ordered(self):
        with pytest.raises(ValidationError, match="must satisfy"):
            FreshnessPolicy(
                source_category=SourceCategory.DAILY,
                real_time_within=timedelta(days=1),
                near_real_time_within=timedelta(minutes=5),
            )

    def test_expiry_uses_cache_ttl(self):
        policy = POLICIES["celestrak_gp"]
        assert policy.expiry_for(NOW) == NOW + timedelta(hours=2)

    def test_no_expiry_without_ttl(self):
        assert POLICIES["bundled_reference"].expiry_for(NOW) is None


class TestRecordClassification:
    def _celestrak(self, epoch_age):
        return assess_freshness(
            policy=POLICIES["celestrak_gp"],
            retrieved_at=NOW,
            valid_at=NOW - epoch_age,
            now=NOW,
        )

    def test_minutes_old_element_set_is_real_time(self):
        result = self._celestrak(timedelta(minutes=2))
        assert result.freshness_class is FreshnessClass.REAL_TIME
        assert result.may_present_as_live is True

    def test_hours_old_element_set_is_near_real_time(self):
        result = self._celestrak(timedelta(hours=3))
        assert result.freshness_class is FreshnessClass.NEAR_REAL_TIME
        assert result.may_present_as_live is True

    def test_two_day_old_element_set_is_recent_not_current(self):
        result = self._celestrak(timedelta(days=2))
        assert result.freshness_class is FreshnessClass.RECENT
        assert result.may_present_as_live is True

    def test_week_old_element_set_is_historical_and_not_live(self):
        """The core rule: a historical element set is never 'current'."""
        result = self._celestrak(timedelta(days=7))
        assert result.freshness_class is FreshnessClass.HISTORICAL
        assert result.may_present_as_live is False
        assert result.is_stale is True

    def test_static_source_is_always_static_class(self):
        result = assess_freshness(
            policy=POLICIES["bundled_reference"],
            retrieved_at=NOW - timedelta(days=400),
            valid_at=NOW - timedelta(days=400),
            now=NOW,
        )
        assert result.freshness_class is FreshnessClass.STATIC
        assert result.is_stale is False
        assert result.may_present_as_live is False

    def test_record_without_epoch_cannot_be_called_current(self):
        result = assess_freshness(policy=POLICIES["celestrak_gp"], retrieved_at=NOW, now=NOW)
        assert result.freshness_class is FreshnessClass.HISTORICAL
        assert result.may_present_as_live is False
        assert "no epoch" in result.reason

    def test_archive_source_is_never_live_even_when_just_fetched(self):
        """A JPL solution fetched a second ago is authoritative, not live."""
        result = assess_freshness(
            policy=POLICIES["jpl_sbdb"],
            retrieved_at=NOW,
            valid_at=NOW - timedelta(seconds=30),
            now=NOW,
        )
        assert result.freshness_class is FreshnessClass.REAL_TIME
        assert result.may_present_as_live is False
        assert "not a live feed" in result.reason


class TestCacheExpiry:
    def test_fresh_cache_may_still_be_live(self):
        result = assess_freshness(
            policy=POLICIES["celestrak_gp"],
            retrieved_at=NOW - timedelta(minutes=30),
            valid_at=NOW - timedelta(minutes=30),
            now=NOW,
        )
        assert result.is_cache_expired is False
        assert result.may_present_as_live is True

    def test_expired_cache_may_not_be_called_live(self):
        """Rule 2: cached data is not live once its policy's TTL has passed."""
        result = assess_freshness(
            policy=POLICIES["celestrak_gp"],
            retrieved_at=NOW - timedelta(hours=5),
            valid_at=NOW - timedelta(minutes=1),
            now=NOW,
        )
        assert result.is_cache_expired is True
        assert result.may_present_as_live is False
        assert "past its TTL" in result.reason

    def test_retrieval_age_is_reported_separately_from_content_age(self):
        result = assess_freshness(
            policy=POLICIES["celestrak_gp"],
            retrieved_at=NOW - timedelta(hours=1),
            valid_at=NOW - timedelta(hours=4),
            now=NOW,
        )
        assert result.retrieval_age == timedelta(hours=1)
        assert result.content_age == timedelta(hours=4)


class TestApplyFreshnessToRecords:
    def _iss_orbit(self, epoch):
        return OrbitRecord(
            canonical_id="orbit:celestrak-25544",
            object_canonical_id="space-station:iss",
            epoch=epoch,
            retrieved_at=NOW,
            frame=FrameContext(
                origin_type=OriginType.GEOCENTRIC,
                center_body="earth",
                reference_frame=ReferenceFrame.TEME,
                coordinate_system=CoordinateSystem.KEPLERIAN,
                time_scale=TimeScale.UTC,
            ),
            element_theory=ElementTheory.SGP4_MEAN,
            elements=OrbitalElements(
                inclination=Quantity(value=51.64, unit="deg"),
                mean_motion=Quantity(value=15.5, unit="rev/day"),
            ),
        )

    def test_orbit_anchors_on_epoch_not_retrieval(self):
        record = self._iss_orbit(NOW - timedelta(days=10))
        assessment = apply_freshness(record, POLICIES["celestrak_gp"], now=NOW)
        assert record.freshness_class is FreshnessClass.HISTORICAL
        assert assessment.may_present_as_live is False
        assert assessment.content_age == timedelta(days=10)
        assert assessment.retrieval_age == timedelta(0)

    def test_apply_sets_expires_at(self):
        record = self._iss_orbit(NOW - timedelta(hours=1))
        apply_freshness(record, POLICIES["celestrak_gp"], now=NOW)
        assert record.expires_at == NOW + timedelta(hours=2)
        assert record.freshness_class is FreshnessClass.NEAR_REAL_TIME

    def test_observation_anchors_on_observed_at(self):
        observation = Observation(
            canonical_id="observation:mpc-1",
            object_canonical_id="asteroid:1-ceres",
            observed_at=NOW - timedelta(days=900),
            retrieved_at=NOW,
            observation_type=ObservationType.OPTICAL_ASTROMETRY,
            frame=FrameContext(
                origin_type=OriginType.TOPOCENTRIC,
                center_body="earth",
                coordinate_system=CoordinateSystem.OBSERVED_ANGLES,
                observatory_code="703",
            ),
        )
        assessment = apply_freshness(observation, POLICIES["mpc_observations"], now=NOW)
        assert observation.freshness_class is FreshnessClass.HISTORICAL
        # An observation is a historical measurement; that is not "stale".
        assert assessment.is_stale is False
        assert assessment.may_present_as_live is False

    def test_plain_record_uses_valid_at(self):
        planet = Planet(
            canonical_id="planet:mars",
            name="Mars",
            retrieved_at=NOW,
            valid_at=NOW - timedelta(days=1000),
        )
        assert planet.temporal_anchor() == NOW - timedelta(days=1000)
        apply_freshness(planet, POLICIES["bundled_reference"], now=NOW)
        assert planet.freshness_class is FreshnessClass.STATIC

    def test_describe_carries_the_caveat(self):
        record = self._iss_orbit(NOW - timedelta(days=10))
        assessment = apply_freshness(record, POLICIES["celestrak_gp"], now=NOW)
        assert assessment.describe().startswith("stale (historical)")
