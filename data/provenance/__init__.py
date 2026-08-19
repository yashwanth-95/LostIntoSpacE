"""Provenance, freshness and lineage.

Implements Architecture principle #4 (Data Provenance): every data point traces
to its source, and every derived value traces to the values it came from.

* `SourceReference` itself lives in `packages/contracts/` — it crosses team
  boundaries — and is re-exported here for convenience.
* `freshness` decides what may be called current.
* `lineage` records how a value got to be what it is.
* `attribution` renders both into citations.
"""

from contracts.provenance import FreshnessClass, SourceReference, SourceType

from .attribution import (
    Citation,
    attribution_block,
    build_citation,
    collect_citations,
    freshness_caveat,
)
from .freshness import (
    DEFAULT_POLICY,
    POLICIES,
    FreshnessAssessment,
    FreshnessPolicy,
    SourceCategory,
    apply_freshness,
    assess_freshness,
    policy_for,
)
from .lineage import (
    DataLineage,
    LineageBuilder,
    LineageStep,
    ProvenanceError,
    TransformationType,
    derive_quantity,
    require_provenance,
)

__all__ = [
    "SourceReference",
    "SourceType",
    "FreshnessClass",
    "SourceCategory",
    "FreshnessPolicy",
    "FreshnessAssessment",
    "assess_freshness",
    "apply_freshness",
    "policy_for",
    "POLICIES",
    "DEFAULT_POLICY",
    "TransformationType",
    "LineageStep",
    "DataLineage",
    "LineageBuilder",
    "ProvenanceError",
    "require_provenance",
    "derive_quantity",
    "Citation",
    "build_citation",
    "collect_citations",
    "attribution_block",
    "freshness_caveat",
]
