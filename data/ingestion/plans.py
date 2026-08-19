"""Ready-made ingestion plans, one per implemented source.

Each plan pairs a fetch strategy with the matching normalizer. They are ordinary
values, so a run can take all of them, a subset, or a caller's own.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence

from contracts._time import utc_now

from ..normalization.celestrak import normalize_gp_record
from ..normalization.esa import normalize_copernicus_product
from ..normalization.exoplanet import normalize_exoplanet_row
from ..normalization.isro import normalize_bhoonidhi_item
from ..normalization.jpl import normalize_sbdb_object
from ..normalization.mpc import normalize_mpc_observations, normalize_mpc_orbit
from ..normalization.nasa import (
    normalize_eonet_event,
    normalize_neows_object,
    normalize_ntrs_citation,
)
from ..sources.base import SourceQuery
from .pipeline import SourcePlan

__all__ = ["build_plans", "PLAN_BUILDERS"]


def _small_body_plan(source_name, designations, normalize):
    async def fetch(source):
        records = []
        for designation in designations:
            record = await source.fetch_by_id(designation)
            if record is not None:
                records.append(record)
        return records

    return SourcePlan(source_name=source_name, fetch=fetch, normalize=normalize)


def build_plans(
    small_bodies: Optional[Sequence[str]] = None,
    satellites: Optional[Sequence[str]] = None,
    exoplanets: Optional[Sequence[str]] = None,
    document_queries: Optional[Sequence[str]] = None,
    enabled: Optional[Sequence[str]] = None,
    bhoonidhi_authorized: bool = False,
) -> List[SourcePlan]:
    """Build a plan per source for a given ingestion scope.

    Scope is explicit rather than "everything": several providers ask users to
    retrieve only what they need, and an unbounded crawl would violate that.
    """
    small_bodies = list(small_bodies or ["Ceres", "Bennu"])
    satellites = list(satellites or ["25544"])
    exoplanets = list(exoplanets or ["Kepler-22 b"])
    document_queries = list(document_queries or ["max-q launch vehicle"])

    plans: List[SourcePlan] = []

    # -- JPL SBDB: primary small-body authority ---------------------------
    plans.append(
        _small_body_plan("jpl_sbdb", small_bodies, normalize_sbdb_object)
    )

    # -- MPC orbits: second authority, for covariance ----------------------
    plans.append(_small_body_plan("mpc_orbits", small_bodies, normalize_mpc_orbit))

    # -- MPC observations --------------------------------------------------
    plans.append(
        _small_body_plan(
            "mpc_observations", small_bodies, normalize_mpc_observations
        )
    )

    # -- NASA NeoWs --------------------------------------------------------
    async def fetch_neows(source):
        records = []
        for identifier in ("2000433",):
            record = await source.fetch_by_id(identifier)
            if record is not None:
                records.append(record)
        return records

    plans.append(
        SourcePlan(
            source_name="nasa_neows",
            fetch=fetch_neows,
            normalize=normalize_neows_object,
        )
    )

    # -- NASA EONET --------------------------------------------------------
    async def fetch_eonet(source):
        page = await source.search(SourceQuery(extra={"status": "open"}, limit=25))
        return page.records

    plans.append(
        SourcePlan(
            source_name="nasa_eonet",
            fetch=fetch_eonet,
            normalize=normalize_eonet_event,
        )
    )

    # -- NASA NTRS ---------------------------------------------------------
    async def fetch_ntrs(source):
        records = []
        for query in document_queries:
            page = await source.search(SourceQuery(text=query, limit=10))
            records.extend(page.records)
        return records

    plans.append(
        SourcePlan(
            source_name="nasa_ntrs",
            fetch=fetch_ntrs,
            normalize=normalize_ntrs_citation,
        )
    )

    # -- Exoplanet Archive -------------------------------------------------
    async def fetch_exoplanets(source):
        records = []
        for name in exoplanets:
            record = await source.fetch_by_id(name)
            if record is not None:
                records.append(record)
        return records

    plans.append(
        SourcePlan(
            source_name="nasa_exoplanet_archive",
            fetch=fetch_exoplanets,
            normalize=normalize_exoplanet_row,
        )
    )

    # -- CelesTrak ---------------------------------------------------------
    async def fetch_celestrak(source):
        records = []
        for catalog_number in satellites:
            record = await source.fetch_by_id(catalog_number)
            if record is not None:
                records.append(record)
        return records

    plans.append(
        SourcePlan(
            source_name="celestrak_gp",
            fetch=fetch_celestrak,
            normalize=normalize_gp_record,
        )
    )

    # -- Copernicus --------------------------------------------------------
    async def fetch_copernicus(source):
        page = await source.search(
            SourceQuery(
                extra={"collection": "SENTINEL-2"},
                start_time=utc_now() - timedelta(days=7),
                limit=10,
            )
        )
        return page.records

    plans.append(
        SourcePlan(
            source_name="esa_copernicus",
            fetch=fetch_copernicus,
            normalize=normalize_copernicus_product,
        )
    )

    # -- Bhoonidhi: only when authorized -----------------------------------
    async def fetch_bhoonidhi(source):
        page = await source.search(
            SourceQuery(extra={"collections": "NISAR-S-RSLC"}, limit=10)
        )
        return page.records

    plans.append(
        SourcePlan(
            source_name="isro_bhoonidhi",
            fetch=fetch_bhoonidhi,
            normalize=normalize_bhoonidhi_item,
            enabled=bhoonidhi_authorized,
            skip_reason=(
                None
                if bhoonidhi_authorized
                else "no Bhoonidhi credentials configured; access is granted on "
                "request from bhoonidhi@nrsc.gov.in"
            ),
        )
    )

    if enabled is not None:
        allowed = set(enabled)
        plans = [plan for plan in plans if plan.source_name in allowed]
    return plans


#: Exposed so callers can compose their own scope without rebuilding everything.
PLAN_BUILDERS = {"build_plans": build_plans}
