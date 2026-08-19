"""Configurable source authority.

**There is no single winner.** JPL leads on ephemerides, the MPC on asteroid
observations and orbit covariance, the Exoplanet Archive on exoplanet
parameters, CelesTrak on current satellite element sets. Hard-coding one global
ranking would be wrong for most fields, so authority is configured per field
pattern and falls back to a documented default order.

Everything here is data, not code: a deployment can reorder authority without
touching the engine.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["AuthorityPolicy", "DEFAULT_AUTHORITY", "FIELD_AUTHORITY"]

#: Per-field-prefix authority, best first. The longest matching prefix wins, so
#: a specific rule beats a general one.
FIELD_AUTHORITY: Dict[str, Tuple[str, ...]] = {
    # -- orbits ----------------------------------------------------------
    #: Element values: JPL's solution is the reference; the MPC is the check.
    "orbits.elements": ("jpl_sbdb", "mpc_orbits", "nasa_neows"),
    #: Covariance: the MPC publishes it most completely for minor planets.
    "orbits.covariance": ("mpc_orbits", "jpl_sbdb"),
    #: Fit quality metadata.
    "orbits.fit": ("jpl_sbdb", "mpc_orbits"),
    #: Anything else about an orbit.
    "orbits": ("jpl_sbdb", "mpc_orbits", "nasa_neows", "celestrak_gp"),

    # -- ephemerides -----------------------------------------------------
    "states": ("jpl_horizons",),
    "ephemeris": ("jpl_horizons",),

    # -- physical parameters ---------------------------------------------
    "physical": ("jpl_sbdb", "nasa_exoplanet_archive", "nasa_neows", "bundled_reference"),
    #: Exoplanet radii and masses come from the archive, not from small-body data.
    "physical.radius_mean": ("nasa_exoplanet_archive", "jpl_sbdb"),

    # -- observations ----------------------------------------------------
    "observation": ("mpc_observations",),

    # -- catalogues ------------------------------------------------------
    "eo_product": ("esa_copernicus", "isro_bhoonidhi"),
    "document": ("nasa_ntrs",),
    "event": ("nasa_eonet",),
}

#: Used when no field rule matches. Ordered by source type: scientific archives,
#: then literature, then agency APIs, then operational feeds, then bundled data,
#: and finally anything this project calculated.
DEFAULT_AUTHORITY: Tuple[str, ...] = (
    "jpl_horizons",
    "jpl_sbdb",
    "mpc_orbits",
    "mpc_observations",
    "nasa_exoplanet_archive",
    "nasa_ntrs",
    "nasa_neows",
    "nasa_eonet",
    "nasa_apod",
    "esa_copernicus",
    "isro_bhoonidhi",
    "celestrak_gp",
    "bundled_reference",
    "derived",
)


class AuthorityPolicy(BaseModel):
    """Which source wins, per field.

    Construct with overrides to change the ranking for a deployment; the
    defaults above are a starting point, not a fixed rule.
    """

    model_config = ConfigDict(extra="forbid")

    field_authority: Dict[str, Tuple[str, ...]] = Field(
        default_factory=lambda: dict(FIELD_AUTHORITY)
    )
    default_order: Tuple[str, ...] = DEFAULT_AUTHORITY
    #: Sources not listed anywhere rank after every listed source rather than
    #: being refused: a newly added adapter stays usable before its ranking is
    #: agreed.
    unknown_source_rank: int = 10_000

    def order_for(self, field: Optional[str]) -> Tuple[str, ...]:
        """The authority order that applies to `field`.

        Longest matching prefix wins, so `orbits.covariance` uses the covariance
        rule rather than the general `orbits` one.
        """
        if not field:
            return self.default_order
        best: Optional[str] = None
        for prefix in self.field_authority:
            if field == prefix or field.startswith(prefix + "."):
                if best is None or len(prefix) > len(best):
                    best = prefix
        if best is not None:
            return self.field_authority[best]
        return self.default_order

    def rank(self, source_name: str, field: Optional[str] = None) -> int:
        """Position of `source_name` for `field`. Lower is more authoritative."""
        order = self.order_for(field)
        if source_name in order:
            return order.index(source_name)
        #: Not in the field-specific list — fall back to the global order, but
        #: always behind everything the field rule named.
        if source_name in self.default_order:
            return len(order) + self.default_order.index(source_name)
        return self.unknown_source_rank

    def preferred(
        self, sources: Sequence[str], field: Optional[str] = None
    ) -> Optional[str]:
        """The most authoritative of `sources` for `field`."""
        candidates = [name for name in sources if name]
        if not candidates:
            return None
        return sorted(candidates, key=lambda name: (self.rank(name, field), name))[0]

    def outranks(self, first: str, second: str, field: Optional[str] = None) -> bool:
        return self.rank(first, field) < self.rank(second, field)

    def explain(self, sources: Sequence[str], field: Optional[str] = None) -> str:
        """Why one source was preferred. Recorded in conflict resolutions."""
        winner = self.preferred(sources, field)
        order = self.order_for(field)
        return (
            "preferred {0} for {1!r}; authority order for this field is {2}".format(
                winner, field or "<default>", list(order)
            )
        )
