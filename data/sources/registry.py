"""Source registry.

One place that knows every adapter, so ingestion can ask "which sources provide
orbital elements?" instead of hard-coding a list that drifts out of date.

Registration is explicit rather than by import-scanning: an adapter that is not
listed here is not wired in, which is a deliberate gate.
"""

from typing import Dict, Iterable, List, Optional, Type

from .base import Capability, SourceInfo, SpaceDataSource
from .celestrak import CelestrakSource
from .esa import CopernicusSource
from .exoplanet_archive import ExoplanetArchiveSource
from .isro import BhoonidhiSource
from .jpl import JplHorizonsSource, JplSbdbSource
from .mpc import MpcObservationsSource, MpcOrbitsSource
from .nasa import NasaApodSource, NasaEonetSource, NasaNeoWsSource, NasaNtrsSource

__all__ = [
    "SOURCE_CLASSES",
    "get_source_class",
    "build_source",
    "all_source_info",
    "sources_with_capability",
    "AUTHORITY_BY_CAPABILITY",
    "preferred_source_for",
]

#: Every adapter, keyed by the `source_name` it reports. These keys match
#: `SourceReference.source_name` and the freshness policy table, so provenance,
#: freshness and adapters can never drift apart.
SOURCE_CLASSES: Dict[str, Type[SpaceDataSource]] = {
    "nasa_apod": NasaApodSource,
    "nasa_neows": NasaNeoWsSource,
    "nasa_eonet": NasaEonetSource,
    "nasa_ntrs": NasaNtrsSource,
    "jpl_sbdb": JplSbdbSource,
    "jpl_horizons": JplHorizonsSource,
    "mpc_orbits": MpcOrbitsSource,
    "mpc_observations": MpcObservationsSource,
    "nasa_exoplanet_archive": ExoplanetArchiveSource,
    "celestrak_gp": CelestrakSource,
    "esa_copernicus": CopernicusSource,
    "isro_bhoonidhi": BhoonidhiSource,
}

#: Which source is authoritative for which kind of data.
#:
#: Ordered best-first, and deliberately **per capability** — there is no single
#: winner across all data types. JPL leads on ephemerides, the MPC on
#: observations, the Exoplanet Archive on exoplanets, and CelesTrak is the only
#: entry for current satellite element sets precisely because no scientific
#: archive publishes them.
AUTHORITY_BY_CAPABILITY: Dict[Capability, List[str]] = {
    Capability.EPHEMERIS: ["jpl_horizons"],
    Capability.ORBITAL_ELEMENTS: [
        "jpl_sbdb",
        "mpc_orbits",
        "nasa_exoplanet_archive",
        "celestrak_gp",
    ],
    Capability.OBSERVATIONS: ["mpc_observations"],
    Capability.EXOPLANETS: ["nasa_exoplanet_archive"],
    Capability.PHYSICAL_PARAMETERS: [
        "jpl_sbdb",
        "nasa_exoplanet_archive",
        "nasa_neows",
    ],
    Capability.CLOSE_APPROACHES: ["jpl_sbdb", "nasa_neows"],
    Capability.NATURAL_EVENTS: ["nasa_eonet"],
    Capability.DOCUMENTS: ["nasa_ntrs"],
    Capability.EO_PRODUCTS: ["esa_copernicus", "isro_bhoonidhi"],
    Capability.MEDIA: ["nasa_apod"],
}


def get_source_class(name: str) -> Type[SpaceDataSource]:
    """Look up an adapter class by source name."""
    try:
        return SOURCE_CLASSES[name]
    except KeyError:
        raise KeyError(
            "unknown source {0!r}; registered sources are: {1}".format(
                name, ", ".join(sorted(SOURCE_CLASSES))
            )
        )


def build_source(name: str, **kwargs) -> SpaceDataSource:
    """Instantiate an adapter by name, applying environment configuration."""
    return get_source_class(name)(**kwargs)


def all_source_info() -> List[SourceInfo]:
    """Static description of every registered source. Makes no network calls."""
    return [cls().get_source_info() for cls in SOURCE_CLASSES.values()]


def sources_with_capability(capability: Capability) -> List[str]:
    """Names of every source declaring `capability`, in authority order.

    Sources not listed in `AUTHORITY_BY_CAPABILITY` are appended after the
    ranked ones, so a newly registered adapter is usable before its authority
    ranking has been agreed.
    """
    ranked = list(AUTHORITY_BY_CAPABILITY.get(capability, []))
    declared = [
        info.name for info in all_source_info() if info.supports(capability)
    ]
    ordered = [name for name in ranked if name in declared]
    ordered.extend(name for name in declared if name not in ordered)
    return ordered


def preferred_source_for(capability: Capability) -> Optional[str]:
    """The highest-authority source for `capability`, or `None`."""
    candidates = sources_with_capability(capability)
    return candidates[0] if candidates else None


def implemented_sources() -> List[str]:
    """Sources whose adapters are wired to a live endpoint."""
    return [info.name for info in all_source_info() if info.implemented]


def iter_sources(names: Optional[Iterable[str]] = None, **kwargs):
    """Yield instantiated adapters for `names`, or for every registered source."""
    for name in names if names is not None else SOURCE_CLASSES:
        yield build_source(name, **kwargs)
