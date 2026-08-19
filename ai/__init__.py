"""AI layer.

Owner: P4 (AI / Search / Data / Integration).

    Question -> classification -> hybrid search -> retrieval -> reranking
             -> context selection -> AI -> citation validation -> response

The rule the whole package is built around, from `ai/README.md`:

> AI is the EXPLANATION layer. The simulation engine is the TRUTH layer.

Vendor SDK code is confined to `ai/providers/`; nothing above it imports one.
"""

__all__ = []
