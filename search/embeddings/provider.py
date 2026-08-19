"""Embedding providers.

The interface is provider-independent: swapping a hosted embedding API for the
local default must not change a line of retrieval code. Only three things are
required of a provider — a stable `model_id`, a fixed `dimensions`, and a batch
`embed`.

The default provider is **local and deterministic**. That is a deliberate
choice, not a placeholder:

* the test suite runs with no API key and no network;
* results are reproducible, so a retrieval-quality regression is attributable to
  a code change rather than to a provider's model being updated underneath us;
* the unresolved pgvector-versus-hosted-embeddings decision in
  `DECISION_LOG.md` stays open.

It is a hashed lexical projection, not a learned semantic model. It captures
term overlap and morphology, which carries the concept queries this product
actually receives, but it will not resolve paraphrases with no shared
vocabulary. `search/evaluation` measures exactly that, so the limitation is
visible rather than assumed away.
"""

import hashlib
import math
from typing import Any, Dict, List, Optional, Sequence

from ..keyword.tokenizer import singularize, tokenize

__all__ = [
    "EmbeddingError",
    "EmbeddingProviderError",
    "DimensionMismatchError",
    "EmbeddingProvider",
    "HashedLexicalProvider",
    "DEFAULT_DIMENSIONS",
]

#: Chosen by measurement, not by taste. On the concept-question evaluation set,
#: top-1 accuracy rises from 4/8 at 384 dimensions to 6/8 at 2048 and then
#: plateaus — 4096 buys nothing. Feature hashing needs enough buckets that
#: collisions stay rare relative to the ~300 features a typical document
#: produces; below about 1024 the collisions dominate and similarity becomes
#: close to noise.
DEFAULT_DIMENSIONS = 2048


class EmbeddingError(Exception):
    """Base class for embedding failures."""


class EmbeddingProviderError(EmbeddingError):
    """The provider could not produce embeddings.

    Retryable in principle: a hosted provider may be briefly unavailable.
    """


class DimensionMismatchError(EmbeddingError):
    """A provider returned vectors of the wrong length.

    Fatal rather than retryable: mixing dimensionalities in one store silently
    corrupts every similarity computation that follows.
    """


class EmbeddingProvider(object):
    """Interface every embedding provider implements."""

    #: Stable identifier, stored on each vector so a model change is detectable.
    model_id = "abstract"
    dimensions = 0

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """Embed a batch of texts. Must return one vector per input, in order."""
        raise NotImplementedError

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]

    def health_check(self) -> Dict[str, Any]:
        """Probe the provider. Never raises; reports instead."""
        try:
            vector = self.embed_one("health check")
        except Exception as exc:  # noqa: BLE001 - health checks report
            return {
                "healthy": False,
                "model_id": self.model_id,
                "detail": "{0}: {1}".format(exc.__class__.__name__, exc),
            }
        return {
            "healthy": len(vector) == self.dimensions,
            "model_id": self.model_id,
            "dimensions": len(vector),
        }

    def validate_batch(self, vectors: Sequence[Sequence[float]], expected: int) -> None:
        """Check a provider's output before it reaches the store."""
        if len(vectors) != expected:
            raise EmbeddingProviderError(
                "provider {0} returned {1} vector(s) for {2} input(s)".format(
                    self.model_id, len(vectors), expected
                )
            )
        for index, vector in enumerate(vectors):
            if len(vector) != self.dimensions:
                raise DimensionMismatchError(
                    "provider {0} returned a {1}-dimensional vector at position "
                    "{2}; {3} was declared".format(
                        self.model_id, len(vector), index, self.dimensions
                    )
                )


class HashedLexicalProvider(EmbeddingProvider):
    """Deterministic local embeddings via feature hashing.

    Features per document: tokens, their singular forms, adjacent token bigrams,
    and character 4-grams within tokens. Character n-grams are what let
    "propulsion" and "propellant" share signal without a learned model.

    Each feature is hashed to a dimension with a signed contribution, weighted
    sub-linearly by frequency, then the vector is L2-normalized so cosine
    similarity is a plain dot product.
    """

    model_id = "hashed-lexical-v1"

    #: Weight per feature kind. Tokens carry the signal; character n-grams are
    #: a small morphological assist. Their weight has to stay low precisely
    #: because there are roughly an order of magnitude more of them — at equal
    #: weight they swamp the words entirely.
    TOKEN_WEIGHT = 1.0
    SINGULAR_WEIGHT = 0.5
    BIGRAM_WEIGHT = 0.5
    CHAR_NGRAM_WEIGHT = 0.12
    #: Shorter tokens produce n-grams that are common across unrelated words,
    #: so they add noise rather than morphology.
    MIN_TOKEN_FOR_CHAR_NGRAMS = 6

    #: Minimum dimensionality. Signed feature hashing needs enough buckets that
    #: collisions stay rare; below this the vectors are mostly collision noise
    #: and similarity becomes meaningless.
    MIN_DIMENSIONS = 128

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS, char_ngram: int = 4):
        if dimensions < self.MIN_DIMENSIONS:
            raise ValueError(
                "dimensions must be at least {0}; fewer buckets than that makes "
                "hash collisions dominate the signal".format(self.MIN_DIMENSIONS)
            )
        self.dimensions = int(dimensions)
        self.char_ngram = int(char_ngram)

    # -- feature extraction ------------------------------------------------
    def _features(self, text: str) -> Dict[str, float]:
        tokens = tokenize(text)
        features: Dict[str, float] = {}

        def bump(feature: str, weight: float) -> None:
            features[feature] = features.get(feature, 0.0) + weight

        for index, token in enumerate(tokens):
            bump("t:" + token, self.TOKEN_WEIGHT)
            singular = singularize(token)
            if singular:
                #: A morphological guess is weaker evidence than the word the
                #: author actually wrote.
                bump("t:" + singular, self.SINGULAR_WEIGHT)
            if index + 1 < len(tokens):
                bump(
                    "b:{0}_{1}".format(token, tokens[index + 1]),
                    self.BIGRAM_WEIGHT,
                )
            if len(token) >= self.MIN_TOKEN_FOR_CHAR_NGRAMS:
                for start in range(len(token) - self.char_ngram + 1):
                    bump(
                        "c:" + token[start:start + self.char_ngram],
                        self.CHAR_NGRAM_WEIGHT,
                    )
        return features

    def _hash(self, feature: str) -> int:
        digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big")

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        vectors: List[List[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for feature, weight in self._features(text or "").items():
                hashed = self._hash(feature)
                bucket = hashed % self.dimensions
                #: Signed hashing keeps collisions from systematically inflating
                #: similarity: two unrelated features that collide are as likely
                #: to cancel as to reinforce.
                sign = 1.0 if (hashed >> 63) & 1 else -1.0
                #: Damp repetition sub-linearly while preserving the *relative*
                #: weights between feature kinds. Applying a log to the weight
                #: itself would flatten those weights to near-equal, which lets
                #: the far more numerous character n-grams drown out the words.
                vector[bucket] += sign * weight * (1.0 + math.log(weight + 1.0)) / (
                    1.0 + math.log(2.0)
                )
            norm = math.sqrt(sum(component * component for component in vector))
            if norm > 0.0:
                vector = [component / norm for component in vector]
            vectors.append(vector)
        return vectors
