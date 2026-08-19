"""Canonical record identity, provenance, optional fields and dimension checks."""

from datetime import date, datetime, timezone

import pytest
from pydantic import ValidationError

from contracts.provenance import SourceReference, SourceType
from data.models import (
    Asteroid,
    AtmosphereProfile,
    CanonicalRecord,
    Composition,
    CompositionComponent,
    DataStatus,
    DiscoveryInfo,
    LaunchVehicle,
    Mission,
    MissionOutcome,
    MissionStatus,
    MissionType,
    Moon,
    ObjectType,
    PhysicalProperties,
    Planet,
    Quantity,
    RotationProperties,
    Satellite,
    SpaceStation,
    Spacecraft,
    Star,
    make_canonical_id,
    slugify,
)


class TestCanonicalId:
    def test_slugify_handles_designations(self):
        assert slugify("2000 SG344") == "2000-sg344"
        assert slugify("C/2019 Y4 (ATLAS)") == "c-2019-y4-atlas"
        assert slugify("  Mars  ") == "mars"

    def test_slugify_rejects_empty(self):
        with pytest.raises(ValueError, match="no alphanumeric"):
            slugify("   ---  ")

    def test_make_canonical_id(self):
        assert make_canonical_id("asteroid", "433 Eros") == "asteroid:433-eros"

    def test_uppercase_id_rejected(self):
        with pytest.raises(ValidationError, match="lowercase"):
            CanonicalRecord(canonical_id="Asteroid:Eros")

    def test_whitespace_in_id_rejected(self):
        with pytest.raises(ValidationError, match="whitespace"):
            CanonicalRecord(canonical_id="asteroid:433 eros")

    def test_empty_id_rejected(self):
        with pytest.raises(ValidationError):
            CanonicalRecord(canonical_id="")


class TestProvenanceOnRecords:
    def test_record_without_sources_reports_missing_provenance(self):
        record = CanonicalRecord(canonical_id="planet:mars")
        assert record.has_provenance is False
        assert record.primary_source is None
        assert record.attribution_lines() == []

    def test_primary_source_prefers_scientific_over_operational(
        self, jpl_source, celestrak_source
    ):
        record = CanonicalRecord(
            canonical_id="satellite:iss",
            source_references=[celestrak_source, jpl_source],
        )
        assert record.primary_source.source_name == "jpl_sbdb"

    def test_calculated_never_outranks_published(self, bundled_source):
        derived = SourceReference(source_name="local_calc", source_type=SourceType.CALCULATED)
        record = CanonicalRecord(
            canonical_id="planet:mars", source_references=[derived, bundled_source]
        )
        assert record.primary_source.source_name == "bundled_reference"

    def test_add_source_dedupes(self, jpl_source):
        record = CanonicalRecord(canonical_id="planet:mars")
        record.add_source(jpl_source)
        record.add_source(jpl_source)
        assert len(record.source_references) == 1

    def test_attribution_lines_use_display_credit(self, jpl_source, celestrak_source):
        record = CanonicalRecord(
            canonical_id="planet:mars", source_references=[jpl_source, celestrak_source]
        )
        assert record.attribution_lines() == [
            "NASA/JPL Small-Body Database",
            "CelesTrak GP data",
        ]

    def test_source_names_are_unique_and_ordered(self, jpl_source, celestrak_source):
        record = CanonicalRecord(
            canonical_id="planet:mars",
            source_references=[jpl_source, celestrak_source, jpl_source],
        )
        assert record.source_names() == ["jpl_sbdb", "celestrak_gp"]

    def test_source_url_with_api_key_rejected(self):
        with pytest.raises(ValidationError, match="credential"):
            SourceReference(
                source_name="nasa_neows",
                source_url="https://api.nasa.gov/neo/rest/v1/feed?api_key=SECRET",
            )

    def test_naive_timestamps_coerced_to_utc(self):
        ref = SourceReference(source_name="x", retrieved_at=datetime(2026, 1, 1, 12, 0))
        assert ref.retrieved_at.tzinfo is not None
        assert ref.retrieved_at == datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    def test_mark_verified_sets_timestamp(self):
        record = CanonicalRecord(canonical_id="planet:mars")
        assert record.last_verified_at is None
        record.mark_verified(datetime(2026, 8, 18, tzinfo=timezone.utc))
        assert record.last_verified_at == datetime(2026, 8, 18, tzinfo=timezone.utc)


class TestPhysicalPropertyDimensions:
    def test_correct_dimensions_accepted(self, jpl_source):
        props = PhysicalProperties(
            mass=Quantity(value=6.4171e23, unit="kg", uncertainty=1e19, source=jpl_source),
            radius_mean=Quantity(value=3389.5, unit="km", source=jpl_source),
            surface_gravity=Quantity(value=3.72076, unit="m/s2"),
            mean_temperature=Quantity(value=-63.0, unit="degC"),
            geometric_albedo=Quantity(value=0.17),
            absolute_magnitude=Quantity(value=-1.5, unit="mag"),
        )
        assert props.mass.dimension.value == "MASS"
        assert props.effective_radius().value == pytest.approx(3389.5)

    def test_mass_in_length_unit_rejected(self):
        with pytest.raises(ValidationError, match="mass must be MASS"):
            PhysicalProperties(mass=Quantity(value=1.0, unit="km"))

    def test_radius_in_mass_unit_rejected(self):
        with pytest.raises(ValidationError, match="radius_mean must be LENGTH"):
            PhysicalProperties(radius_mean=Quantity(value=1.0, unit="kg"))

    def test_albedo_with_magnitude_unit_rejected(self):
        with pytest.raises(ValidationError, match="geometric_albedo must be DIMENSIONLESS"):
            PhysicalProperties(geometric_albedo=Quantity(value=0.3, unit="mag"))

    def test_swapped_temperature_range_rejected(self):
        with pytest.raises(ValidationError, match="min_temperature exceeds"):
            PhysicalProperties(
                min_temperature=Quantity(value=300.0, unit="K"),
                max_temperature=Quantity(value=100.0, unit="K"),
            )

    def test_swapped_radii_rejected(self):
        with pytest.raises(ValidationError, match="probably swapped"):
            PhysicalProperties(
                radius_equatorial=Quantity(value=6356.8, unit="km"),
                radius_polar=Quantity(value=6378.1, unit="km"),
            )

    def test_extra_must_be_quantities(self):
        with pytest.raises(ValidationError):
            PhysicalProperties(extra={"tidal_q": 100.0})

    def test_extra_preserves_source_specific_values(self, jpl_source):
        props = PhysicalProperties(
            extra={"moment_of_inertia_factor": Quantity(value=0.365, source=jpl_source)}
        )
        assert props.extra["moment_of_inertia_factor"].source.source_name == "jpl_sbdb"

    def test_effective_radius_falls_back_to_half_diameter(self):
        props = PhysicalProperties(diameter=Quantity(value=1000.0, unit="km", uncertainty=10.0))
        radius = props.effective_radius()
        assert radius.si_value() == pytest.approx(500_000.0)
        assert radius.uncertainty == pytest.approx(5000.0)

    def test_all_fields_optional(self):
        props = PhysicalProperties()
        assert props.mass is None
        assert props.effective_radius() is None


class TestCompositionAndAtmosphere:
    def test_composition_totals(self):
        composition = Composition(
            basis="atmosphere",
            components=[
                CompositionComponent(species="CO2", fraction=Quantity(value=95.1, unit="percent")),
                CompositionComponent(species="N2", fraction=Quantity(value=2.59, unit="percent")),
                CompositionComponent(species="Ar", qualifier="trace"),
            ],
        )
        assert composition.total_fraction() == pytest.approx(0.9769)

    def test_qualitative_only_composition_has_no_total(self):
        composition = Composition(
            components=[CompositionComponent(species="silicates", qualifier="dominant")]
        )
        assert composition.total_fraction() is None

    def test_component_needs_fraction_or_qualifier(self):
        with pytest.raises(ValidationError, match="fraction or a"):
            CompositionComponent(species="CO2")

    def test_atmosphere_requires_atmospheric_basis(self):
        with pytest.raises(ValidationError, match="basis='atmosphere'"):
            AtmosphereProfile(composition=Composition(basis="bulk"))

    def test_bulk_slot_rejects_atmospheric_composition(self):
        with pytest.raises(ValidationError, match="belongs on"):
            PhysicalProperties(composition=Composition(basis="atmosphere"))

    def test_atmosphere_absence_is_recordable(self):
        profile = AtmosphereProfile(present=False)
        assert profile.present is False

    def test_rotation_dimension_checked(self):
        with pytest.raises(ValidationError, match="axial_tilt must be ANGLE"):
            RotationProperties(axial_tilt=Quantity(value=25.19, unit="km"))


class TestObjectHierarchy:
    def test_subclasses_pin_object_type(self):
        assert Moon(canonical_id="moon:luna", name="Moon",
                    parent_canonical_id="planet:earth").object_type is ObjectType.MOON
        assert Star(canonical_id="star:sol", name="Sun").object_type is ObjectType.STAR
        assert Asteroid(canonical_id="asteroid:ceres", name="Ceres").object_type is (
            ObjectType.ASTEROID
        )

    def test_moon_requires_parent(self):
        with pytest.raises(ValidationError, match="parent_canonical_id"):
            Moon(canonical_id="moon:luna", name="Moon")

    def test_exoplanet_switches_object_type_and_needs_host(self):
        planet = Planet(
            canonical_id="exoplanet:kepler-22-b",
            name="Kepler-22 b",
            is_exoplanet=True,
            host_star_name="Kepler-22",
            data_status=DataStatus.CONFIRMED,
        )
        assert planet.object_type is ObjectType.EXOPLANET
        assert planet.data_status is DataStatus.CONFIRMED

    def test_exoplanet_without_host_rejected(self):
        with pytest.raises(ValidationError, match="host star"):
            Planet(canonical_id="exoplanet:x", name="X", is_exoplanet=True)

    def test_candidate_status_is_not_confirmed(self):
        planet = Planet(
            canonical_id="exoplanet:koi-1234-01",
            name="KOI-1234.01",
            is_exoplanet=True,
            host_star_name="KOI-1234",
            data_status=DataStatus.CANDIDATE,
        )
        assert planet.data_status is DataStatus.CANDIDATE
        assert planet.data_status is not DataStatus.CONFIRMED

    def test_star_magnitude_requires_band(self):
        with pytest.raises(ValidationError, match="magnitude_band"):
            Star(
                canonical_id="star:kepler-22",
                name="Kepler-22",
                apparent_magnitude=Quantity(value=11.7, unit="mag"),
            )

    def test_star_metallicity_requires_ratio(self):
        with pytest.raises(ValidationError, match="metallicity_ratio"):
            Star(canonical_id="star:x", name="X", metallicity=Quantity(value=-0.29))

    def test_hazardous_non_neo_rejected(self):
        with pytest.raises(ValidationError, match="potentially hazardous"):
            Asteroid(
                canonical_id="asteroid:x",
                name="X",
                is_near_earth_object=False,
                is_potentially_hazardous=True,
            )

    def test_satellite_decayed_cannot_be_active(self):
        with pytest.raises(ValidationError, match="cannot be active"):
            Satellite(
                canonical_id="satellite:x",
                name="X",
                decay_date=date(2020, 1, 1),
                is_active=True,
            )

    def test_space_station_is_a_satellite(self):
        iss = SpaceStation(
            canonical_id="space-station:iss",
            name="International Space Station",
            aliases=["ISS", "ZARYA", "ISS (ZARYA)"],
            norad_cat_id=25544,
            international_designator="1998-067A",
            crew_capacity=7,
            partner_agencies=["NASA", "Roscosmos", "ESA", "JAXA", "CSA"],
        )
        assert isinstance(iss, Satellite)
        assert iss.object_type is ObjectType.SPACE_STATION
        assert iss.all_names()[0] == "International Space Station"

    def test_spacecraft_dry_mass_cannot_exceed_launch_mass(self):
        with pytest.raises(ValidationError, match="dry_mass exceeds"):
            Spacecraft(
                canonical_id="spacecraft:x",
                name="X",
                launch_mass=Quantity(value=100.0, unit="kg"),
                dry_mass=Quantity(value=200.0, unit="kg"),
            )

    def test_launch_vehicle_success_rate(self):
        vehicle = LaunchVehicle(
            canonical_id="launch-vehicle:pslv",
            name="PSLV",
            manufacturer="ISRO",
            stage_count=4,
            total_launches=60,
            successful_launches=57,
            liftoff_thrust=Quantity(value=4800.0, unit="kN"),
        )
        assert vehicle.success_rate() == pytest.approx(0.95)

    def test_launch_vehicle_thrust_must_be_force(self):
        with pytest.raises(ValidationError, match="liftoff_thrust must be FORCE"):
            LaunchVehicle(
                canonical_id="launch-vehicle:x",
                name="X",
                liftoff_thrust=Quantity(value=4800.0, unit="kg"),
            )

    def test_distance_requires_context(self):
        with pytest.raises(ValidationError, match="distance_context"):
            Star(canonical_id="star:x", name="X", distance=Quantity(value=190.0, unit="pc"))

    def test_aliases_deduped_case_insensitively(self):
        obj = Asteroid(
            canonical_id="asteroid:ceres",
            name="1 Ceres",
            aliases=["Ceres", "ceres", "  A899 OF ", ""],
        )
        assert obj.aliases == ["Ceres", "A899 OF"]

    def test_discovery_year_contradiction_rejected(self):
        with pytest.raises(ValidationError, match="contradicts"):
            DiscoveryInfo(discovery_date=date(1801, 1, 1), discovery_year=1802)

    def test_implausible_discovery_year_rejected(self):
        with pytest.raises(ValidationError, match="plausible"):
            DiscoveryInfo(discovery_year=1200)


class TestMissionCatalogue:
    def test_mission_derives_status_from_outcome(self):
        mission = Mission(
            canonical_id="mission:apollo-11",
            name="Apollo 11",
            agency="NASA",
            mission_type=MissionType.CREWED,
            launch_date=date(1969, 7, 16),
            end_date=date(1969, 7, 24),
            crew=["Neil Armstrong", "Michael Collins", "Buzz Aldrin"],
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["First crewed lunar landing"],
            ),
        )
        assert mission.status is MissionStatus.COMPLETED
        assert mission.is_complete

    def test_contradictory_status_rejected(self):
        with pytest.raises(ValidationError, match="contradicts"):
            Mission(
                canonical_id="mission:x",
                name="X",
                status=MissionStatus.ACTIVE,
                outcome=MissionOutcome(status=MissionStatus.FAILED),
            )

    def test_crew_on_uncrewed_type_rejected(self):
        with pytest.raises(ValidationError, match="has crew"):
            Mission(
                canonical_id="mission:x",
                name="X",
                mission_type=MissionType.ORBITER,
                crew=["Someone"],
            )

    def test_prehistoric_launch_date_rejected(self):
        with pytest.raises(ValidationError, match="predates spaceflight"):
            Mission(canonical_id="mission:x", name="X", launch_date=date(1801, 1, 1))

    def test_end_before_launch_rejected(self):
        with pytest.raises(ValidationError, match="after end_date"):
            Mission(
                canonical_id="mission:x",
                name="X",
                launch_date=date(2020, 1, 2),
                end_date=date(2020, 1, 1),
            )
