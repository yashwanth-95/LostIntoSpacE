"""Turning canonical records into indexable documents."""

from .documents import (
    ENTITY_TYPE_BY_RECORD,
    FieldWeights,
    SearchDocument,
    extract_document,
)

__all__ = [
    "SearchDocument",
    "extract_document",
    "FieldWeights",
    "ENTITY_TYPE_BY_RECORD",
]
