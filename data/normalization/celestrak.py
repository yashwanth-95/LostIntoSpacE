"""Normalizer for CelesTrak GP/OMM records.

Produces a `Satellite` (or `SpaceStation`) plus an `OrbitRecord` carrying SGP4
mean elements.

Three things this module is careful about:

1. **Element theory.** GP data is SGP4 mean elements in TEME. The record says so
   via `ElementTheory.SGP4_MEAN`, and the canonical `OrbitRecord` validator
   rejects the combination of SGP4 elements with a non-geocentric origin or a
   non-TEME frame. That prevents them being mixed with JPL osculating elements.
2. **Authority.** Every record is labelled `SECONDARY_OPERATIONAL_ORBIT_FEED`, so
   the distinction from a primary scientific source survives into storage and
   into anything shown to a user.
3. **Elements are not an ephemeris.** A GP element set plus SGP4 yields an
   approximate position; it is not a precise ephemeris, and nothing here
   produces a `StateVector`.
"""

from typing import Any, Dict, List, Optional, Tuple

from data.models import (
    CoordinateSystem,
    DataStatus,
    ElementTheory,
    FrameContext,
    ObjectType,
    OrbitalElements,
    OrbitRecord,
    OrbitRegime,
    OriginType,
    Quantity,
    ReferenceFrame,
    Satellite,
    SpaceStation,
    TimeScale,
    make_canonical_id,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType
from data.sources.celestrak import PROVENANCE_LABEL

from .parsing import clean_text, make_quantity, parse_datetime, parse_float, parse_int

__all__ = ["normalize_gp_record", "classify_regime", "STATION_CATALOG_NUMBERS"]

_MODULE = "data.normalization.celestrak"

#: Catalog numbers this project treats as crewable stations rather than plain
#: satellites. Small and explicit: guessing from the object name would
#: misclassify resupply vehicles and station modules.
STATION_CATALOG_NUMBERS = {
    25544: "International Space Station",
    48274: "Tiangong Space Station",
}

#: Earth's equatorial radius, used only to turn a mean motion into an
#: approximate altitude for regime classification. Not stored as a measurement.
_EARTH_RADIUS_KM = 6378.137
#: Earth's gravitational parameter, km^3/s^2.
_EARTH_MU = 398600.4418


def classify_regime(mean_motion_rev_per_day: Optional[float],
                    eccentricity: Optional[float]) -> OrbitRegime:
    """Approximate orbit regime from mean motion.

    A coarse label for faceting search, derived from the semi-major axis
    implied by the mean motion. It is explicitly a classification, not a
    measurement, and is never presented as a published value.
    """
    if not mean_motion_rev_per_day or mean_motion_rev_per_day <= 0:
        return OrbitRegime.UNKNOWN

    revolutions_per_second = mean_motion_rev_per_day / 86400.0
    angular_rate = revolutions_per_second * 2.0 * 3.141592653589793
    semi_major_axis_km = (_EARTH_MU / (angular_rate ** 2)) ** (1.0 / 3.0)
    altitude_km = semi_major_axis_km - _EARTH_RADIUS_KM

    if eccentricity is not None and eccentricity > 0.25:
        return OrbitRegime.HEO
    if altitude_km < 2000:
        return OrbitRegime.LEO
    if altitude_km < 35000:
        return OrbitRegime.MEO
    if altitude_km < 36500:
        return OrbitRegime.GEO
    return OrbitRegime.UNKNOWN


def normalize_gp_record(record) -> Tuple[Satellite, DataLineage]:
    """One OMM row -> canonical `Satellite`/`SpaceStation` with its orbit."""
    row: Dict[str, Any] = record.payload
    reference = record.source_reference

    catalog_number = parse_int(row.get("NORAD_CAT_ID"))
    object_name = clean_text(row.get("OBJECT_NAME")) or "unknown"
    international_designator = clean_text(row.get("OBJECT_ID"))

    if catalog_number is None:
        raise ValueError("GP record has no NORAD_CAT_ID; it cannot be identified")

    is_station = catalog_number in STATION_CATALOG_NUMBERS
    canonical_id = make_canonical_id(
        "space-station" if is_station else "satellite", str(catalog_number)
    )

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read OMM/GP fields", module=_MODULE)

    epoch = parse_datetime(row.get("EPOCH"))
    if epoch is None:
        raise ValueError(
            "GP record for {0} has no EPOCH; SGP4 elements are meaningless without "
            "one".format(catalog_number)
        )
    builder.normalized(
        TransformationType.EPOCH_CONVERSION,
        "EPOCH {0!r} -> UTC datetime".format(row.get("EPOCH")),
        module=_MODULE,
        inputs=["EPOCH"],
        output="orbits[0].epoch",
        input_value=row.get("EPOCH"),
        output_value=epoch.isoformat(),
    )

    mean_motion = parse_float(row.get("MEAN_MOTION"))
    eccentricity = parse_float(row.get("ECCENTRICITY"))

    elements = OrbitalElements(
        eccentricity=make_quantity(row.get("ECCENTRICITY"), "1", source=reference),
        inclination=make_quantity(row.get("INCLINATION"), "deg", source=reference),
        ascending_node_longitude=make_quantity(
            row.get("RA_OF_ASC_NODE"), "deg", source=reference
        ),
        argument_of_periapsis=make_quantity(
            row.get("ARG_OF_PERICENTER"), "deg", source=reference
        ),
        mean_anomaly=make_quantity(row.get("MEAN_ANOMALY"), "deg", source=reference),
        mean_motion=make_quantity(row.get("MEAN_MOTION"), "rev/day", source=reference),
        #: B* is published in inverse Earth radii. Keeping the unit explicit is
        #: what stops it being read as a plain number.
        bstar=make_quantity(row.get("BSTAR"), "1/R_earth", source=reference),
        mean_motion_dot=parse_float(row.get("MEAN_MOTION_DOT")),
        mean_motion_ddot=parse_float(row.get("MEAN_MOTION_DDOT")),
        revolution_number_at_epoch=parse_int(row.get("REV_AT_EPOCH")),
    )
    builder.normalized(
        TransformationType.FIELD_MAPPING,
        "mapped OMM element fields; mean motion kept in rev/day and B* in "
        "1/R_earth, the units the feed publishes",
        module=_MODULE,
        inputs=["MEAN_MOTION", "ECCENTRICITY", "INCLINATION", "RA_OF_ASC_NODE",
                "ARG_OF_PERICENTER", "MEAN_ANOMALY", "BSTAR"],
        output="orbits[0].elements",
    )

    frame = FrameContext(
        origin_type=OriginType.GEOCENTRIC,
        center_body="earth",
        reference_frame=ReferenceFrame.TEME,
        coordinate_system=CoordinateSystem.KEPLERIAN,
        time_scale=TimeScale.UTC,
    )
    builder.normalized(
        TransformationType.FRAME_ANNOTATION,
        "GP data is SGP4 mean elements in TEME, geocentric, epoch in UTC; these "
        "are not osculating Keplerian elements and must not be mixed with them",
        module=_MODULE,
        output="orbits[0].frame",
    )

    orbit = OrbitRecord(
        canonical_id="{0}:orbit:celestrak-{1}".format(
            canonical_id, epoch.strftime("%Y%m%d-%H%M%S")
        ),
        object_canonical_id=canonical_id,
        source_designation=object_name,
        epoch=epoch,
        frame=frame,
        element_theory=ElementTheory.SGP4_MEAN,
        elements=elements,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={
            #: The label that keeps this distinguishable from JPL/MPC output
            #: everywhere downstream.
            "provenance_label": PROVENANCE_LABEL,
            "ephemeris_type": parse_int(row.get("EPHEMERIS_TYPE")),
            "classification_type": clean_text(row.get("CLASSIFICATION_TYPE")),
            "element_set_number": parse_int(row.get("ELEMENT_SET_NO")),
            "note": (
                "SGP4 mean element set. Propagating it yields an approximate "
                "position, not a precise ephemeris."
            ),
        },
    )

    regime = classify_regime(mean_motion, eccentricity)
    builder.derived(
        "orbit regime {0} classified from mean motion {1} rev/day".format(
            regime.value, mean_motion
        ),
        inputs=["MEAN_MOTION", "ECCENTRICITY"],
        output="orbit_regime",
        module=_MODULE,
    )

    common = dict(
        canonical_id=canonical_id,
        name=object_name,
        norad_cat_id=catalog_number,
        international_designator=international_designator,
        orbit_regime=regime,
        is_active=True,
        orbits=[orbit],
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={"provenance_label": PROVENANCE_LABEL},
    )

    if is_station:
        satellite = SpaceStation(
            aliases=[STATION_CATALOG_NUMBERS[catalog_number]]
            if STATION_CATALOG_NUMBERS[catalog_number] != object_name
            else [],
            **common
        )
    else:
        satellite = Satellite(**common)

    builder.validated(
        "canonical {0} constructed; labelled {1}".format(
            type(satellite).__name__, PROVENANCE_LABEL
        ),
        module=_MODULE,
    )
    builder.finalized(module=_MODULE)
    return satellite, builder.build()
