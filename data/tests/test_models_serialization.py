"""Serialization round-trips.

Canonical records are persisted and shipped over the API as JSON, so every
record must survive `model_dump_json()` -> `model_validate_json()` with its
units, uncertainties, frame context and provenance intact.
"""

import json
from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from data.models import (
    SPACE_OBJECT_TYPES,
    Asteroid,
    AtmosphereProfile,
    Composition,
    CompositionComponent,
    CoordinateSystem,
    Covariance,
    DataStatus,
    DiscoveryInfo,
    ElementTheory,
    FrameContext,
    Mission,
    MissionOutcome,
    MissionStatus,
    MissionType,
    ObjectType,
    OrbitalElements,
    OrbitFitInfo,
    OrbitRecord,
    OriginType,
    PhysicalProperties,
    Planet,
    Quantity,
    ReferenceFrame,
    RotationProperties,
    TimeScale,
)

EPOCH = datetime(2026, 8, 18, 0, 0, tzinfo=timezone.utc)


class TestQuantitySerialization:
    def test_roundtrip_preserves_unit_and_uncertainty(self, jpl_source):
        original = Quantity(value=939.4, unit="km", uncertainty=0.2, source=jpl_source)
        restored = Quantity.model_validate_json(original.model_dump_json())
        assert restored == original
        assert restored.unit == "km"
        assert restored.uncertainty == pytest.approx(0.2)
        assert restored.source.source_record_id == "2000001"

    def test_json_mode_dump_is_json_serializable(self, jpl_source):
        payload = Quantity(value=1.0, unit="au", source=jpl_source).model_dump(mode="json")
        json.dumps(payload)  # must not raise
        assert payload["unit"] == "au"
        assert payload["source"]["source_type"] == "PRIMARY_SCIENTIFIC"

    def test_asymmetric_uncertainty_roundtrip(self):
        original = Quantity(
            value=2.38, unit="R_earth", uncertainty_upper=0.13, uncertainty_lower=0.11
        )
        restored = Quantity.model_validate_json(original.model_dump_json())
        assert restored.uncertainty_upper == pytest.approx(0.13)
        assert restored.uncertainty_lower == pytest.approx(0.11)
        assert restored.uncertainty is None


class TestSpaceObjectSerialization:
    def _mars(self, source):
        return Planet(
            canonical_id="planet:mars",
            name="Mars",
            aliases=["499", "Red Planet"],
            description="Fourth planet from the Sun.",
            data_status=DataStatus.CONFIRMED,
            confidence=0.95,
            confidence_basis="cross-checked against two archives",
            retrieved_at=EPOCH,
            source_updated_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            source_references=[source],
            moon_count=2,
            has_ring_system=False,
            physical=PhysicalProperties(
                mass=Quantity(value=6.4171e23, unit="kg", uncertainty=1e19, source=source),
                radius_equatorial=Quantity(value=3396.2, unit="km", source=source),
                radius_polar=Quantity(value=3376.2, unit="km", source=source),
                surface_gravity=Quantity(value=3.72076, unit="m/s2"),
                mean_temperature=Quantity(value=-63.0, unit="degC"),
                rotation=RotationProperties(
                    sidereal_rotation_period=Quantity(value=24.6229, unit="h"),
                    axial_tilt=Quantity(value=25.19, unit="deg"),
                    is_tidally_locked=False,
                ),
                atmosphere=AtmosphereProfile(
                    present=True,
                    surface_pressure=Quantity(value=636.0, unit="Pa"),
                    scale_height=Quantity(value=11.1, unit="km"),
                    composition=Composition(
                        basis="atmosphere",
                        components=[
                            CompositionComponent(
                                species="CO2", fraction=Quantity(value=95.1, unit="percent")
                            ),
                            CompositionComponent(species="Ar", qualifier="trace"),
                        ],
                    ),
                ),
                extra={"bond_albedo": Quantity(value=0.25, source=source)},
            ),
        )

    def test_full_planet_roundtrip(self, jpl_source):
        original = self._mars(jpl_source)
        restored = Planet.model_validate_json(original.model_dump_json())
        assert restored == original
        assert restored.physical.mass.uncertainty == pytest.approx(1e19)
        assert restored.physical.atmosphere.composition.basis == "atmosphere"
        assert restored.physical.extra["bond_albedo"].source.source_name == "jpl_sbdb"
        assert restored.object_type is ObjectType.PLANET

    def test_timestamps_roundtrip_as_utc(self, jpl_source):
        restored = Planet.model_validate_json(self._mars(jpl_source).model_dump_json())
        assert restored.retrieved_at == EPOCH
        assert restored.retrieved_at.tzinfo is not None

    def test_optional_fields_omitted_stay_none(self):
        minimal = Planet(canonical_id="planet:x", name="X")
        restored = Planet.model_validate_json(minimal.model_dump_json())
        assert restored.physical is None
        assert restored.discovery is None
        assert restored.orbits == []
        assert restored.confidence is None
        assert restored.source_references == []

    def test_record_type_selects_concrete_class(self, jpl_source):
        asteroid = Asteroid(
            canonical_id="asteroid:1-ceres",
            name="1 Ceres",
            designation="1 Ceres",
            packed_designation="00001",
            spk_id="2000001",
            number=1,
            orbit_class="MBA",
            is_near_earth_object=False,
            discovery=DiscoveryInfo(
                discovered_by="Giuseppe Piazzi",
                discovery_date=date(1801, 1, 1),
                discovery_year=1801,
                discovery_facility="Palermo Observatory",
            ),
            source_references=[jpl_source],
        )
        payload = json.loads(asteroid.model_dump_json())
        assert payload["record_type"] == "asteroid"
        cls = SPACE_OBJECT_TYPES[payload["record_type"]]
        restored = cls.model_validate(payload)
        assert isinstance(restored, Asteroid)
        assert restored.discovery.discovered_by == "Giuseppe Piazzi"

    def test_every_concrete_class_has_a_distinct_record_type(self):
        assert len(SPACE_OBJECT_TYPES) == 12
        assert SPACE_OBJECT_TYPES["space_station"].__name__ == "SpaceStation"

    def test_malformed_payload_rejected_on_load(self):
        with pytest.raises(ValidationError):
            Planet.model_validate_json('{"canonical_id": "planet:mars"}')  # missing name

    def test_unknown_field_in_payload_rejected(self):
        payload = {"canonical_id": "planet:mars", "name": "Mars", "colour": "red"}
        with pytest.raises(ValidationError):
            Planet.model_validate(payload)

    def test_bad_unit_in_payload_rejected(self):
        payload = {
            "canonical_id": "planet:mars",
            "name": "Mars",
            "physical": {"mass": {"value": 1.0, "unit": "smoots"}},
        }
        with pytest.raises(ValidationError, match="unknown unit"):
            Planet.model_validate(payload)

    def test_wrong_dimension_in_payload_rejected(self):
        payload = {
            "canonical_id": "planet:mars",
            "name": "Mars",
            "physical": {"mass": {"value": 1.0, "unit": "km"}},
        }
        with pytest.raises(ValidationError, match="mass must be MASS"):
            Planet.model_validate(payload)

    def test_orbit_belonging_to_another_object_rejected(self, jpl_source):
        orbit = OrbitRecord(
            canonical_id="orbit:other",
            object_canonical_id="asteroid:2-pallas",
            epoch=EPOCH,
            frame=FrameContext(origin_type=OriginType.HELIOCENTRIC, center_body="sun"),
            elements=OrbitalElements(eccentricity=Quantity(value=0.23)),
            source_references=[jpl_source],
        )
        with pytest.raises(ValidationError, match="belongs to"):
            Asteroid(canonical_id="asteroid:1-ceres", name="1 Ceres", orbits=[orbit])


class TestOrbitRecordSerialization:
    def test_full_orbit_roundtrip_preserves_frame_and_covariance(self, jpl_source):
        original = OrbitRecord(
            canonical_id="orbit:sbdb-ceres-2026-08-18",
            object_canonical_id="asteroid:1-ceres",
            source_designation="1 Ceres",
            epoch=EPOCH,
            frame=FrameContext(
                origin_type=OriginType.HELIOCENTRIC,
                center_body="sun",
                reference_frame=ReferenceFrame.ECLIPJ2000,
                coordinate_system=CoordinateSystem.KEPLERIAN,
                time_scale=TimeScale.TDB,
            ),
            element_theory=ElementTheory.OSCULATING_KEPLERIAN,
            elements=OrbitalElements(
                semi_major_axis=Quantity(value=2.7658, unit="au", uncertainty=1.2e-9),
                eccentricity=Quantity(value=0.07839, uncertainty=2.4e-9),
                inclination=Quantity(value=10.5868, unit="deg"),
            ),
            covariance=Covariance(
                labels=["e", "a"],
                units=["1", "au"],
                matrix=[[5.76e-18, 0.0], [0.0, 1.44e-18]],
            ),
            fit=OrbitFitInfo(observations_used=1075, condition_code="0"),
            orbit_class="MBA",
            orbit_class_description="Main-belt Asteroid",
            source_references=[jpl_source],
        )
        restored = OrbitRecord.model_validate_json(original.model_dump_json())
        assert restored == original
        assert restored.frame.origin_type is OriginType.HELIOCENTRIC
        assert restored.frame.time_scale is TimeScale.TDB
        assert restored.covariance.sigma("e") == pytest.approx(2.4e-9)
        assert restored.elements.semi_major_axis.uncertainty == pytest.approx(1.2e-9)

    def test_frame_is_required(self):
        with pytest.raises(ValidationError):
            OrbitRecord.model_validate(
                {
                    "canonical_id": "orbit:x",
                    "object_canonical_id": "asteroid:x",
                    "epoch": "2026-08-18T00:00:00Z",
                    "elements": {},
                }
            )

    def test_source_specific_fields_survive(self, jpl_source):
        original = OrbitRecord(
            canonical_id="orbit:x",
            object_canonical_id="asteroid:x",
            epoch=EPOCH,
            frame=FrameContext(origin_type=OriginType.HELIOCENTRIC, center_body="sun"),
            elements=OrbitalElements(eccentricity=Quantity(value=0.1)),
            source_references=[jpl_source],
            source_specific={"two_body": False, "sbdb_orbit_id": "JPL 132"},
        )
        restored = OrbitRecord.model_validate_json(original.model_dump_json())
        assert restored.source_specific["sbdb_orbit_id"] == "JPL 132"


class TestMissionSerialization:
    def test_mission_roundtrip(self, bundled_source):
        original = Mission(
            canonical_id="mission:chandrayaan-3",
            name="Chandrayaan-3",
            aliases=["CH-3"],
            agency="ISRO",
            mission_type=MissionType.LANDER,
            launch_date=date(2023, 7, 14),
            target_canonical_ids=["mission-target:moon-south-pole"],
            objectives=["Safe soft landing", "Rover mobility demonstration"],
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["First soft landing near the lunar south pole"],
            ),
            topics=["lunar", "lander", "isro"],
            source_references=[bundled_source],
        )
        restored = Mission.model_validate_json(original.model_dump_json())
        assert restored == original
        assert restored.status is MissionStatus.COMPLETED
        assert restored.launch_date == date(2023, 7, 14)

    def test_mission_record_type_is_distinct_from_project_mission(self):
        """Guards the contract boundary flagged in the Task 1 audit."""
        assert Mission.model_fields["record_type"].default == "mission"
        assert "user_id" not in Mission.model_fields
        assert "project_id" not in Mission.model_fields
