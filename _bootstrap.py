"""Makes the P4 Python trees importable without an install step.

    import contracts.provenance  -> packages/contracts/src/contracts/
    import data.models           -> data/
    import search.retrieval      -> search/
    import ai.grounding          -> ai/

Called from `conftest.py` for tests and from `evaluation/__init__.py` for
standalone scripts, so both paths agree. Once the project adopts an editable
install (`pip install -e .`), this becomes unnecessary and should go.

`apps/api/` imports P4 modules the same way, with the repository root on
`sys.path`; that wiring is P2's to add in their own entrypoint.
"""

import sys
from pathlib import Path

__all__ = ["ROOT", "ensure_paths"]

ROOT = Path(__file__).resolve().parent

_PATHS = [
    ROOT,
    ROOT / "packages" / "contracts" / "src",
]


def ensure_paths() -> None:
    """Put the P4 trees on `sys.path`. Idempotent."""
    for path in _PATHS:
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
