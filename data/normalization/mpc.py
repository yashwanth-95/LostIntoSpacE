"""Normalizers for Minor Planet Center records.

Two mappings, deliberately kept apart:

    MPC orbit       -> canonical OrbitRecord   (a fitted solution)
    MPC observation -> canonical Observation   (a measurement)

The MPC is the only source in this project that publishes both, which is
exactly why the distinction is enforced here rather than assumed. An
`Observation` has no fields for orbital elements, so raw astrometry cannot
become an orbit determination by accident.

The Orbits API returns two element sets — cometary (`COM`) and Cartesian
(`CAR`) — each with its own covariance. `COM` is used for the canonical element
record because its parameters map onto the Keplerian fields; `CAR` is preserved
in `source_specific` rather than discarded, since it is the form a state-vector
consumer needs.
"""

from typing import Any, Dict, List, Optional, Tuple

from data.models import (
    CoordinateSystem,
    Covariance,
    DataStatus,
    ElementTheory,
    FrameContext,
    Observation,
    ObservationType,
    OrbitalElements,
    OrbitFitInfo,
    OrbitRecord,
    OriginType,
    Quantity,
    ReferenceFrame,
    TimeScale,
    make_canonical_id,
    slugify,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import (
    arcsec_to_degrees,
    clean_text,
    make_quantity,
    modified_julian_date_to_datetime,
    parse_bool,
    parse_datetime,
    parse_float,
    parse_int,
)

__all__ = ["normalize_mpc_orbit", "normalize_mpc_observations", "MPC_TIME_SCALES"]

_MODULE = "data.normalization.mpc"

#: MPC cometary element name -> (canonical field, unit).
_COM_MAP = {
    "q": ("periapsis_distance", "au"),
    "e": ("eccentricity", "1"),
    "i": ("inclination", "deg"),
    "node": ("ascending_node_longitude", "deg"),
    "argperi": ("argument_of_periapsis", "deg"),
}

#: The MPC labels its epoch time system "TDT", the older name for Terrestrial
#: Time. Mapping it explicitly avoids storing an unrecognised scale.
MPC_TIME_SCALES = {
    "TDT": TimeScale.TT,
    "TT": TimeScale.TT,
    "TDB": TimeScale.TDB,
    "UTC": TimeScale.UTC,
    "UT": TimeScale.UTC,
}


def normalize_mpc_orbit(record) -> Tuple[OrbitRecord, DataLineage]:
    """MPC orbit payload -> canonical `OrbitRecord` with covariance."""
    payload = record.payload
    reference = record.source_reference

    designation_data = payload.get("designation_data") or {}
    permid = clean_text(designation_data.get("permid"))
    name = clean_text(designation_data.get("name"))
    provisional = clean_text(
        designation_data.get("unpacked_primary_provisional_designation")
    )
    designation = permid or provisional or name or "unknown"

    categorization = payload.get("categorization") or {}
    is_comet = "comet" in (clean_text(categorization.get("object_type_str")) or "").lower()
    object_id = make_canonical_id("comet" if is_comet else "asteroid", designation)

    builder = LineageBuilder(object_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read mpc_orb blocks", module=_MODULE)

    epoch, time_scale = _mpc_epoch(payload, builder)
    if epoch is None:
        raise ValueError("MPC orbit for {0!r} has no usable epoch".format(designation))

    com = payload.get("COM") or {}
    elements, covariance = _com_elements(com, reference, epoch, builder)

    frame, frame_note = _mpc_frame(payload, time_scale)
    builder.normalized(
        TransformationType.FRAME_ANNOTATION,
        frame_note,
        module=_MODULE,
        output="frame",
    )

    stats = payload.get("orbit_fit_statistics") or {}
    software = payload.get("software_data") or {}
    fit = OrbitFitInfo(
        observations_used=parse_int(stats.get("nobs_total_sel"))
        or parse_int(stats.get("nobs_total")),
        rms_residual_arcsec=parse_float(stats.get("normalized_RMS")),
        condition_code=(
            None if stats.get("U_param") is None else str(stats.get("U_param"))
        ),
        solution_date=parse_datetime(software.get("fitting_datetime")),
        solution_id=clean_text(software.get("mpcorb_version")),
    )

    orbit = OrbitRecord(
        canonical_id="{0}:orbit:mpc-{1}".format(
            object_id, slugify(epoch.strftime("%Y%m%d"))
        ),
        object_canonical_id=object_id,
        source_designation=designation,
        epoch=epoch,
        frame=frame,
        element_theory=ElementTheory.OSCULATING_KEPLERIAN,
        elements=elements,
        covariance=covariance,
        fit=fit,
        orbit_class=clean_text(categorization.get("orbit_type_str")),
        orbit_class_description=clean_text(categorization.get("orbit_subtype_str")) or None,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={
            "packed_primary_provisional_designation": clean_text(
                designation_data.get("packed_primary_provisional_designation")
            ),
            "unpacked_secondary_provisional_designations": designation_data.get(
                "unpacked_secondary_provisional_designations"
            ),
            "iau_name": clean_text(designation_data.get("iau_name")) or name,
            "orbit_quality": clean_text(stats.get("orbit_quality")),
            "arc_length_total": clean_text(stats.get("arc_length_total")),
            "number_of_oppositions": parse_int(stats.get("nopp")),
            "nobs_radar": parse_int(stats.get("nobs_radar")),
            "magnitude_data": payload.get("magnitude_data"),
            "moid_data": payload.get("moid_data"),
            "non_grav_booleans": payload.get("non_grav_booleans"),
            "system_data": payload.get("system_data"),
            "fitting_software": "{0} {1}".format(
                clean_text(software.get("fitting_software_name")) or "?",
                clean_text(software.get("fitting_software_version")) or "?",
            ),
            #: The Cartesian element set is kept whole. It is a different
            #: parameterization of the same solution, not redundant data.
            "cartesian_element_set": payload.get("CAR"),
        },
    )
    builder.validated("canonical OrbitRecord constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return orbit, builder.build()


def _mpc_epoch(payload, builder):
    """Read the epoch and its time system, converting from MJD when needed."""
    epoch_data = payload.get("epoch_data") or {}
    raw = epoch_data.get("epoch")
    timeform = (clean_text(epoch_data.get("timeform")) or "").upper()
    timesystem = (clean_text(epoch_data.get("timesystem")) or "").upper()
    scale = MPC_TIME_SCALES.get(timesystem, TimeScale.UNKNOWN)

    if timeform == "MJD":
        epoch = modified_julian_date_to_datetime(raw)
        builder.normalized(
            TransformationType.EPOCH_CONVERSION,
            "epoch MJD {0} ({1}) -> datetime; time scale recorded as {2}".format(
                raw, timesystem or "unstated", scale.value
            ),
            module=_MODULE,
            inputs=["epoch_data.epoch"],
            output="epoch",
            input_value=raw,
            output_value=epoch.isoformat() if epoch else None,
        )
    elif timeform == "JD":
        from .parsing import julian_date_to_datetime

        epoch = julian_date_to_datetime(raw)
    else:
        epoch = parse_datetime(raw)
    return epoch, scale


def _com_elements(com, reference, epoch, builder):
    """Map the MPC cometary element set and its covariance."""
    names = [clean_text(name) for name in com.get("coefficient_names") or []]
    values = com.get("coefficient_values") or []
    sigmas = com.get("coefficient_uncertainties") or []
    if not names or len(values) != len(names):
        return OrbitalElements(), None

    fields: Dict[str, Any] = {}
    for index, name in enumerate(names):
        sigma = sigmas[index] if index < len(sigmas) else None
        if name == "peri_time":
            # Time of perihelion passage is published as an MJD.
            fields["periapsis_time"] = modified_julian_date_to_datetime(values[index])
            continue
        mapping = _COM_MAP.get(name)
        if mapping is None:
            continue
        field, unit = mapping
        quantity = make_quantity(
            values[index], unit, uncertainty=sigma, source=reference
        )
        if quantity is not None:
            fields[field] = quantity

    builder.normalized(
        TransformationType.FIELD_MAPPING,
        "mapped MPC cometary elements {0} onto canonical fields".format(names),
        module=_MODULE,
        inputs=["COM.coefficient_values"],
        output="elements",
    )

    covariance = _com_covariance(com, names, epoch, builder)
    return OrbitalElements(**fields), covariance


def _com_covariance(com, names, epoch, builder) -> Optional[Covariance]:
    """Rebuild the covariance matrix from the MPC's `covNN` keys.

    The MPC publishes only the upper triangle; the lower triangle is filled by
    symmetry, which is what the canonical `Covariance` validator then checks.
    """
    block = com.get("covariance") or {}
    if not block:
        return None
    size = len(names)
    matrix = [[0.0 for _ in range(size)] for _ in range(size)]
    seen = False
    for key, value in block.items():
        text = clean_text(key) or ""
        if not text.startswith("cov") or len(text) != 5:
            continue
        try:
            row = int(text[3])
            column = int(text[4])
        except ValueError:
            continue
        if row >= size or column >= size:
            continue
        number = parse_float(value)
        if number is None:
            continue
        matrix[row][column] = number
        matrix[column][row] = number
        seen = True
    if not seen:
        return None

    units = []
    for name in names:
        if name == "e":
            units.append("1")
        elif name == "q":
            units.append("au")
        elif name == "peri_time":
            units.append("d")
        else:
            units.append("deg")

    builder.parsed(
        "rebuilt {0}x{0} covariance from MPC covNN keys, mirroring the upper "
        "triangle".format(size),
        module=_MODULE,
        inputs=["COM.covariance"],
        output="covariance",
    )
    return Covariance(
        labels=list(names),
        units=units,
        matrix=matrix,
        epoch=epoch,
        notes="Covariance as published by the MPC for the cometary element set.",
    )


def _mpc_frame(payload, time_scale) -> Tuple[FrameContext, str]:
    """Build the frame context from the MPC's `system_data` block."""
    system = payload.get("system_data") or {}
    refframe = (clean_text(system.get("refframe")) or "").upper()
    refsys = (clean_text(system.get("refsys")) or "").lower()

    if "ecliptic" in refsys:
        frame = ReferenceFrame.ECLIPJ2000
    elif "icrf" in refframe:
        frame = ReferenceFrame.ICRF
    else:
        frame = ReferenceFrame.UNKNOWN

    note = (
        "MPC orbit elements are heliocentric; refframe={0!r}, refsys={1!r} -> {2}, "
        "epoch scale {3}".format(
            system.get("refframe"), system.get("refsys"), frame.value, time_scale.value
        )
    )
    return (
        FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            reference_frame=frame,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=time_scale,
        ),
        note,
    )


# --------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------

#: ADES observation modes that are optical astrometry.
_OPTICAL_MODES = {"CCD", "CMO", "VID", "PHO", "ENC", "PMT", "MIC", "MER", "TDI"}


def normalize_mpc_observations(record) -> Tuple[List[Observation], DataLineage]:
    """MPC observation rows -> canonical `Observation` records.

    Every result is a measurement. None of them is an orbit, and none of them
    can become one here: `Observation` has no element fields at all.
    """
    payload = record.payload
    reference = record.source_reference
    designation = clean_text(payload.get("designation")) or "unknown"
    output_format = clean_text(payload.get("format"))

    object_id = make_canonical_id("asteroid", designation)
    builder = LineageBuilder(object_id)
    builder.fetched(reference, module=_MODULE)

    if output_format != "ADES_DF":
        raise ValueError(
            "only the structured ADES_DF format is normalized; got {0!r}. The "
            "fixed-column OBS80 rendition is stored raw rather than parsed.".format(
                output_format
            )
        )

    rows = payload.get("rows") or []
    builder.parsed(
        "read {0} ADES observation row(s) for {1}".format(len(rows), designation),
        module=_MODULE,
    )

    observations: List[Observation] = []
    for index, row in enumerate(rows):
        observation = _ades_observation(row, index, designation, object_id, reference, record)
        if observation is not None:
            observations.append(observation)

    builder.normalized(
        TransformationType.UNIT_CONVERSION,
        "astrometric uncertainties arcsec -> degrees, to share the unit of the "
        "positions they qualify",
        module=_MODULE,
        inputs=["rmsra", "rmsdec"],
        output="right_ascension.uncertainty",
    )
    builder.validated(
        "{0} canonical Observation record(s) constructed; none is an orbital "
        "solution".format(len(observations)),
        module=_MODULE,
    )
    builder.finalized(module=_MODULE)
    return observations, builder.build()


def _ades_observation(row, index, designation, object_id, reference, record):
    """Map one ADES row onto an `Observation`."""
    observed_at = parse_datetime(row.get("obstime"))
    if observed_at is None:
        return None

    station = clean_text(row.get("stn"))
    obstype = (clean_text(row.get("Obstype")) or "optical").lower()
    mode = (clean_text(row.get("mode")) or "").upper()

    if obstype == "radar":
        observation_type = ObservationType.RADAR
    elif mode in _OPTICAL_MODES or obstype == "optical":
        observation_type = ObservationType.OPTICAL_ASTROMETRY
    else:
        observation_type = ObservationType.UNKNOWN

    # Radar observations are ranging measurements taken from a site; optical
    # astrometry is angular. Both are topocentric, and both therefore require
    # the observatory code that `FrameContext` insists on.
    frame = FrameContext(
        origin_type=OriginType.TOPOCENTRIC,
        center_body="earth",
        reference_frame=ReferenceFrame.ICRF,
        coordinate_system=(
            CoordinateSystem.OBSERVED_ANGLES
            if observation_type is not ObservationType.RADAR
            else CoordinateSystem.SPHERICAL
        ),
        time_scale=TimeScale.UTC,
        observatory_code=station or "XXX",
        observatory_name=clean_text(row.get("obscenter")),
    )

    magnitude = make_quantity(row.get("mag"), "mag", source=reference)
    band = clean_text(row.get("band"))
    if magnitude is not None and not band:
        # A magnitude without its band is not comparable, and the canonical
        # model rejects it. Dropping the magnitude keeps the astrometry usable.
        magnitude = None

    observation_id = clean_text(row.get("obsid")) or "{0}-{1}".format(
        slugify(designation), index
    )

    return Observation(
        canonical_id=make_canonical_id("observation", "mpc-{0}".format(observation_id)),
        object_canonical_id=object_id,
        source_designation=clean_text(row.get("provid")) or clean_text(row.get("permid"))
        or designation,
        packed_designation=clean_text(row.get("trksub")),
        observed_at=observed_at,
        observation_type=observation_type,
        frame=frame,
        right_ascension=make_quantity(
            row.get("ra"), "deg", uncertainty=arcsec_to_degrees(row.get("rmsra"))
        ) if row.get("ra") is not None else None,
        declination=make_quantity(
            row.get("dec"), "deg", uncertainty=arcsec_to_degrees(row.get("rmsdec"))
        ) if row.get("dec") is not None else None,
        magnitude=magnitude,
        magnitude_band=band if magnitude is not None else None,
        is_discovery=bool(parse_bool(row.get("disc")) or clean_text(row.get("disc"))),
        note=clean_text(row.get("notes")),
        program_code=clean_text(row.get("prog")),
        catalog_code=clean_text(row.get("astcat")),
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={
            "obsid": clean_text(row.get("obsid")),
            "trkid": clean_text(row.get("trkid")),
            "mode": mode or None,
            "photcat": clean_text(row.get("photcat")),
            "exposure_seconds": parse_float(row.get("exp")),
            "seeing_arcsec": parse_float(row.get("seeing")),
            "rms_time_seconds": parse_float(row.get("rmstime")),
            "reference": clean_text(row.get("ref")),
            "deprecated": row.get("deprecated"),
        },
    )
