"""The platform catalog.

Reference content for the product: space objects, launch sites, verified
imagery, science topics, experiments, reference missions and the asset library.

This is deliberately separate from `data/models/`, which holds the canonical
archive-grade record types that ingestion and validation work against. These
records are shaped for the interface — an ordered list of properties, an image,
the missions that went there — and they can change as screens change without
disturbing anything upstream.

Everything here is loaded into PostgreSQL by `database/seeds/` and served from
there. These modules stay the authoring source of truth, which is what keeps
the platform populated on an install whose database has not been seeded yet.
"""

from .assets import assets_by_id, build_assets
from .experiments import build_experiments, experiments_by_id
from .imagery import IMAGERY, image_for
from .launch_sites import build_launch_sites, launch_sites_by_id, rotation_bonus_ms
from .models import (
    AssetRecord,
    CatalogObject,
    Experiment,
    LaunchSiteRecord,
    ObjectKind,
    ReferenceMission,
    ScienceTopic,
)
from .reference_missions import build_reference_missions, reference_missions_by_id
from .science import STRANDS, build_science_topics, science_topics_by_slug
from .space_objects import build_space_objects, space_objects_by_id

__all__ = [
    "AssetRecord",
    "CatalogObject",
    "Experiment",
    "LaunchSiteRecord",
    "ObjectKind",
    "ReferenceMission",
    "ScienceTopic",
    "STRANDS",
    "IMAGERY",
    "image_for",
    "build_space_objects",
    "space_objects_by_id",
    "build_launch_sites",
    "launch_sites_by_id",
    "rotation_bonus_ms",
    "build_science_topics",
    "science_topics_by_slug",
    "build_experiments",
    "experiments_by_id",
    "build_reference_missions",
    "reference_missions_by_id",
    "build_assets",
    "assets_by_id",
]
