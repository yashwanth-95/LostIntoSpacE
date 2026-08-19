"""Seed data.

Curated content the product needs but no archive supplies: engineering concepts,
lessons, and a small reference mission catalogue. All of it is
`SourceType.EDITORIAL` or `BUNDLED_REFERENCE`, so it can never be confused with
ingested archive data.
"""

from .concepts import CONCEPT_SLUGS, EDITORIAL_SOURCE, build_concepts
from .missions import MISSION_SLUGS, build_missions

__all__ = [
    "build_concepts",
    "CONCEPT_SLUGS",
    "EDITORIAL_SOURCE",
    "build_missions",
    "MISSION_SLUGS",
]
