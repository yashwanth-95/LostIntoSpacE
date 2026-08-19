"""Normalizer for NASA Exoplanet Archive rows.

An archive row becomes a canonical `Planet` (with `is_exoplanet=True`) plus,
when the row carries stellar columns, a `Star` for the host.

**Disposition is never upgraded locally.** The archive's `soltype` is mapped
onto `DataStatus`, and an unrecognised disposition becomes `UNKNOWN` rather
than `CONFIRMED`. A candidate stays a candidate.

Asymmetric error bars are preserved: the archive publishes `*err1` (upper) and
`*err2` (lower, as a negative number), and collapsing them to a single sigma
would discard real information about how well a parameter is known.
"""

from typing import Any, Dict, List, Optional, Tuple

from data.models import (
    DataStatus,
    DiscoveryInfo,
    ObjectType,
    PhysicalProperties,
    Planet,
    Quantity,
    Star,
    make_canonical_id,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import clean_text, make_quantity, parse_bool, parse_float, parse_int

__all__ = [
    "normalize_exoplanet_row",
    "SOLTYPE_TO_STATUS",
    "map_disposition",
    "strip_reference_markup",
]

_MODULE = "data.normalization.exoplanet"

#: Archive `soltype` -> canonical `DataStatus`.
#:
#: Anything not listed maps to UNKNOWN. That is deliberate: an unrecognised
#: disposition must never default to CONFIRMED.
SOLTYPE_TO_STATUS = {
    "published confirmed": DataStatus.CONFIRMED,
    "published candidate": DataStatus.CANDIDATE,
    "kepler confirmed": DataStatus.CONFIRMED,
    "kepler candidate": DataStatus.CANDIDATE,
    "k2 confirmed": DataStatus.CONFIRMED,
    "k2 candidate": DataStatus.CANDIDATE,
    "tess project candidate": DataStatus.CANDIDATE,
    "candidate": DataStatus.CANDIDATE,
    "confirmed": DataStatus.CONFIRMED,
    "false positive": DataStatus.DEPRECATED,
    "refuted": DataStatus.DEPRECATED,
    "retracted": DataStatus.DEPRECATED,
}


def map_disposition(soltype: Optional[str], table: Optional[str] = None) -> DataStatus:
    """Map an archive disposition onto `DataStatus`, conservatively.

    `pscomppars` carries no `soltype` column because every row in it is a
    confirmed planet; that is the one case where absence implies CONFIRMED, and
    it is stated explicitly rather than assumed for every table.
    """
    text = (clean_text(soltype) or "").lower()
    if text:
        return SOLTYPE_TO_STATUS.get(text, DataStatus.UNKNOWN)
    if (table or "").lower() == "pscomppars":
        return DataStatus.CONFIRMED
    return DataStatus.UNKNOWN


def strip_reference_markup(value: Optional[str]) -> Optional[str]:
    """Turn the archive's HTML anchor reference into plain text.

    `pl_refname` arrives as `<a refstr=... href=...>Bonomo et al. 2023</a>`.
    The visible text is the citation; the markup is display scaffolding that
    must not reach a stored record or an AI answer.
    """
    text = clean_text(value)
    if not text:
        return None
    if "<" not in text:
        return text
    inner = text.split(">", 1)[-1]
    inner = inner.split("<", 1)[0]
    return clean_text(inner) or text


def _asymmetric(row, base: str, unit: str, reference) -> Optional[Quantity]:
    """Build a quantity from `base`, `base+err1` (upper) and `base+err2` (lower)."""
    return make_quantity(
        row.get(base),
        unit,
        uncertainty_upper=row.get("{0}err1".format(base)),
        uncertainty_lower=row.get("{0}err2".format(base)),
        source=reference,
    )


def normalize_exoplanet_row(record) -> Tuple[Planet, Optional[Star], DataLineage]:
    """One archive row -> canonical `Planet` and, when present, its host `Star`."""
    row: Dict[str, Any] = record.payload
    reference = record.source_reference
    table = clean_text(row.get("_table"))

    planet_name = clean_text(row.get("pl_name"))
    if not planet_name:
        raise ValueError("exoplanet row has no pl_name")
    host_name = clean_text(row.get("hostname"))

    canonical_id = make_canonical_id("exoplanet", planet_name)
    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read exoplanet archive row from table {0!r}".format(table),
                   module=_MODULE)

    status = map_disposition(row.get("soltype"), table)
    builder.add(
        TransformationType.VALIDATION,
        "disposition soltype={0!r} (table {1!r}) -> data_status {2}".format(
            clean_text(row.get("soltype")), table, status.value
        ),
        module=_MODULE,
        inputs=["soltype"],
        output="data_status",
    )

    physical = PhysicalProperties(
        radius_mean=_asymmetric(row, "pl_rade", "R_earth", reference),
        mass=_asymmetric(row, "pl_bmasse", "M_earth", reference),
        effective_temperature=make_quantity(row.get("pl_eqt"), "K", source=reference),
    )
    if physical.radius_mean is not None or physical.mass is not None:
        builder.normalized(
            TransformationType.FIELD_MAPPING,
            "pl_rade/pl_bmasse mapped with asymmetric error bars preserved "
            "(err1 upper, err2 lower)",
            module=_MODULE,
            inputs=["pl_rade", "pl_radeerr1", "pl_radeerr2", "pl_bmasse"],
            output="physical",
        )

    host_star_id = make_canonical_id("star", host_name) if host_name else None

    planet = Planet(
        canonical_id=canonical_id,
        name=planet_name,
        is_exoplanet=True,
        host_star_name=host_name,
        host_star_canonical_id=host_star_id,
        system_name=host_name,
        data_status=status,
        physical=physical,
        system_planet_count=parse_int(row.get("sy_pnum")),
        equilibrium_temperature=make_quantity(row.get("pl_eqt"), "K", source=reference),
        insolation_flux=make_quantity(row.get("pl_insol"), "1", source=reference),
        distance=make_quantity(row.get("sy_dist"), "pc", source=reference),
        distance_context="from Earth (system distance)" if row.get("sy_dist") else None,
        discovery=DiscoveryInfo(
            discovery_year=parse_int(row.get("disc_year")),
            discovery_method=clean_text(row.get("discoverymethod")),
            discovery_facility=clean_text(row.get("disc_facility")),
            reference=strip_reference_markup(row.get("pl_refname")),
        ) if row.get("disc_year") or row.get("discoverymethod") else None,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={
            "table": table,
            "soltype": clean_text(row.get("soltype")),
            "default_flag": parse_int(row.get("default_flag")),
            "controversial": parse_bool(row.get("pl_controv_flag")),
            "planet_reference": strip_reference_markup(row.get("pl_refname")),
            #: Orbital parameters live here rather than in an `OrbitRecord`:
            #: the archive publishes period and semi-major axis without an
            #: epoch or a reference frame, so they cannot honestly become a
            #: frame-bearing orbit solution.
            "orbital_parameters": _orbital_parameters(row, reference),
        },
    )

    star = _host_star(row, host_name, host_star_id, reference, record, builder)
    builder.validated("canonical Planet constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return planet, star, builder.build()


def _orbital_parameters(row, reference) -> Dict[str, Any]:
    """Orbital values as published, each with its own uncertainties."""
    parameters: Dict[str, Any] = {}
    for base, unit, key in (
        ("pl_orbper", "d", "orbital_period"),
        ("pl_orbsmax", "au", "semi_major_axis"),
        ("pl_orbeccen", "1", "eccentricity"),
    ):
        quantity = _asymmetric(row, base, unit, reference)
        if quantity is not None:
            parameters[key] = quantity.model_dump(mode="json")
    inclination = make_quantity(row.get("pl_orbincl"), "deg", source=reference)
    if inclination is not None:
        parameters["inclination"] = inclination.model_dump(mode="json")
    return parameters


def _host_star(row, host_name, host_star_id, reference, record, builder) -> Optional[Star]:
    """Build the host `Star` when the row carries stellar columns."""
    if not host_name:
        return None
    stellar_columns = ("st_teff", "st_rad", "st_mass", "st_spectype", "st_met", "sy_vmag")
    if not any(row.get(column) is not None for column in stellar_columns):
        return None

    metallicity = make_quantity(row.get("st_met"), "1", source=reference)
    metallicity_ratio = clean_text(row.get("st_metratio"))
    if metallicity is not None and not metallicity_ratio:
        # A metallicity without its ratio is uninterpretable, and the canonical
        # model rejects it. Dropping the value keeps the rest of the star.
        metallicity = None

    magnitude = make_quantity(row.get("sy_vmag"), "mag", source=reference)

    builder.parsed(
        "built host star {0!r} from stellar columns".format(host_name), module=_MODULE
    )
    return Star(
        canonical_id=host_star_id,
        name=host_name,
        object_type=ObjectType.STAR,
        is_host_star=True,
        planet_count=parse_int(row.get("sy_pnum")),
        spectral_type=clean_text(row.get("st_spectype")),
        metallicity=metallicity,
        metallicity_ratio=metallicity_ratio if metallicity is not None else None,
        apparent_magnitude=magnitude,
        magnitude_band="V" if magnitude is not None else None,
        distance=make_quantity(row.get("sy_dist"), "pc", source=reference),
        distance_context="from Earth" if row.get("sy_dist") else None,
        physical=PhysicalProperties(
            effective_temperature=make_quantity(row.get("st_teff"), "K", source=reference),
            radius_mean=make_quantity(row.get("st_rad"), "R_sun", source=reference),
            mass=make_quantity(row.get("st_mass"), "M_sun", source=reference),
        ),
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={"stellar_reference": strip_reference_markup(row.get("st_refname"))},
    )
