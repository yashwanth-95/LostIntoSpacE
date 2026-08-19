"""Tokenization for scientific text.

Domain-specific in three ways that ordinary tokenizers get wrong here:

* **Hyphenated terms.** "Max-Q" must match "max q", "maxq" and "Max-Q". Splitting
  on the hyphen alone loses the joined form; keeping it whole loses the parts.
  Both are emitted.
* **Designations.** "2024 YR4" and "1998-067A" are identifiers, not prose. Their
  joined forms are preserved so a paste-in search finds them.
* **Stop words.** A small list only. Dropping "a" is safe; dropping "not" or
  "no" would change the meaning of a scientific phrase.
"""

import re
from typing import Iterable, List, Optional, Sequence, Set

__all__ = [
    "tokenize",
    "normalize",
    "STOP_WORDS",
    "expand_query_tokens",
    "singularize",
]

#: Words carrying no retrieval signal. Two groups: ordinary function words, and
#: the interrogatives and auxiliaries that dominate natural-language questions.
#:
#: The second group matters more than it looks. "How does a gravity assist
#: work?" is 7 tokens, of which 5 are noise; leaving them in means most of the
#: query vector is generic filler that matches long documents at random.
#:
#: Curated by hand rather than taken from a generic list, because several
#: everyday stop words are meaningful here — "no", "not", "up", "down" change
#: the sense of a scientific statement, and single letters are element symbols
#: (e for eccentricity, i for inclination, q for periapsis distance and Max-Q).
STOP_WORDS: Set[str] = {
    # articles, conjunctions, prepositions
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "and", "or",
    "with", "by", "from", "as", "into", "onto", "than", "then", "there",
    # copulas and auxiliaries
    "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "doing", "done",
    "has", "have", "had", "having",
    "can", "could", "will", "would", "shall", "should", "may", "might", "must",
    # pronouns and determiners
    "it", "its", "this", "that", "these", "those", "their", "them", "they",
    "you", "your", "we", "our", "us", "he", "she", "his", "her", "i",
    "some", "any", "each", "such", "other", "another",
    # interrogatives
    "what", "how", "why", "when", "where", "which", "who", "whom", "whose",
    # generic verbs and fillers common in questions
    "work", "works", "mean", "means", "tell", "explain", "describe",
    "about", "please", "much", "many", "very", "also", "just", "get", "gets",
}

_SPLIT = re.compile(r"[^a-z0-9]+")
_ALPHANUM = re.compile(r"[a-z0-9]+")
#: Sequences that look like designations: letters and digits with separators.
_DESIGNATION = re.compile(r"\b[a-z0-9]+(?:[-/ ][a-z0-9]+)+\b")


def normalize(text: str) -> str:
    """Lowercase and collapse whitespace."""
    return " ".join(str(text or "").lower().split())


def tokenize(text: str, keep_stop_words: bool = False) -> List[str]:
    """Split text into search tokens.

    Emits, in addition to the plain word tokens:

    * the joined form of any hyphenated or slash-separated term, so `max-q`
      also indexes as `maxq`;
    * the joined form of a spaced designation, so `2024 YR4` also indexes as
      `2024yr4`.
    """
    lowered = normalize(text)
    if not lowered:
        return []

    tokens: List[str] = []
    seen: Set[str] = set()

    def add(token: str) -> None:
        if not token or token in seen:
            return
        if not keep_stop_words and token in STOP_WORDS:
            return
        seen.add(token)
        tokens.append(token)

    for word in _SPLIT.split(lowered):
        add(word)

    #: Joined forms for hyphenated and spaced compounds.
    for match in _DESIGNATION.finditer(lowered):
        joined = "".join(_ALPHANUM.findall(match.group(0)))
        if len(joined) > 1:
            add(joined)

    return tokens


#: Suffixes stripped from query tokens to match a singular indexed form.
#: Query-side only: the index keeps words exactly as written, so this never
#: corrupts stored text. Deliberately minimal — a real stemmer would conflate
#: terms like "orbiter" and "orbit" that mean different things here.
_PLURAL_RULES = (
    ("ies", "y"),
    ("ses", "s"),
    ("xes", "x"),
    ("hes", "h"),
    ("s", ""),
)

#: Words whose trailing "s" is part of the word, not a plural.
_NOT_PLURAL = {"mars", "gas", "class", "mass", "axis", "us", "gps", "physics",
               "dynamics", "mechanics", "its", "this", "has", "was", "is", "as"}


def singularize(token: str) -> Optional[str]:
    """A plausible singular form of `token`, or `None`.

    Returns `None` rather than guessing when the word is on the exception list
    or is too short for the transformation to be meaningful.
    """
    if len(token) < 4 or token in _NOT_PLURAL:
        return None
    for suffix, replacement in _PLURAL_RULES:
        if token.endswith(suffix):
            candidate = token[: -len(suffix)] + replacement
            if len(candidate) >= 3:
                return candidate
    return None


def expand_query_tokens(text: str) -> List[str]:
    """Tokens for a *query*, including the phrase and singular forms.

    The full phrase is kept so an exact-title match can be detected without a
    second pass over the text. Singular forms are appended so "exoplanets"
    finds "exoplanet".
    """
    tokens = tokenize(text)
    phrase = normalize(text)

    #: The whole phrase joined is only ever useful as an identifier lookup
    #: ("Max-Q", "1998-067A"). For a full sentence it is a junk token that
    #: matches nothing, so it is only added for short inputs.
    if len(phrase.split()) <= 3:
        joined = "".join(_ALPHANUM.findall(phrase))
        if joined and joined not in tokens:
            tokens.append(joined)

    for token in list(tokens):
        singular = singularize(token)
        if singular and singular not in tokens:
            tokens.append(singular)
    return tokens
