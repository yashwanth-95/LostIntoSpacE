"""Orbit, ephemeris and observation records — frame context and covariance."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from data.models import (
    CoordinateSystem,
    Covariance,
    ElementTheory,
    EphemerisRecord,
    FrameContext,
    Observation,
    ObservationType,
    OrbitalElements,
    OrbitFitInfo,
    OrbitRecord,
    OriginType,
    Quantity,
    ReferenceFrame,
    StateVector,
    TimeScale,
)

EPOCH = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)


def heliocentric_frame():
    return FrameContext(
        origin_type=OriginType.HELIOCENTRIC,
        center_body="sun",
        reference_frame=ReferenceFrame.ECLIPJ2000,
        coordinate_system=CoordinateSystem.KEPLERIAN,
        time_scale=TimeScale.TDB,
    )


def ceres_elements():
    return OrbitalElements(
        semi_major_axis=Quantity(value=2.7658, unit="au", uncertainty=1.2e-9),
        eccentricity=Quantity(value=0.07839, uncertainty=2.4e-9),
        inclination=Quantity(value=10.5868, unit="deg", uncertainty=1.5e-6),
        ascending_node_longitude=Quantity(value=80.2699, unit="deg"),
        argument_of_periapsis=Quantity(value=73.6, unit="deg"),
        mean_anomaly=Quantity(value=291.4, unit="deg"),
        orbital_period=Quantity(value=1681.6, unit="d"),
    )


class TestFrameContext:
    def test_heliocentric_must_be_centred_on_sun(self):
        with pytest.raises(ValidationError, match="requires center_body"):
            FrameContext(origin_type=OriginType.HELIOCENTRIC, center_body="earth")

    def test_geocentric_must_be_centred_on_earth(self):
        with pytest.raises(ValidationError, match="requires center_body"):
            FrameContext(origin_type=OriginType.GEOCENTRIC, center_body="sun")

    def test_barycentric_accepts_ssb(self):
        frame = FrameContext(origin_type=OriginType.BARYCENTRIC, center_body="SSB")
        assert frame.center_body == "ssb"

    def test_topocentric_requires_an_observing_site(self):
        with pytest.raises(ValidationError, match="observatory_code"):
            FrameContext(origin_type=OriginType.TOPOCENTRIC, center_body="earth")

    def test_planetocentric_allows_any_body(self):
        frame = FrameContext(origin_type=OriginType.PLANETOCENTRIC, center_body="Mars")
        assert frame.center_body == "mars"

    def test_describe_states_the_context(self):
        text = heliocentric_frame().describe()
        assert "heliocentric" in text
        assert "centred on sun" in text
        assert "ECLIPJ2000" in text
        assert "TDB" in text

    def test_frames_of_different_origin_are_not_comparable(self):
        helio = heliocentric_frame()
        geo = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.ECLIPJ2000,
            coordinate_system=CoordinateSystem.KEPLERIAN,
        )
        assert not helio.is_comparable_to(geo)
        assert helio.is_comparable_to(heliocentric_frame())


class TestOrbitalElements:
    def test_elements_keep_individual_uncertainties(self):
        elements = ceres_elements()
        assert elements.semi_major_axis.uncertainty == pytest.approx(1.2e-9)
        assert elements.eccentricity.uncertainty == pytest.approx(2.4e-9)

    def test_provided_element_names(self):
        names = ceres_elements().provided_element_names()
        assert "semi_major_axis" in names
        assert "true_anomaly" not in names

    def test_inclination_must_be_an_angle(self):
        with pytest.raises(ValidationError, match="inclination must be ANGLE"):
            OrbitalElements(inclination=Quantity(value=10.0, unit="km"))

    def test_semi_major_axis_must_be_a_length(self):
        with pytest.raises(ValidationError, match="semi_major_axis must be LENGTH"):
            OrbitalElements(semi_major_axis=Quantity(value=2.7, unit="deg"))

    def test_negative_eccentricity_rejected(self):
        with pytest.raises(ValidationError, match="must not be negative"):
            OrbitalElements(eccentricity=Quantity(value=-0.1))

    def test_periapsis_above_apoapsis_rejected(self):
        with pytest.raises(ValidationError, match="exceeds apoapsis"):
            OrbitalElements(
                periapsis_distance=Quantity(value=5.0, unit="au"),
                apoapsis_distance=Quantity(value=1.0, unit="au"),
            )

    def test_closed_orbit_detection(self):
        assert OrbitalElements(eccentricity=Quantity(value=0.5)).is_closed_orbit is True
        assert OrbitalElements(eccentricity=Quantity(value=1.4)).is_closed_orbit is False
        assert OrbitalElements().is_closed_orbit is None

    def test_mean_motion_accepts_rev_per_day(self):
        elements = OrbitalElements(mean_motion=Quantity(value=15.5, unit="rev/day"))
        assert elements.mean_motion.si_value() > 0


class TestOrbitRecord:
    def _record(self, **overrides):
        payload = dict(
            canonical_id="orbit:sbdb-ceres-2026",
            object_canonical_id="asteroid:1-ceres",
            source_designation="1 Ceres",
            epoch=EPOCH,
            frame=heliocentric_frame(),
            element_theory=ElementTheory.OSCULATING_KEPLERIAN,
            elements=ceres_elements(),
        )
        payload.update(overrides)
        return OrbitRecord(**payload)

    def test_valid_record(self, jpl_source):
        record = self._record(source_references=[jpl_source])
        assert record.record_type == "orbit_record"
        assert "osculating keplerian" in record.describe_context()
        assert "heliocentric" in record.describe_context()

    def test_cartesian_coordinate_system_rejected(self):
        frame = FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            coordinate_system=CoordinateSystem.CARTESIAN,
        )
        with pytest.raises(ValidationError, match="use EphemerisRecord"):
            self._record(frame=frame)

    def test_sgp4_elements_must_be_geocentric(self):
        with pytest.raises(ValidationError, match="geocentric by definition"):
            self._record(element_theory=ElementTheory.SGP4_MEAN)

    def test_sgp4_elements_must_be_teme(self):
        frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.J2000,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.UTC,
        )
        with pytest.raises(ValidationError, match="expressed in TEME"):
            self._record(frame=frame, element_theory=ElementTheory.SGP4_MEAN)

    def test_bstar_requires_sgp4_theory(self):
        elements = ceres_elements().model_copy(
            update={"bstar": Quantity(value=1e-4, unit="1/R_earth")}
        )
        with pytest.raises(ValidationError, match="only meaningful for SGP4"):
            self._record(elements=elements)

    def test_sgp4_record_with_drag_terms_accepted(self, celestrak_source):
        frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.TEME,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.UTC,
        )
        record = OrbitRecord(
            canonical_id="orbit:celestrak-25544-2026-08-18",
            object_canonical_id="space-station:iss",
            source_designation="ISS (ZARYA)",
            epoch=EPOCH,
            frame=frame,
            element_theory=ElementTheory.SGP4_MEAN,
            elements=OrbitalElements(
                eccentricity=Quantity(value=0.0002571),
                inclination=Quantity(value=51.6412, unit="deg"),
                ascending_node_longitude=Quantity(value=247.4627, unit="deg"),
                argument_of_periapsis=Quantity(value=130.5360, unit="deg"),
                mean_anomaly=Quantity(value=325.0288, unit="deg"),
                mean_motion=Quantity(value=15.50103472, unit="rev/day"),
                bstar=Quantity(value=0.00016717, unit="1/R_earth"),
                revolution_number_at_epoch=48123,
            ),
            source_references=[celestrak_source],
        )
        assert record.elements.bstar is not None
        assert record.primary_source.source_type.value == "SECONDARY_OPERATIONAL"

    def test_validity_window_ordering(self):
        with pytest.raises(ValidationError, match="valid_from is after"):
            self._record(
                valid_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
                valid_until=datetime(2026, 8, 1, tzinfo=timezone.utc),
            )

    def test_naive_epoch_coerced_to_utc(self):
        record = self._record(epoch=datetime(2026, 8, 18, 0, 0))
        assert record.epoch == EPOCH


class TestCovariance:
    def test_valid_covariance(self):
        cov = Covariance(
            labels=["e", "q", "i"],
            units=["1", "au", "deg"],
            matrix=[
                [4.0e-18, 1.0e-18, 0.0],
                [1.0e-18, 9.0e-18, 0.0],
                [0.0, 0.0, 2.25e-12],
            ],
        )
        assert cov.sigma("e") == pytest.approx(2.0e-9)
        assert cov.sigma("i") == pytest.approx(1.5e-6)
        assert cov.sigma("not_present") is None

    def test_non_square_rejected(self):
        with pytest.raises(ValidationError, match="rows but"):
            Covariance(labels=["e", "q"], matrix=[[1.0, 0.0]])

    def test_ragged_row_rejected(self):
        with pytest.raises(ValidationError, match="entries, expected"):
            Covariance(labels=["e", "q"], matrix=[[1.0, 0.0], [0.0]])

    def test_asymmetric_rejected(self):
        with pytest.raises(ValidationError, match="not symmetric"):
            Covariance(labels=["e", "q"], matrix=[[1.0, 2.0], [3.0, 4.0]])

    def test_negative_variance_rejected(self):
        with pytest.raises(ValidationError, match="cannot\\s+be negative"):
            Covariance(labels=["e"], matrix=[[-1.0]])

    def test_unit_count_must_match_labels(self):
        with pytest.raises(ValidationError, match="units has"):
            Covariance(labels=["e", "q"], units=["1"], matrix=[[1.0, 0.0], [0.0, 1.0]])


class TestOrbitFitInfo:
    def test_valid_fit(self):
        fit = OrbitFitInfo(
            observations_used=1075,
            data_arc_days=79101.0,
            first_observation=datetime(1802, 1, 1, tzinfo=timezone.utc),
            last_observation=datetime(2018, 6, 1, tzinfo=timezone.utc),
            rms_residual_arcsec=0.42,
            condition_code="0",
        )
        assert fit.observations_used == 1075

    def test_reversed_arc_rejected(self):
        with pytest.raises(ValidationError, match="after last_observation"):
            OrbitFitInfo(
                first_observation=datetime(2020, 1, 1, tzinfo=timezone.utc),
                last_observation=datetime(2010, 1, 1, tzinfo=timezone.utc),
            )

    def test_negative_observation_count_rejected(self):
        with pytest.raises(ValidationError, match="must not be negative"):
            OrbitFitInfo(observations_used=-1)


class TestStateVectorAndEphemeris:
    def _state(self, **overrides):
        payload = dict(
            epoch=EPOCH,
            x=Quantity(value=1.2345e8, unit="km"),
            y=Quantity(value=-9.8765e7, unit="km"),
            z=Quantity(value=4.321e6, unit="km"),
            vx=Quantity(value=21.5, unit="km/s"),
            vy=Quantity(value=24.1, unit="km/s"),
            vz=Quantity(value=-0.8, unit="km/s"),
        )
        payload.update(overrides)
        return StateVector(**payload)

    def test_position_and_velocity_in_si(self):
        state = self._state()
        assert state.has_velocity
        assert state.position_si()[0] == pytest.approx(1.2345e11)
        assert state.velocity_si()[0] == pytest.approx(21500.0)

    def test_position_only_state_allowed(self):
        state = self._state(vx=None, vy=None, vz=None)
        assert not state.has_velocity
        assert state.velocity_si() is None

    def test_partial_velocity_rejected(self):
        with pytest.raises(ValidationError, match="fully specified"):
            self._state(vz=None)

    def test_velocity_in_length_unit_rejected(self):
        with pytest.raises(ValidationError, match="vx must be VELOCITY"):
            self._state(vx=Quantity(value=21.5, unit="km"))

    def test_range_alias_accepted(self):
        state = StateVector(
            epoch=EPOCH,
            x=Quantity(value=1.0, unit="au"),
            y=Quantity(value=0.0, unit="au"),
            z=Quantity(value=0.0, unit="au"),
            **{"range": Quantity(value=1.0, unit="au")}
        )
        assert state.range_.si_value() == pytest.approx(1.495978707e11)

    def test_ephemeris_requires_state_coordinate_system(self):
        with pytest.raises(ValidationError, match="coordinate_system must be CARTESIAN"):
            EphemerisRecord(
                canonical_id="ephemeris:x",
                target_canonical_id="planet:mars",
                observer="500@399",
                frame=heliocentric_frame(),
            )

    def test_ephemeris_records_query_and_frame(self, jpl_source):
        frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            reference_frame=ReferenceFrame.ICRF,
            coordinate_system=CoordinateSystem.CARTESIAN,
            time_scale=TimeScale.TDB,
        )
        record = EphemerisRecord(
            canonical_id="ephemeris:horizons-mars-2026-08-18",
            target_canonical_id="planet:mars",
            target_designation="499",
            observer="500@399",
            frame=frame,
            start_time=EPOCH,
            stop_time=datetime(2026, 8, 19, tzinfo=timezone.utc),
            step_size="1 d",
            states=[self._state()],
            query_parameters={"COMMAND": "'499'", "CENTER": "'500@399'", "EPHEM_TYPE": "VECTORS"},
            source_references=[jpl_source],
        )
        assert record.epoch_range == (EPOCH, EPOCH)
        assert record.query_parameters["EPHEM_TYPE"] == "VECTORS"
        assert "relative to 500@399" in record.describe_context()

    def test_state_outside_window_rejected(self):
        frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            coordinate_system=CoordinateSystem.CARTESIAN,
        )
        with pytest.raises(ValidationError, match="before start_time"):
            EphemerisRecord(
                canonical_id="ephemeris:x",
                target_canonical_id="planet:mars",
                observer="500@399",
                frame=frame,
                start_time=datetime(2026, 8, 19, tzinfo=timezone.utc),
                stop_time=datetime(2026, 8, 20, tzinfo=timezone.utc),
                states=[self._state()],
            )

    def test_empty_ephemeris_has_no_range(self):
        frame = FrameContext(
            origin_type=OriginType.GEOCENTRIC,
            center_body="earth",
            coordinate_system=CoordinateSystem.CARTESIAN,
        )
        record = EphemerisRecord(
            canonical_id="ephemeris:empty",
            target_canonical_id="planet:mars",
            observer="500@399",
            frame=frame,
        )
        assert record.epoch_range is None


class TestObservation:
    def _observation(self, **overrides):
        payload = dict(
            canonical_id="observation:mpc-ceres-1",
            object_canonical_id="asteroid:1-ceres",
            source_designation="00001",
            observed_at=EPOCH,
            observation_type=ObservationType.OPTICAL_ASTROMETRY,
            frame=FrameContext(
                origin_type=OriginType.TOPOCENTRIC,
                center_body="earth",
                reference_frame=ReferenceFrame.ICRF,
                coordinate_system=CoordinateSystem.OBSERVED_ANGLES,
                time_scale=TimeScale.UTC,
                observatory_code="703",
            ),
            right_ascension=Quantity(value=182.63, unit="deg", uncertainty=0.0002),
            declination=Quantity(value=-3.41, unit="deg", uncertainty=0.0002),
            magnitude=Quantity(value=8.9, unit="mag"),
            magnitude_band="V",
        )
        payload.update(overrides)
        return Observation(**payload)

    def test_valid_observation(self, jpl_source):
        observation = self._observation(source_references=[jpl_source])
        assert observation.has_astrometry
        assert "site 703" in observation.describe_context()

    def test_observation_is_never_an_orbital_solution(self):
        """Raw astrometry must not be presentable as an orbit determination."""
        assert self._observation().is_orbital_solution is False
        with pytest.raises(ValidationError):
            self._observation(is_orbital_solution=True)

    def test_declination_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match=r"declination must be within"):
            self._observation(declination=Quantity(value=-120.0, unit="deg"))

    def test_right_ascension_out_of_range_rejected(self):
        with pytest.raises(ValidationError, match="right_ascension must be within"):
            self._observation(right_ascension=Quantity(value=400.0, unit="deg"))

    def test_magnitude_requires_band(self):
        with pytest.raises(ValidationError, match="photometric band"):
            self._observation(magnitude_band=None)

    def test_astrometry_needs_known_origin(self):
        with pytest.raises(ValidationError, match="observatory_code"):
            self._observation(
                frame=FrameContext(origin_type=OriginType.TOPOCENTRIC, center_body="earth")
            )

    def test_radar_observation_uses_range(self):
        observation = self._observation(
            observation_type=ObservationType.RADAR,
            right_ascension=None,
            declination=None,
            magnitude=None,
            magnitude_band=None,
            **{"range": Quantity(value=0.031, unit="au", uncertainty=1e-6)}
        )
        assert not observation.has_astrometry
        assert observation.range_.si_value() > 0
