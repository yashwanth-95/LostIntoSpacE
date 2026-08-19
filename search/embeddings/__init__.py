"""Provider-independent embeddings.

Swapping the local default for a hosted embedding API changes one constructor
argument and nothing else. Every vector carries the provenance metadata
retrieval and citation need.
"""

from .provider import (
    DEFAULT_DIMENSIONS,
    DimensionMismatchError,
    EmbeddingError,
    EmbeddingProvider,
    EmbeddingProviderError,
    HashedLexicalProvider,
)
from .service import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    EmbeddingBatchResult,
    EmbeddingService,
    chunk_text,
)
from .vectors import (
    TRUST_ORDER,
    EmbeddingRecord,
    TrustLevel,
    VectorMetadata,
    content_hash,
    trust_for_source_type,
)

__all__ = [
    "EmbeddingProvider",
    "HashedLexicalProvider",
    "EmbeddingError",
    "EmbeddingProviderError",
    "DimensionMismatchError",
    "DEFAULT_DIMENSIONS",
    "EmbeddingService",
    "EmbeddingBatchResult",
    "chunk_text",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_OVERLAP",
    "EmbeddingRecord",
    "VectorMetadata",
    "TrustLevel",
    "TRUST_ORDER",
    "trust_for_source_type",
    "content_hash",
]
