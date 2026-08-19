"""Repeatable accuracy evaluation for the Person 4 subsystem.

    datasets/  labelled question sets
    runners/   harnesses that execute a set against a component
    metrics/   scoring functions
    reports/   generated baselines, checked in so regressions are visible

Owner: P4. Everything here is offline and deterministic: no evaluation depends
on a network call or an AI vendor account.
"""

import sys as _sys
from pathlib import Path as _Path

#: The evaluation runners are executable scripts, not only test fixtures, so
#: they need the same import bootstrap `conftest.py` applies for pytest.
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _bootstrap import ensure_paths as _ensure_paths  # noqa: E402

_ensure_paths()

__all__ = []
