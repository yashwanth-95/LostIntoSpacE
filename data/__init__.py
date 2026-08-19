"""Data ingestion, normalization and canonical models.

Owner: P4 (AI / Search / Data / Integration).

Layering (see docs/PERSON4_DATA_ARCHITECTURE.md §1.2) — a module may only
import from layers below it:

    models / provenance / validation / normalization   (no I/O)
    sources                                            (HTTP, no persistence)
    ingestion / entity_resolution                      (orchestration)

Nothing in this package imports `apps/api/`, `simulation/` or `scientific/`.
"""

__all__ = []
