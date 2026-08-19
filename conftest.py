"""Pytest bootstrap for the P4 Python trees.

Path setup lives in `_bootstrap.py` so standalone scripts — the evaluation
runners in particular — can use exactly the same one.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _bootstrap import ensure_paths  # noqa: E402

ensure_paths()
