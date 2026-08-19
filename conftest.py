"""Pytest bootstrap for the P4 Python trees.

Makes the repository importable without an install step:

    import contracts.provenance   -> packages/contracts/src/contracts/
    import data.models           -> data/
    import search.retrieval      -> search/
    import ai.rag                -> ai/

`apps/api/` imports P4 modules the same way (repo root on ``sys.path``); that
wiring is P2's to add in their own application entrypoint.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_PATHS = [
    _ROOT,
    _ROOT / "packages" / "contracts" / "src",
]

for _p in _PATHS:
    _s = str(_p)
    if _s not in sys.path:
        sys.path.insert(0, _s)
