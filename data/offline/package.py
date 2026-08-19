"""The offline knowledge package.

What the product can answer with no network at all: fundamental astronomy,
rocket engineering concepts, common planets, common missions, and terminology.

**Every item carries its source and the dataset version it shipped in.** That
is the requirement, and it exists because offline data is the easiest kind to
present dishonestly: it is always available, always fast, and never obviously
out of date. A planet's mass does not change, but the *value we shipped* was
taken from a particular source at a particular time, and a user comparing it
against a live archive needs to know which.

The version is a content hash, not a hand-maintained number. A hand-maintained
version is wrong the first time someone forgets to bump it.
"""

import hashlib
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from contracts.provenance import FreshnessClass, SourceReference, SourceType

__all__ = [
    "OFFLINE_DATASET_DATE",
    "OfflineItem",
    "OfflinePackage",
    "build_offline_package",
]

#: When this dataset's values were compiled. Part of the version identity.
OFFLINE_DATASET_DATE = date(2026, 8, 19)

#: Provenance for the bundled reference values. Individual items name the
#: upstream authority they were taken from in `upstream_source`.
_BUNDLED = SourceReference(
    source_name="bundled_reference",
    source_type=SourceType.BUNDLED_REFERENCE,
    retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    attribution="Curated reference values bundled with LostIntoSpacE",
)


class OfflineItem(BaseModel):
    """One item in the offline package."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    name: str
    summary: str
    #: The upstream authority these values came from. Named per item, because
    #: "bundled_reference" says where it is stored, not where it came from.
    upstream_source: str
    detail: Dict[str, Any] = Field(default_factory=dict)
    aliases: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)

    def content_signature(self) -> str:
        """Everything that must change the package version if it changes."""
        parts = [self.id, self.kind, self.name, self.summary,
                 self.upstream_source]
        for key in sorted(self.detail):
            parts.append("{0}={1}".format(key, self.detail[key]))
        return "|".join(parts)


class OfflinePackage(BaseModel):
    """A versioned set of offline items."""

    model_config = ConfigDict(extra="forbid")

    version: str
    dataset_date: date
    items: List[OfflineItem] = Field(default_factory=list)

    @property
    def freshness_class(self) -> FreshnessClass:
        """Always STATIC. Offline data is never current by definition."""
        return FreshnessClass.STATIC

    def source_reference(self) -> SourceReference:
        """Provenance carrying the dataset version, for citation."""
        return _BUNDLED.model_copy(
            update={
                "source_version": self.version,
                "attribution": (
                    "Curated reference values bundled with LostIntoSpacE "
                    "(dataset {0}, compiled {1})".format(
                        self.version, self.dataset_date.isoformat()
                    )
                ),
            }
        )

    def get(self, item_id: str) -> Optional[OfflineItem]:
        for item in self.items:
            if item.id == item_id:
                return item
        return None

    def by_kind(self, kind: str) -> List[OfflineItem]:
        return [item for item in self.items if item.kind == kind]

    def lookup(self, name: str) -> Optional[OfflineItem]:
        """Find by name or alias, case-insensitively."""
        needle = str(name or "").strip().lower()
        if not needle:
            return None
        for item in self.items:
            if item.name.lower() == needle:
                return item
            if any(alias.lower() == needle for alias in item.aliases):
                return item
        return None

    def describe_item(self, item: OfflineItem) -> str:
        """A citable rendering, always stating source and version."""
        lines = [item.name, item.summary]
        for key in sorted(item.detail):
            lines.append("  {0}: {1}".format(key, item.detail[key]))
        lines.append(
            "  source: {0} (bundled offline dataset {1}, compiled {2})".format(
                item.upstream_source, self.version,
                self.dataset_date.isoformat(),
            )
        )
        return "\n".join(lines)


def _planet(id, name, upstream, **detail):
    return OfflineItem(
        id="offline:planet:{0}".format(id),
        kind="planet",
        name=name,
        summary=detail.pop("summary", ""),
        upstream_source=upstream,
        detail=detail,
        topics=["planets", "solar system"],
    )


def _term(id, name, summary, aliases=()):
    return OfflineItem(
        id="offline:term:{0}".format(id),
        kind="terminology",
        name=name,
        summary=summary,
        upstream_source="LostIntoSpacE editorial",
        aliases=list(aliases),
        topics=["terminology"],
    )


def _fundamental(id, name, summary, upstream, **detail):
    return OfflineItem(
        id="offline:astronomy:{0}".format(id),
        kind="astronomy",
        name=name,
        summary=summary,
        upstream_source=upstream,
        detail=detail,
        topics=["astronomy", "fundamentals"],
    )


def _items() -> List[OfflineItem]:
    """The offline content.

    Planetary values are the IAU/NASA published figures — widely agreed and
    stable to far more precision than this product needs. Each names its
    upstream authority so a user can check it.
    """
    return [
        # -- common planets -----------------------------------------------
        _planet("mercury", "Mercury", "NASA planetary fact sheet",
                summary="The smallest planet and the closest to the Sun.",
                mass_kg="3.301e23", equatorial_radius_km=2440.5,
                orbital_period_days=88.0, moons=0),
        _planet("venus", "Venus", "NASA planetary fact sheet",
                summary="Similar in size to Earth, with a dense carbon-dioxide "
                        "atmosphere and a runaway greenhouse effect.",
                mass_kg="4.867e24", equatorial_radius_km=6051.8,
                orbital_period_days=224.7, moons=0),
        _planet("earth", "Earth", "NASA planetary fact sheet",
                summary="The only planet known to support life.",
                mass_kg="5.972e24", equatorial_radius_km=6378.1,
                orbital_period_days=365.25, moons=1),
        _planet("mars", "Mars", "NASA planetary fact sheet",
                summary="A cold desert world with a thin atmosphere, the most "
                        "visited planet after Earth.",
                mass_kg="6.417e23", equatorial_radius_km=3396.2,
                orbital_period_days=687.0, moons=2),
        _planet("jupiter", "Jupiter", "NASA planetary fact sheet",
                summary="The largest planet, a gas giant with a strong magnetic "
                        "field and dozens of moons.",
                mass_kg="1.898e27", equatorial_radius_km=71492.0,
                orbital_period_days=4331.0, moons=95),
        _planet("saturn", "Saturn", "NASA planetary fact sheet",
                summary="A gas giant best known for its extensive ring system.",
                mass_kg="5.683e26", equatorial_radius_km=60268.0,
                orbital_period_days=10747.0, moons=146),
        _planet("uranus", "Uranus", "NASA planetary fact sheet",
                summary="An ice giant that rotates on its side, visited only by "
                        "Voyager 2.",
                mass_kg="8.681e25", equatorial_radius_km=25559.0,
                orbital_period_days=30589.0, moons=28),
        _planet("neptune", "Neptune", "NASA planetary fact sheet",
                summary="The outermost planet, with the fastest winds in the "
                        "Solar System.",
                mass_kg="1.024e26", equatorial_radius_km=24764.0,
                orbital_period_days=59800.0, moons=16),

        # -- fundamental astronomy ----------------------------------------
        _fundamental(
            "astronomical-unit", "Astronomical unit",
            "The defined mean Earth-Sun distance, used as the base unit of "
            "distance within the Solar System.",
            "IAU 2012 definition", value_m="1.495978707e11", symbol="au",
        ),
        _fundamental(
            "light-year", "Light-year",
            "The distance light travels in one Julian year.",
            "IAU definition", value_m="9.4607304725808e15", symbol="ly",
        ),
        _fundamental(
            "standard-gravity", "Standard gravity",
            "The conventional value of gravitational acceleration at Earth's "
            "surface, used in the definition of specific impulse.",
            "CGPM 1901 definition", value_ms2=9.80665, symbol="g0",
        ),
        _fundamental(
            "gravitational-constant", "Gravitational constant",
            "The constant of proportionality in Newton's law of gravitation.",
            "CODATA 2018", value="6.67430e-11 m^3 kg^-1 s^-2", symbol="G",
        ),
        _fundamental(
            "solar-mass", "Solar mass",
            "The mass of the Sun, the standard unit for stellar masses.",
            "IAU nominal value", value_kg="1.98892e30", symbol="M_sun",
        ),
        _fundamental(
            "escape-velocity-earth", "Earth escape velocity",
            "The speed needed at Earth's surface to escape its gravity, "
            "ignoring atmospheric drag.",
            "NASA planetary fact sheet", value_ms=11186.0,
        ),
        _fundamental(
            "orbital-velocity-leo", "Low Earth orbit velocity",
            "The approximate orbital speed at a few hundred kilometres "
            "altitude.",
            "Derived from the vis-viva equation", value_ms="~7800",
        ),

        # -- terminology ---------------------------------------------------
        _term("apogee", "Apogee",
              "The point in an Earth orbit farthest from Earth.",
              ["apoapsis (Earth)"]),
        _term("perigee", "Perigee",
              "The point in an Earth orbit closest to Earth.",
              ["periapsis (Earth)"]),
        _term("apoapsis", "Apoapsis",
              "The point in any orbit farthest from the body being orbited."),
        _term("periapsis", "Periapsis",
              "The point in any orbit closest to the body being orbited."),
        _term("epoch", "Epoch",
              "The reference time at which a set of orbital elements is "
              "valid. Elements describe the orbit at their epoch, not now."),
        _term("delta-v", "Delta-v",
              "The change in velocity a manoeuvre requires, and the standard "
              "currency of mission planning.", ["dv", "delta v"]),
        _term("twr", "Thrust-to-weight ratio",
              "Thrust divided by weight. A launch vehicle needs a ratio above "
              "1.0 at lift-off to leave the pad.", ["thrust to weight"]),
        _term("staging", "Staging",
              "Discarding spent structure during flight so the remaining "
              "engines no longer accelerate empty tanks."),
        _term("isp", "Specific impulse",
              "A measure of propellant efficiency: thrust per unit of "
              "propellant consumed per second.", ["Isp"]),
        _term("mach", "Mach number",
              "Speed divided by the local speed of sound."),
        _term("norad-id", "NORAD catalog number",
              "A unique number assigned to each tracked object in Earth "
              "orbit.", ["NORAD ID", "catalog number", "satellite number"]),
        _term("tle", "Two-line element set",
              "A compact format for satellite orbital elements, valid near "
              "its epoch and intended for use with the SGP4 model.",
              ["TLE", "two line element"]),
        _term("ephemeris", "Ephemeris",
              "A table or calculation of an object's position over time."),
        _term("albedo", "Albedo",
              "The fraction of incident light a surface reflects."),
        _term("regolith", "Regolith",
              "The layer of loose material covering solid rock on a planet, "
              "moon or asteroid."),
    ]


def _compute_version(items: Sequence[OfflineItem], dataset_date: date) -> str:
    """A content hash, so the version cannot drift from the content.

    A hand-maintained version number is wrong the first time someone edits a
    value and forgets to bump it — and a wrong version is worse than none,
    because it is trusted.
    """
    digest = hashlib.sha256()
    digest.update(dataset_date.isoformat().encode("utf-8"))
    for item in sorted(items, key=lambda entry: entry.id):
        digest.update(item.content_signature().encode("utf-8"))
        digest.update(b"\x1f")
    return "offline-{0}-{1}".format(
        dataset_date.strftime("%Y%m%d"), digest.hexdigest()[:12]
    )


def build_offline_package() -> OfflinePackage:
    """Build the offline package, with a version derived from its content."""
    items = _items()
    return OfflinePackage(
        version=_compute_version(items, OFFLINE_DATASET_DATE),
        dataset_date=OFFLINE_DATASET_DATE,
        items=items,
    )
