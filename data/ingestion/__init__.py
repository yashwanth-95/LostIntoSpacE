"""Unified multi-source ingestion.

    Source -> Adapter -> Raw Record -> Parser -> Normalizer -> Validator
           -> Entity Resolution -> Provenance -> Canonical Record -> Index

One provider failing never fails the run: each source is guarded, and its
outcome is recorded in its own `SourceReport`.
"""

from .pipeline import IngestionPipeline, RecordStore, SourcePlan
from .plans import build_plans
from .report import (
    ConflictNote,
    IngestionReport,
    RejectedRecord,
    RejectionReason,
    SourceReport,
    SourceStatus,
)

__all__ = [
    "IngestionPipeline",
    "RecordStore",
    "SourcePlan",
    "build_plans",
    "IngestionReport",
    "SourceReport",
    "SourceStatus",
    "RejectedRecord",
    "RejectionReason",
    "ConflictNote",
]
