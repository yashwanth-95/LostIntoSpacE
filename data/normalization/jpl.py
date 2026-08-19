"""Normalizers for JPL source records.

Two very different jobs:

* `normalize_sbdb_object` reads a JSON document and produces an `Asteroid` or
  `Comet` plus a fully-specified `OrbitRecord` including covariance.
* `parse_horizons_vectors` parses Horizons' *text* output into an
  `EphemerisRecord`. Horizons returns a formatted report, not JSON, and the
  header of that report is where the frame, centre, units and time scale are
  stated. Those are read from the response rather than assumed, because the
  same numbers mean different things under different headers.

Precision is preserved throughout: values keep the digits JPL published, and
each element carries its own published sigma.
"""

import re
from typing import Any, Dict, List, Optional, Tuple

from data.models import (
    Asteroid,
    Comet,
    Composition,
    CoordinateSystem,
    Covariance,
    DataStatus,
    DiscoveryInfo,
    ElementTheory,
    EphemerisRecord,
    FrameContext,
    ObjectType,
    OrbitalElements,
    OrbitFitInfo,
    OrbitRecord,
    OriginType,
    PhysicalProperties,
    Quantity,
    ReferenceFrame,
    RotationProperties,
    StateVector,
    TimeScale,
    make_canonical_id,
    slugify,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import (
    clean_text,
    julian_date_to_datetime,
    make_quantity,
    parse_bool,
    parse_datetime,
    parse_float,
    parse_int,
)

__all__ = [
    "normalize_sbdb_object",
    "parse_horizons_vectors",
    "HorizonsHeader",
]

_MODULE = "data.normalization.jpl"

#: SBDB element name -> (canonical field, unit override).
#: `None` means the element's own `units` field is authoritative.
_ELEMENT_MAP = {
    "e": ("eccentricity", "1"),
    "a": ("semi_major_axis", None),
    "q": ("periapsis_distance", None),
    "i": ("inclination", None),
    "om": ("ascending_node_longitude", None),
    "w": ("argument_of_periapsis", None),
    "ma": ("mean_anomaly", None),
    "per": ("orbital_period", None),
    "n": ("mean_motion", None),
    "ad": ("apoapsis_distance", None),
}

#: SBDB physical-parameter name -> (canonical field, unit override).
_PHYS_MAP = {
    "H": ("absolute_magnitude", "mag"),
    "G": ("magnitude_slope", "1"),
    "diameter": ("diameter", None),
    "GM": ("gm", None),
    "density": ("density", None),
    "albedo": ("geometric_albedo", "1"),
}


def normalize_sbdb_object(record) -> Tuple[Any, DataLineage]:
    """SBDB payload -> canonical `Asteroid` or `Comet`, with its orbit."""
    payload = record.payload
    reference = record.source_reference
    obj = payload.get("object") or {}

    designation = clean_text(obj.get("des"))
    fullname = clean_text(obj.get("fullname"))
    shortname = clean_text(obj.get("shortname"))
    name = shortname or fullname or designation or "unknown"

    kind = (clean_text(obj.get("kind")) or "").lower()
    is_comet = kind.startswith("c")
    canonical_id = make_canonical_id(
        "comet" if is_comet else "asteroid", designation or name
    )

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read SBDB object/orbit/phys_par blocks", module=_MODULE)

    physical, rotation_notes = _sbdb_physical(payload, reference, builder)
    orbit = _sbdb_orbit(payload, canonical_id, reference, record, builder)
    discovery = _sbdb_discovery(payload)

    aliases = [
        value
        for value in (fullname, designation, shortname)
        if value and value != name
    ]

    common = dict(
        canonical_id=canonical_id,
        name=name,
        aliases=aliases,
        designation=designation,
        spk_id=clean_text(obj.get("spkid")),
        physical=physical,
        orbits=[orbit] if orbit is not None else [],
        discovery=discovery,
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={
            "kind": kind,
            "orbit_id": clean_text(obj.get("orbit_id")),
            "prefix": clean_text(obj.get("prefix")),
            "sbdb_extras": rotation_notes,
        },
    )

    orbit_class = (obj.get("orbit_class") or {})
    if is_comet:
        body = Comet(
            comet_class=clean_text(orbit_class.get("code")),
            is_periodic=_comet_is_periodic(payload),
            **common
        )
    else:
        number = parse_int(designation) if (designation or "").isdigit() else None
        body = Asteroid(
            number=number,
            orbit_class=clean_text(orbit_class.get("code")),
            is_near_earth_object=parse_bool(obj.get("neo")),
            is_potentially_hazardous=parse_bool(obj.get("pha")),
            earth_moid=make_quantity(
                (payload.get("orbit") or {}).get("moid"), "au", source=reference
            ),
            spectral_type=_phys_text(payload, "spec_T") or _phys_text(payload, "spec_B"),
            **common
        )

    builder.validated("canonical body constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return body, builder.build()


def _comet_is_periodic(payload) -> Optional[bool]:
    """A comet is periodic when its solution is a closed orbit."""
    for element in (payload.get("orbit") or {}).get("elements") or []:
        if element.get("name") == "e":
            value = parse_float(element.get("value"))
            if value is None:
                return None
            return value < 1.0
    return None


def _phys_entries(payload) -> Dict[str, Dict[str, Any]]:
    return {
        clean_text(entry.get("name")): entry
        for entry in payload.get("phys_par") or []
        if clean_text(entry.get("name"))
    }


def _phys_text(payload, name: str) -> Optional[str]:
    entry = _phys_entries(payload).get(name)
    return clean_text(entry.get("value")) if entry else None


def _sbdb_physical(payload, reference, builder):
    """Map SBDB `phys_par` entries onto `PhysicalProperties`.

    Each entry carries its own unit and sigma, and several carry a literature
    reference of their own — `ref` is preserved in `source_specific` so a value
    can be traced to the paper it came from, not just to SBDB.
    """
    entries = _phys_entries(payload)
    extras: Dict[str, Any] = {}
    fields: Dict[str, Quantity] = {}

    for name, entry in entries.items():
        mapping = _PHYS_MAP.get(name)
        if mapping is None:
            value = clean_text(entry.get("value"))
            if value is not None:
                extras[name] = {
                    "value": value,
                    "units": clean_text(entry.get("units")),
                    "sigma": clean_text(entry.get("sigma")),
                    "title": clean_text(entry.get("title")),
                    "ref": clean_text(entry.get("ref")),
                }
            continue
        field, unit_override = mapping
        unit = unit_override or clean_text(entry.get("units")) or "1"
        quantity = make_quantity(
            entry.get("value"), unit, uncertainty=entry.get("sigma"), source=reference
        )
        if quantity is None:
            continue
        fields[field] = quantity
        if clean_text(entry.get("ref")):
            extras.setdefault("references", {})[field] = clean_text(entry.get("ref"))

    rotation = None
    rot_entry = entries.get("rot_per")
    pole_entry = entries.get("pole")
    pole_ra = pole_dec = None
    if pole_entry:
        # SBDB packs the pole as "RA/Dec" with a matching "sigmaRA/sigmaDec".
        parts = (clean_text(pole_entry.get("value")) or "").split("/")
        sigmas = (clean_text(pole_entry.get("sigma")) or "").split("/")
        if len(parts) == 2:
            pole_ra = make_quantity(
                parts[0], "deg",
                uncertainty=sigmas[0] if len(sigmas) == 2 else None,
                source=reference,
            )
            pole_dec = make_quantity(
                parts[1], "deg",
                uncertainty=sigmas[1] if len(sigmas) == 2 else None,
                source=reference,
            )
            builder.parsed(
                "split SBDB pole direction {0!r} into right ascension and "
                "declination".format(clean_text(pole_entry.get("value"))),
                module=_MODULE,
                inputs=["phys_par.pole"],
                output="physical.rotation",
            )

    if rot_entry or pole_ra is not None:
        rotation = RotationProperties(
            sidereal_rotation_period=make_quantity(
                (rot_entry or {}).get("value"),
                clean_text((rot_entry or {}).get("units")) or "h",
                uncertainty=(rot_entry or {}).get("sigma"),
                source=reference,
            ) if rot_entry else None,
            pole_right_ascension=pole_ra,
            pole_declination=pole_dec,
        )

    physical = PhysicalProperties(rotation=rotation, **fields)
    if fields:
        builder.normalized(
            TransformationType.FIELD_MAPPING,
            "mapped SBDB phys_par entries {0} onto canonical fields".format(
                sorted(fields)
            ),
            module=_MODULE,
            inputs=["phys_par"],
            output="physical",
        )
    return physical, extras


def _sbdb_orbit(payload, object_id, reference, record, builder) -> Optional[OrbitRecord]:
    """Build an `OrbitRecord` from SBDB's `orbit` block."""
    orbit = payload.get("orbit") or {}
    if not orbit:
        return None
    epoch = julian_date_to_datetime(orbit.get("epoch"))
    if epoch is None:
        return None

    builder.normalized(
        TransformationType.EPOCH_CONVERSION,
        "orbit epoch JD {0} (TDB) -> UTC-rendered datetime; time scale preserved "
        "as TDB".format(orbit.get("epoch")),
        module=_MODULE,
        inputs=["orbit.epoch"],
        output="orbits[0].epoch",
        input_value=orbit.get("epoch"),
        output_value=epoch.isoformat(),
    )

    fields: Dict[str, Any] = {}
    for element in orbit.get("elements") or []:
        name = clean_text(element.get("name"))
        mapping = _ELEMENT_MAP.get(name)
        if name == "tp":
            # Time of perihelion passage is a Julian date, not a scalar element.
            fields["periapsis_time"] = julian_date_to_datetime(element.get("value"))
            continue
        if mapping is None:
            continue
        field, unit_override = mapping
        unit = unit_override or clean_text(element.get("units")) or "1"
        quantity = make_quantity(
            element.get("value"),
            unit,
            uncertainty=element.get("sigma"),
            source=reference,
        )
        if quantity is not None:
            fields[field] = quantity

    elements = OrbitalElements(**fields)
    builder.normalized(
        TransformationType.FIELD_MAPPING,
        "mapped SBDB element names {0} onto canonical element fields".format(
            sorted(name for name in fields)
        ),
        module=_MODULE,
        inputs=["orbit.elements"],
        output="orbits[0].elements",
    )

    covariance = _sbdb_covariance(orbit, builder)

    equinox = (clean_text(orbit.get("equinox")) or "").upper()
    frame = ReferenceFrame.ECLIPJ2000 if equinox.startswith("J2000") else (
        ReferenceFrame.UNKNOWN
    )
    builder.normalized(
        TransformationType.FRAME_ANNOTATION,
        "SBDB elements are heliocentric ecliptic; equinox {0!r} -> {1}".format(
            equinox or "unstated", frame.value
        ),
        module=_MODULE,
        output="orbits[0].frame",
    )

    fit = OrbitFitInfo(
        observations_used=parse_int(orbit.get("n_obs_used")),
        data_arc_days=parse_float(orbit.get("data_arc")),
        first_observation=parse_datetime(orbit.get("first_obs")),
        last_observation=parse_datetime(orbit.get("last_obs")),
        rms_residual_arcsec=parse_float(orbit.get("rms")),
        condition_code=clean_text(orbit.get("condition_code")),
        solution_date=parse_datetime(orbit.get("soln_date")),
        solution_id=clean_text(orbit.get("orbit_id")),
    )

    orbit_class = ((payload.get("object") or {}).get("orbit_class") or {})
    return OrbitRecord(
        canonical_id="{0}:orbit:sbdb-{1}".format(object_id, clean_text(orbit.get("orbit_id"))
                                                 or epoch.strftime("%Y%m%d")),
        object_canonical_id=object_id,
        source_designation=clean_text((payload.get("object") or {}).get("des")),
        epoch=epoch,
        frame=FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            reference_frame=frame,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            time_scale=TimeScale.TDB,
        ),
        element_theory=ElementTheory.OSCULATING_KEPLERIAN,
        elements=elements,
        covariance=covariance,
        fit=fit,
        orbit_class=clean_text(orbit_class.get("code")),
        orbit_class_description=clean_text(orbit_class.get("name")),
        valid_from=parse_datetime(orbit.get("not_valid_before")),
        valid_until=parse_datetime(orbit.get("not_valid_after")),
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={
            "producer": clean_text(orbit.get("producer")),
            "source": clean_text(orbit.get("source")),
            "two_body": orbit.get("two_body"),
            "model_pars": orbit.get("model_pars"),
            "t_jup": clean_text(orbit.get("t_jup")),
            "moid_jup": clean_text(orbit.get("moid_jup")),
        },
    )


def _sbdb_covariance(orbit, builder) -> Optional[Covariance]:
    """Read SBDB's covariance matrix, preserving its own epoch and labels.

    The covariance epoch is frequently *not* the orbit epoch, so it is stored
    separately rather than inherited.
    """
    block = orbit.get("covariance") or {}
    labels = block.get("labels")
    data = block.get("data")
    if not labels or not data:
        return None
    matrix = [[float(parse_float(cell) or 0.0) for cell in row] for row in data]
    covariance = Covariance(
        labels=[str(label) for label in labels],
        matrix=matrix,
        epoch=julian_date_to_datetime(block.get("epoch")),
        notes="Covariance as published by JPL SBDB; element set: {0}".format(
            block.get("elements") or "unstated"
        ),
    )
    builder.parsed(
        "read {0}x{0} covariance with labels {1}".format(len(labels), list(labels)),
        module=_MODULE,
        inputs=["orbit.covariance"],
        output="orbits[0].covariance",
    )
    return covariance


def _sbdb_discovery(payload) -> Optional[DiscoveryInfo]:
    block = payload.get("discovery") or {}
    if not block:
        return None
    discovered = parse_datetime(block.get("date"))
    return DiscoveryInfo(
        discovered_by=clean_text(block.get("who")),
        discovery_date=discovered.date() if discovered else None,
        discovery_year=discovered.year if discovered else None,
        discovery_facility=clean_text(block.get("location")) or clean_text(block.get("site")),
        reference=clean_text(block.get("ref")),
    )


# --------------------------------------------------------------------------
# Horizons text parsing
# --------------------------------------------------------------------------

_HEADER_PATTERNS = {
    "target": re.compile(r"^Target body name:\s*(.+?)\s*(?:\{.*\})?\s*$", re.MULTILINE),
    "center": re.compile(r"^Center body name:\s*(.+?)\s*(?:\{.*\})?\s*$", re.MULTILINE),
    "center_site": re.compile(r"^Center-site name:\s*(.+?)\s*$", re.MULTILINE),
    "start": re.compile(r"^Start time\s*:\s*(.+?)\s*$", re.MULTILINE),
    "stop": re.compile(r"^Stop\s+time\s*:\s*(.+?)\s*$", re.MULTILINE),
    "step": re.compile(r"^Step-size\s*:\s*(.+?)\s*$", re.MULTILINE),
    "units": re.compile(r"^Output units\s*:\s*(.+?)\s*$", re.MULTILINE),
    "frame": re.compile(r"^Reference frame\s*:\s*(.+?)\s*$", re.MULTILINE),
    "output_type": re.compile(r"^Output type\s*:\s*(.+?)\s*$", re.MULTILINE),
}

_TIME_LINE = re.compile(
    r"^\s*(?P<jd>\d+\.\d+)\s*=\s*A\.D\.\s*(?P<cal>[\d\-A-Za-z:. ]+?)\s+"
    r"(?P<scale>TDB|UT|UTC|TT)\s*$"
)
_XYZ_LINE = re.compile(
    r"X\s*=\s*(?P<x>[-+0-9.Ee]+)\s+Y\s*=\s*(?P<y>[-+0-9.Ee]+)\s+Z\s*=\s*(?P<z>[-+0-9.Ee]+)"
)
_VXYZ_LINE = re.compile(
    r"VX\s*=\s*(?P<vx>[-+0-9.Ee]+)\s+VY\s*=\s*(?P<vy>[-+0-9.Ee]+)\s+"
    r"VZ\s*=\s*(?P<vz>[-+0-9.Ee]+)"
)

#: Horizons' "Output units" line -> (length unit, velocity unit).
_UNIT_TABLE = {
    "KM-S": ("km", "km/s"),
    "AU-D": ("au", "au/d"),
    "KM-D": ("km", "km/s"),
}

#: Centre names Horizons prints -> canonical origin type and body.
_CENTER_TABLE = (
    ("solar system barycenter", OriginType.BARYCENTRIC, "ssb"),
    ("sun", OriginType.HELIOCENTRIC, "sun"),
    ("earth-moon barycenter", OriginType.BARYCENTRIC, "earth-moon barycenter"),
    ("earth", OriginType.GEOCENTRIC, "earth"),
)


class HorizonsHeader(object):
    """Frame, units and time context read from a Horizons report header.

    Every field here changes what the numbers *mean*. Guessing any of them is
    how heliocentric and barycentric states end up averaged together.
    """

    def __init__(self, text: str):
        self.raw = {}
        for key, pattern in _HEADER_PATTERNS.items():
            match = pattern.search(text)
            self.raw[key] = clean_text(match.group(1)) if match else None

    @property
    def target(self) -> Optional[str]:
        return self.raw.get("target")

    @property
    def center(self) -> Optional[str]:
        return self.raw.get("center")

    @property
    def units(self) -> Tuple[str, str]:
        """(length unit, velocity unit) as stated by the report."""
        label = (self.raw.get("units") or "").upper().strip()
        for key, value in _UNIT_TABLE.items():
            if label.startswith(key):
                return value
        raise ValueError(
            "Horizons output units {0!r} are not recognised; refusing to guess "
            "units for state vectors".format(self.raw.get("units"))
        )

    @property
    def reference_frame(self) -> ReferenceFrame:
        text = (self.raw.get("frame") or "").lower()
        if "ecliptic" in text:
            return ReferenceFrame.ECLIPJ2000
        if "icrf" in text or "j2000" in text:
            return ReferenceFrame.ICRF
        return ReferenceFrame.UNKNOWN

    @property
    def origin(self) -> Tuple[OriginType, str]:
        text = (self.center or "").lower()
        for needle, origin_type, body in _CENTER_TABLE:
            if needle in text:
                return (origin_type, body)
        if self.center:
            return (OriginType.PLANETOCENTRIC, self.center.split("(")[0].strip().lower())
        return (OriginType.UNKNOWN, "unknown")

    @property
    def time_scale(self) -> TimeScale:
        for key in ("start", "stop"):
            value = (self.raw.get(key) or "").upper()
            for scale in ("TDB", "UTC", "TT", "UT1"):
                if value.endswith(scale) or " {0}".format(scale) in value:
                    return TimeScale[scale]
        return TimeScale.UNKNOWN


def parse_horizons_vectors(record) -> Tuple[EphemerisRecord, DataLineage]:
    """Horizons VECTORS report -> canonical `EphemerisRecord`.

    Units, frame, origin and time scale all come from the report header. If the
    header does not state the units, parsing fails rather than assuming — an
    ephemeris with guessed units is worse than no ephemeris.
    """
    text = record.payload.get("result") or ""
    request = record.payload.get("request") or {}
    reference = record.source_reference

    header = HorizonsHeader(text)
    length_unit, velocity_unit = header.units
    origin_type, center_body = header.origin
    time_scale = header.time_scale

    target_label = header.target or clean_text(record.source_record_id) or "unknown"
    canonical_target = make_canonical_id("body", target_label.split("(")[0].strip())
    canonical_id = "ephemeris:horizons-{0}-{1}".format(
        slugify(target_label.split("(")[0].strip()),
        slugify(str(record.retrieved_at.strftime("%Y%m%dT%H%M%S"))),
    )

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed(
        "read Horizons report header: units={0!r}, frame={1!r}, centre={2!r}".format(
            header.raw.get("units"), header.raw.get("frame"), header.center
        ),
        module=_MODULE,
    )
    builder.normalized(
        TransformationType.FRAME_ANNOTATION,
        "origin {0} centred on {1}, frame {2}, epochs in {3}".format(
            origin_type.value, center_body, header.reference_frame.value, time_scale.value
        ),
        module=_MODULE,
        output="frame",
    )

    states = _parse_state_block(text, length_unit, velocity_unit, reference)
    builder.parsed(
        "parsed {0} state vector(s) between $$SOE and $$EOE".format(len(states)),
        module=_MODULE,
        output="states",
    )

    epochs = [state.epoch for state in states]
    ephemeris = EphemerisRecord(
        canonical_id=canonical_id,
        target_canonical_id=canonical_target,
        target_designation=target_label,
        observer=header.center or request.get("CENTER", "unknown"),
        frame=FrameContext(
            origin_type=origin_type,
            center_body=center_body,
            reference_frame=header.reference_frame,
            coordinate_system=CoordinateSystem.CARTESIAN,
            time_scale=time_scale,
        ),
        start_time=min(epochs) if epochs else None,
        stop_time=max(epochs) if epochs else None,
        step_size=clean_text(header.raw.get("step")),
        states=states,
        #: The request is part of the result: a Horizons ephemeris is only
        #: reproducible if the exact query is known.
        query_parameters=dict(request),
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
        source_specific={
            "output_type": header.raw.get("output_type"),
            "reference_frame_text": header.raw.get("frame"),
            "output_units_text": header.raw.get("units"),
            "center_site": header.raw.get("center_site"),
        },
    )
    builder.validated("canonical EphemerisRecord constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return ephemeris, builder.build()


def _parse_state_block(text, length_unit, velocity_unit, reference) -> List[StateVector]:
    """Extract state vectors from between the $$SOE / $$EOE markers."""
    if "$$SOE" not in text or "$$EOE" not in text:
        raise ValueError("Horizons result has no $$SOE/$$EOE ephemeris block")
    block = text.split("$$SOE", 1)[1].split("$$EOE", 1)[0]

    states: List[StateVector] = []
    epoch = None
    position: Optional[Dict[str, str]] = None

    for line in block.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        time_match = _TIME_LINE.match(stripped)
        if time_match:
            epoch = julian_date_to_datetime(time_match.group("jd"))
            position = None
            continue
        xyz = _XYZ_LINE.search(stripped)
        if xyz and epoch is not None:
            position = xyz.groupdict()
            continue
        velocity = _VXYZ_LINE.search(stripped)
        if velocity and epoch is not None and position is not None:
            states.append(
                StateVector(
                    epoch=epoch,
                    x=make_quantity(position["x"], length_unit, source=reference),
                    y=make_quantity(position["y"], length_unit, source=reference),
                    z=make_quantity(position["z"], length_unit, source=reference),
                    vx=make_quantity(velocity.group("vx"), velocity_unit, source=reference),
                    vy=make_quantity(velocity.group("vy"), velocity_unit, source=reference),
                    vz=make_quantity(velocity.group("vz"), velocity_unit, source=reference),
                )
            )
            position = None
    return states
