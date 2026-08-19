"""Cross-source identity resolution.

Identity is established from **strong identifiers** — the ones archives assign
and do not reuse — rather than from names. Names are ambiguous ("Europa" is a
moon and an asteroid), and a name collision that silently merges two objects is
far worse than a duplicate that a human can spot.

Strong identifiers, in descending order of trust:

1. `spk_id`      — JPL SPK-ID, unique across small bodies
2. `norad_cat_id`— NORAD catalog number, unique across artificial satellites
3. `packed_designation` / `designation` — MPC designations, after normalization
4. `product_id`  — provider-assigned EO product id

Names and aliases are used only to *propose* a match, never to confirm one on
their own. A name-only match is recorded as a candidate for review.
"""

import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from ..models.base import slugify

__all__ = [
    "IdentityKey",
    "MergeDecision",
    "ResolutionOutcome",
    "EntityResolver",
    "normalize_designation",
]

#: Fields that carry a strong identifier, and the namespace each belongs to.
#: The namespace prevents a NORAD number colliding with an asteroid number.
_STRONG_FIELDS = (
    ("spk_id", "spk"),
    ("norad_cat_id", "norad"),
    ("packed_designation", "packed"),
    ("product_id", "product"),
)

_DESIGNATION_CLEAN = re.compile(r"[\s_]+")


def normalize_designation(value: Any) -> Optional[str]:
    """Canonicalize a designation for comparison.

    ``"2024 YR4"``, ``"2024YR4"`` and ``"2024_yr4"`` all normalize to
    ``"2024yr4"``. Case and internal spacing vary between archives for the same
    object, and comparing raw strings would miss real matches.
    """
    if value is None:
        return None
    text = _DESIGNATION_CLEAN.sub("", str(value).strip().lower())
    return text or None


class MergeDecision(str, Enum):
    """What the resolver concluded about a record."""

    #: No existing entity matched; a new canonical id was assigned.
    NEW = "NEW"
    #: A strong identifier matched an existing entity.
    MERGED = "MERGED"
    #: Only names matched. Kept separate, flagged for review.
    CANDIDATE = "CANDIDATE"
    #: Strong identifiers matched two *different* existing entities.
    CONFLICT = "CONFLICT"


class IdentityKey(BaseModel):
    """One strong identifier, namespaced by the kind of identifier it is."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    namespace: str
    value: str

    def __str__(self) -> str:
        return "{0}:{1}".format(self.namespace, self.value)


class ResolutionOutcome(BaseModel):
    """The result of resolving one record against the registry."""

    model_config = ConfigDict(extra="forbid")

    canonical_id: str
    decision: MergeDecision
    #: Strong keys extracted from the record.
    keys: List[IdentityKey] = Field(default_factory=list)
    #: The canonical id the record was merged into, when it was merged.
    merged_into: Optional[str] = None
    #: Other canonical ids that also matched. Non-empty means a conflict.
    conflicting_ids: List[str] = Field(default_factory=list)
    #: Human-readable justification, recorded in lineage.
    reason: str = ""

    @property
    def is_conflict(self) -> bool:
        return self.decision is MergeDecision.CONFLICT


class EntityResolver:
    """Maps `(source, source_record_id)` and strong identifiers to canonical ids.

    In-memory for now. The interface is the part that matters: when P2's
    database exists, the same calls back onto a table without callers changing.
    """

    def __init__(self):
        #: strong key -> canonical id
        self._keys: Dict[str, str] = {}
        #: normalized name -> set of canonical ids that use it
        self._names: Dict[str, Set[str]] = {}
        #: canonical id -> every strong key it owns
        self._owned: Dict[str, Set[str]] = {}
        #: (source_name, source_record_id) -> canonical id
        self._source_records: Dict[Tuple[str, str], str] = {}

    # -- extraction --------------------------------------------------------
    def extract_keys(self, record) -> List[IdentityKey]:
        """Strong identifiers present on a canonical record."""
        keys: List[IdentityKey] = []
        for field, namespace in _STRONG_FIELDS:
            value = getattr(record, field, None)
            if value in (None, ""):
                continue
            normalized = normalize_designation(value)
            if normalized:
                keys.append(IdentityKey(namespace=namespace, value=normalized))

        #: A bare `designation` is strong only for small bodies, where archives
        #: agree on the IAU form. It is namespaced by object type so an
        #: asteroid's "1" cannot match a satellite's "1".
        designation = getattr(record, "designation", None)
        object_type = getattr(record, "object_type", None)
        if designation and object_type is not None:
            normalized = normalize_designation(designation)
            if normalized:
                keys.append(
                    IdentityKey(
                        namespace="desig-{0}".format(str(object_type.value).lower()),
                        value=normalized,
                    )
                )
        return keys

    def _name_keys(self, record) -> List[str]:
        names = []
        for name in getattr(record, "all_names", lambda: [])():
            slug = normalize_designation(name)
            if slug:
                names.append(slug)
        return names

    # -- resolution --------------------------------------------------------
    def resolve(self, record, source_name: Optional[str] = None,
                source_record_id: Optional[str] = None) -> ResolutionOutcome:
        """Decide which canonical entity `record` belongs to.

        Does not mutate the record. Callers apply the outcome, which keeps the
        decision auditable and reversible.
        """
        keys = self.extract_keys(record)
        matches = {self._keys[str(key)] for key in keys if str(key) in self._keys}

        if len(matches) > 1:
            # Two archives assert identifiers that point at different entities.
            # Refusing to choose is correct: this needs a human or a rule, not
            # a coin toss.
            return ResolutionOutcome(
                canonical_id=record.canonical_id,
                decision=MergeDecision.CONFLICT,
                keys=keys,
                conflicting_ids=sorted(matches),
                reason=(
                    "strong identifiers {0} match {1} different existing entities: "
                    "{2}".format(
                        [str(key) for key in keys], len(matches), sorted(matches)
                    )
                ),
            )

        if len(matches) == 1:
            existing = matches.pop()
            return ResolutionOutcome(
                canonical_id=existing,
                decision=MergeDecision.MERGED,
                keys=keys,
                merged_into=existing,
                reason="strong identifier match on {0}".format(
                    ", ".join(
                        str(key) for key in keys if str(key) in self._keys
                    )
                ),
            )

        # No strong match. A name match is a hint, not a decision.
        name_matches: Set[str] = set()
        for name in self._name_keys(record):
            name_matches.update(self._names.get(name, set()))
        name_matches.discard(record.canonical_id)

        if name_matches:
            return ResolutionOutcome(
                canonical_id=record.canonical_id,
                decision=MergeDecision.CANDIDATE,
                keys=keys,
                conflicting_ids=sorted(name_matches),
                reason=(
                    "name matches {0} but no strong identifier does; kept separate "
                    "for review".format(sorted(name_matches))
                ),
            )

        return ResolutionOutcome(
            canonical_id=record.canonical_id,
            decision=MergeDecision.NEW,
            keys=keys,
            reason="no existing entity matched",
        )

    def register(self, record, outcome: ResolutionOutcome,
                 source_name: Optional[str] = None,
                 source_record_id: Optional[str] = None) -> None:
        """Record an accepted resolution so later records can match it."""
        canonical_id = outcome.canonical_id
        owned = self._owned.setdefault(canonical_id, set())
        for key in outcome.keys:
            text = str(key)
            self._keys[text] = canonical_id
            owned.add(text)
        for name in self._name_keys(record):
            self._names.setdefault(name, set()).add(canonical_id)
        if source_name and source_record_id:
            self._source_records[(source_name, str(source_record_id))] = canonical_id

    def canonical_id_for(self, source_name: str, source_record_id: str) -> Optional[str]:
        """The canonical id a given source record was resolved to, if any."""
        return self._source_records.get((source_name, str(source_record_id)))

    def keys_for(self, canonical_id: str) -> List[str]:
        return sorted(self._owned.get(canonical_id, set()))

    @property
    def entity_count(self) -> int:
        return len(self._owned)

    def aliases_for(self, canonical_id: str) -> List[str]:
        """Every normalized name pointing at this entity."""
        return sorted(
            name for name, ids in self._names.items() if canonical_id in ids
        )
