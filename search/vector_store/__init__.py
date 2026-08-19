"""Vector storage and nearest-neighbour retrieval.

`VectorStore` is the interface; `InMemoryVectorStore` is the reference
implementation. When the pgvector decision closes, the vectors go into the
project's existing PostgreSQL database as another table — there is no second
database, and callers do not change.
"""

from .base import VectorFilter, VectorMatch, VectorStore, VectorStoreHealth
from .memory import InMemoryVectorStore

__all__ = [
    "VectorStore",
    "InMemoryVectorStore",
    "VectorFilter",
    "VectorMatch",
    "VectorStoreHealth",
]
