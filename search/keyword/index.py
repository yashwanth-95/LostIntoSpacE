"""The keyword index.

An in-memory inverted index with field weighting, prefix matching and metadata
filters. It is deliberately simple and explainable: every result can say which
fields matched and why it scored what it did.

**Adding records requires no code change.** `add_record` extracts a document
generically, so a record type the index has never seen becomes searchable as
soon as it is ingested. That is the "live data" requirement of Task 15.

The Postgres full-text implementation the project plans for MVP would replace
the storage here, not the interface: `KeywordIndex.search` takes a `SearchQuery`
and returns a `SearchResponse`, which is what the API layer calls.
"""

import bisect
import math
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from contracts.search import (
    MatchType,
    SearchEntityType,
    SearchFacet,
    SearchQuery,
    SearchResponse,
    SearchResult,
    SearchStatus,
    SortOrder,
)

from ..indexing.documents import DEFAULT_WEIGHTS, FieldWeights, SearchDocument, extract_document

__all__ = ["KeywordIndex", "MATCH_TYPE_BOOST"]

#: Multiplier applied by how the match was made. Exact identity beats a body
#: mention by a wide margin, because it almost always is what the user meant.
MATCH_TYPE_BOOST = {
    MatchType.EXACT: 4.0,
    MatchType.ALIAS: 2.5,
    MatchType.PREFIX: 1.4,
    MatchType.PARTIAL: 1.0,
}

#: Score below which a text query is treated as having found nothing reliable.
#: Tuned so a single weak body-token match does not become an answer.
DEFAULT_RELIABILITY_FLOOR = 0.12


class KeywordIndex:
    """Inverted index over `SearchDocument`s."""

    def __init__(
        self,
        weights: FieldWeights = DEFAULT_WEIGHTS,
        reliability_floor: float = DEFAULT_RELIABILITY_FLOOR,
    ):
        self.weights = weights
        self.reliability_floor = reliability_floor
        self._documents: Dict[str, SearchDocument] = {}
        #: token -> {document id -> {field -> count}}
        self._postings: Dict[str, Dict[str, Dict[str, int]]] = {}
        #: Sorted token list, for prefix lookup by binary search.
        self._sorted_tokens: List[str] = []
        self._tokens_dirty = False
        #: Normalized title/alias/identifier -> document ids, for exact hits.
        self._exact: Dict[str, Set[str]] = {}
        self._alias_exact: Dict[str, Set[str]] = {}

    # -- building ---------------------------------------------------------
    def add_record(self, record) -> SearchDocument:
        """Index any canonical record. No per-type wiring needed."""
        document = extract_document(record, self.weights)
        self.add_document(document)
        return document

    def add_records(self, records: Iterable[Any]) -> int:
        count = 0
        for record in records:
            self.add_record(record)
            count += 1
        return count

    def add_document(self, document: SearchDocument) -> None:
        from .tokenizer import normalize, tokenize

        if document.id in self._documents:
            self.remove(document.id)
        self._documents[document.id] = document

        for field, text in document.fields.items():
            for token in tokenize(text):
                postings = self._postings.setdefault(token, {})
                fields = postings.setdefault(document.id, {})
                fields[field] = fields.get(field, 0) + 1

        self._exact.setdefault(normalize(document.title), set()).add(document.id)
        for identifier in document.identifiers:
            self._exact.setdefault(normalize(identifier), set()).add(document.id)
        for alias in document.aliases:
            self._alias_exact.setdefault(normalize(alias), set()).add(document.id)

        self._tokens_dirty = True

    def remove(self, document_id: str) -> bool:
        """Remove a document. Returns True when something was removed."""
        document = self._documents.pop(document_id, None)
        if document is None:
            return False
        for token in list(self._postings):
            postings = self._postings[token]
            postings.pop(document_id, None)
            if not postings:
                del self._postings[token]
        for mapping in (self._exact, self._alias_exact):
            for key in list(mapping):
                mapping[key].discard(document_id)
                if not mapping[key]:
                    del mapping[key]
        self._tokens_dirty = True
        return True

    def get(self, document_id: str) -> Optional[SearchDocument]:
        return self._documents.get(document_id)

    def documents(self) -> List[SearchDocument]:
        return list(self._documents.values())

    def __len__(self) -> int:
        return len(self._documents)

    # -- lookup -----------------------------------------------------------
    def _tokens(self) -> List[str]:
        if self._tokens_dirty:
            self._sorted_tokens = sorted(self._postings)
            self._tokens_dirty = False
        return self._sorted_tokens

    def _prefix_matches(self, prefix: str, limit: int = 50) -> List[str]:
        """Index tokens starting with `prefix`, via binary search."""
        tokens = self._tokens()
        start = bisect.bisect_left(tokens, prefix)
        found: List[str] = []
        for token in tokens[start:]:
            if not token.startswith(prefix):
                break
            found.append(token)
            if len(found) >= limit:
                break
        return found

    # -- scoring ----------------------------------------------------------
    def _idf(self, token: str) -> float:
        """Inverse document frequency for `token`.

        A rare term is strong evidence; a term in most documents is weak. The
        `+1`/`+0.5` smoothing keeps the value above 1 even on a tiny corpus, so
        a match never scores *worse* for being in a small index.
        """
        document_frequency = len(self._postings.get(token, {}))
        if document_frequency == 0:
            return 1.0
        total = max(1, len(self._documents))
        return 1.0 + math.log((total + 1.0) / (document_frequency + 0.5))

    def _score_document(
        self, document_id: str, query_tokens: Sequence[str], phrase: str
    ) -> Tuple[float, MatchType, List[str], bool]:
        """Score one document, and say how and where it matched.

        Returns `(score, match_type, matched_fields, had_exact_token)`. The last
        value drives the reliability decision: an exact token match is real
        evidence even when the score is low, while a prefix-only match is not.
        """
        from .tokenizer import normalize

        document = self._documents[document_id]
        raw = 0.0
        matched_fields: Set[str] = set()
        match_type = MatchType.PARTIAL
        had_exact_token = False

        #: Exact title or identifier match dominates everything else.
        if document_id in self._exact.get(phrase, set()):
            raw += self.weights.title * MATCH_TYPE_BOOST[MatchType.EXACT] * 3.0
            matched_fields.add("title")
            match_type = MatchType.EXACT
        elif document_id in self._alias_exact.get(phrase, set()):
            raw += self.weights.aliases * MATCH_TYPE_BOOST[MatchType.ALIAS] * 3.0
            matched_fields.add("aliases")
            match_type = MatchType.ALIAS

        matched_tokens = 0
        for token in query_tokens:
            postings = self._postings.get(token, {})
            fields = postings.get(document_id)
            if fields:
                matched_tokens += 1
                had_exact_token = True
                idf = self._idf(token)
                for field, count in fields.items():
                    weight = self.weights.weight(field)
                    #: Sub-linear in count: a word repeated ten times is not ten
                    #: times more relevant.
                    raw += weight * idf * (1.0 + math.log(count))
                    matched_fields.add(field)
                if match_type is MatchType.PARTIAL and (
                    "title" in fields or "identifiers" in fields
                ):
                    match_type = MatchType.EXACT if len(query_tokens) == 1 else (
                        MatchType.PARTIAL
                    )
                continue

            #: No exact token — try a prefix match, scored lower.
            for candidate in self._prefix_matches(token):
                candidate_fields = self._postings.get(candidate, {}).get(document_id)
                if not candidate_fields:
                    continue
                matched_tokens += 1
                idf = self._idf(candidate)
                for field, count in candidate_fields.items():
                    raw += (
                        self.weights.weight(field)
                        * idf
                        * MATCH_TYPE_BOOST[MatchType.PREFIX]
                        * 0.5
                        * (1.0 + math.log(count))
                    )
                    matched_fields.add(field)
                if match_type is MatchType.PARTIAL:
                    match_type = MatchType.PREFIX
                break

        if raw <= 0.0:
            return (0.0, match_type, [], False)

        #: Reward covering more of the query: a document matching every term is
        #: much more likely to be the intended answer than one matching a third.
        coverage = matched_tokens / float(max(1, len(query_tokens)))
        raw *= 0.4 + 0.6 * coverage

        #: Squash into 0..1, with the half-way constant scaled to the length of
        #: the query. A fixed constant would make single-word queries score
        #: systematically lower than multi-word ones for no good reason.
        half = 4.0 + 3.0 * len(query_tokens)
        score = raw / (raw + half)
        return (score, match_type, sorted(matched_fields), had_exact_token)

    # -- filtering --------------------------------------------------------
    def _passes_filters(self, document: SearchDocument, query: SearchQuery) -> bool:
        if query.entity_types and document.entity_type not in query.entity_types:
            return False
        if query.sources and not set(query.sources) & set(document.source_names):
            return False
        if query.source_types:
            wanted = {item.value for item in query.source_types}
            if not wanted & set(document.source_types):
                return False
        if query.object_types and document.object_type not in query.object_types:
            return False
        if query.missions:
            wanted = set(query.missions)
            haystack = set(document.mission_ids) | {document.id}
            if not wanted & haystack:
                return False
        if query.topics:
            wanted = {topic.lower() for topic in query.topics}
            present = {topic.lower() for topic in document.topics}
            if not wanted & present:
                return False
        if query.start_date and (document.date is None or document.date < query.start_date):
            return False
        if query.end_date and (document.date is None or document.date > query.end_date):
            return False
        if not query.include_stale and document.is_stale:
            return False
        return True

    # -- search -----------------------------------------------------------
    def search(self, query: SearchQuery) -> SearchResponse:
        """Run a query and return a full `SearchResponse`."""
        from .tokenizer import expand_query_tokens, normalize

        started = time.time()
        phrase = normalize(query.text)
        tokens = expand_query_tokens(query.text) if query.text else []

        if query.is_browse:
            scored = [
                (document.id, 1.0, MatchType.PARTIAL, [], True)
                for document in self._documents.values()
                if self._passes_filters(document, query)
            ]
        else:
            candidates: Set[str] = set()
            for token in tokens:
                candidates.update(self._postings.get(token, {}))
                if not self._postings.get(token):
                    for candidate in self._prefix_matches(token, limit=25):
                        candidates.update(self._postings.get(candidate, {}))
            candidates.update(self._exact.get(phrase, set()))
            candidates.update(self._alias_exact.get(phrase, set()))

            scored = []
            for document_id in candidates:
                document = self._documents[document_id]
                if not self._passes_filters(document, query):
                    continue
                score, match_type, fields, exact = self._score_document(
                    document_id, tokens, phrase
                )
                if score <= 0.0:
                    continue
                scored.append((document_id, score, match_type, fields, exact))

        floor = max(query.min_score, 0.0)
        above_floor = [item for item in scored if item[1] >= floor]

        #: A result counts as reliable evidence when it matched a query term
        #: exactly, or when it scored above the floor. A prefix-only match on a
        #: fragment is neither, and presenting one as an answer would be a
        #: guess dressed up as a result.
        reliable = [
            item
            for item in above_floor
            if item[4] or item[1] >= self.reliability_floor
        ]

        status = SearchStatus.OK
        explanation = None
        if not scored:
            status = SearchStatus.EMPTY
            explanation = "no indexed record matched this query"
        elif not query.is_browse and not reliable:
            status = SearchStatus.NO_RELIABLE_MATCH
            explanation = (
                "found {0} candidate(s), but none matched a query term exactly or "
                "scored above the reliability threshold of {1:.2f}".format(
                    len(scored), self.reliability_floor
                )
            )
            above_floor = []

        ordered = self._sort(above_floor, query)
        total = len(ordered)
        page = ordered[query.offset:query.offset + query.limit]

        results = [
            self._to_result(document_id, score, match_type, fields)
            for document_id, score, match_type, fields, _exact in page
        ]

        facets: List[SearchFacet] = []
        if query.include_facets:
            facets = self._facets([item[0] for item in ordered])

        return SearchResponse(
            query=query,
            status=status,
            results=results,
            total=total,
            offset=query.offset,
            limit=query.limit,
            took_ms=(time.time() - started) * 1000.0,
            facets=facets,
            explanation=explanation,
        )

    def _sort(self, scored, query: SearchQuery):
        if query.sort is SortOrder.RELEVANCE:
            return sorted(scored, key=lambda item: (-item[1], item[0]))
        if query.sort is SortOrder.TITLE:
            return sorted(scored, key=lambda item: self._documents[item[0]].title.lower())

        def date_key(item):
            date = self._documents[item[0]].date
            #: Records with no date sort last in both directions rather than
            #: being silently treated as very old or very new.
            return (date is None, date or datetime.min)

        reverse = query.sort is SortOrder.NEWEST
        undated = [item for item in scored if self._documents[item[0]].date is None]
        dated = [item for item in scored if self._documents[item[0]].date is not None]
        dated.sort(key=lambda item: self._documents[item[0]].date, reverse=reverse)
        return dated + undated

    def _to_result(self, document_id, score, match_type, fields) -> SearchResult:
        document = self._documents[document_id]
        return SearchResult(
            id=document.id,
            entity_type=document.entity_type,
            title=document.title,
            summary=document.summary,
            score=round(float(score), 6),
            match_type=match_type,
            matched_fields=fields,
            provenance=document.provenance,
            object_type=document.object_type,
            topics=document.topics,
            mission_ids=document.mission_ids,
            date=document.date,
            url=document.url,
            metadata=document.metadata,
        )

    def _facets(self, document_ids: Sequence[str]) -> List[SearchFacet]:
        entity_counts: Dict[str, int] = {}
        source_counts: Dict[str, int] = {}
        topic_counts: Dict[str, int] = {}
        for document_id in document_ids:
            document = self._documents[document_id]
            key = document.entity_type.value
            entity_counts[key] = entity_counts.get(key, 0) + 1
            for name in set(document.source_names):
                source_counts[name] = source_counts.get(name, 0) + 1
            for topic in set(document.topics):
                topic_counts[topic] = topic_counts.get(topic, 0) + 1
        return [
            SearchFacet(name="entity_type", counts=entity_counts),
            SearchFacet(name="source", counts=source_counts),
            SearchFacet(name="topic", counts=topic_counts),
        ]

    # -- vocabulary --------------------------------------------------------
    def knows(self, token: str) -> bool:
        """Whether `token` appears anywhere in the indexed corpus."""
        from .tokenizer import normalize, singularize

        needle = normalize(token)
        if not needle:
            return False
        if needle in self._postings or needle in self._exact:
            return True
        if needle in self._alias_exact:
            return True
        singular = singularize(needle)
        return bool(singular and singular in self._postings)

    #: Words that name a *catalogue or namespace* rather than a subject.
    #: "What is NORAD 25544?" is a question about object 25544, not about an
    #: entity called NORAD — and treating the namespace as an unknown subject
    #: made the system refuse questions it could answer perfectly well. This is
    #: the over-aggressive-filter failure the injection scanner is careful to
    #: avoid, arriving through a different door.
    IDENTIFIER_NAMESPACES = frozenset({
        "norad", "cospar", "spk", "spkid", "tle", "gp", "omm", "sbdb",
        "mpc", "jpl", "nasa", "esa", "isro", "nrsc", "ntrs", "eonet",
        "celestrak", "copernicus", "bhoonidhi", "id", "no", "cat",
        "catalog", "catalogue", "designation", "number",
    })

    def unknown_proper_nouns(self, text: str) -> List[str]:
        """Capitalized query terms that appear nowhere in the corpus.

        A strong, cheap signal that a question is about a specific subject the
        index does not hold. "What did the Beagle 2 lander discover on Mars?"
        overlaps heavily with every Mars mission on the generic words, so
        similarity alone cannot tell that *Beagle 2* is missing — but the
        absence of the name itself can.

        Only mid-sentence capitals count. The first word of a sentence is
        capitalized by grammar, not because it names something.
        """
        from .tokenizer import STOP_WORDS

        words = str(text or "").split()
        unknown: List[str] = []
        for position, word in enumerate(words):
            stripped = word.strip(".,;:!?'\"()[]")
            #: Strip a possessive before testing. "the ISS's elements" is about
            #: the ISS, and treating "ISS's" as an unknown name made the system
            #: refuse questions about entities it holds.
            for suffix in ("'s", "’s", "s'", "s’"):
                if stripped.endswith(suffix):
                    stripped = stripped[: -len(suffix)]
                    break
            if position == 0 or not stripped:
                continue
            if not stripped[0].isupper():
                continue
            if stripped.lower() in STOP_WORDS:
                continue
            if stripped.lower() in self.IDENTIFIER_NAMESPACES:
                continue
            #: An all-caps token is often an acronym worth the same treatment,
            #: but a single letter is too weak a signal to act on.
            if len(stripped) < 2:
                continue
            if not self.knows(stripped) and stripped not in unknown:
                unknown.append(stripped)
        return unknown

    # -- suggestions -------------------------------------------------------
    def suggest(self, prefix: str, limit: int = 10) -> List[str]:
        """Autocomplete over titles and aliases."""
        from .tokenizer import normalize

        needle = normalize(prefix)
        if not needle:
            return []
        found: List[str] = []
        for document in self._documents.values():
            for candidate in [document.title] + document.aliases:
                if normalize(candidate).startswith(needle) and candidate not in found:
                    found.append(candidate)
                    if len(found) >= limit:
                        return sorted(found, key=len)
        return sorted(found, key=len)
