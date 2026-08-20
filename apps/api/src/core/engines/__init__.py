"""The seam between the API and the repository's compute engines.

Before this module existed, `apps/api/` imported nothing from `simulation/`,
`search/`, `ai/`, `data/`, or `packages/contracts/` — roughly 55,000 lines of
physics, retrieval, and space-data code with no route in front of it. This is
the one place that reaches across that boundary.

Why a module rather than direct imports
---------------------------------------
Three reasons, all of which showed up during the first-prototype integration:

1. **Path setup.** The engines are not installed packages; they are sibling
   trees importable only with the repository root on ``sys.path``. Doing that
   once, here, beats every router repeating it.
2. **Optional dependencies.** The AI and search trees pull in ``httpx`` and
   ``numpy``. The API must still boot, and ``/health`` must still answer, on an
   install that lacks them — so availability is probed and reported, never
   assumed.
3. **Blast radius.** Route handlers import *this*, not the engines. When an
   engine's internal layout changes, one file moves.

Nothing here contains physics, retrieval, or prompt logic. It resolves imports
and reports what is available.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = [
    "EngineUnavailableError",
    "engine_status",
    "ensure_engine_paths",
    "get_ai",
    "get_catalog",
    "get_environment",
    "get_search",
    "get_simulation",
]

#: Repository root. This file is at
#: ``<root>/apps/api/src/core/engines/__init__.py``, so the root is six levels
#: up: engines -> core -> src -> api -> apps -> root.
_REPO_ROOT = Path(__file__).resolve().parents[5]

#: Trees that must be importable for the engines to work. `packages/contracts`
#: is separate because P4's contracts live under an extra `src` directory.
_ENGINE_PATHS = (_REPO_ROOT, _REPO_ROOT / "packages" / "contracts" / "src")


class EngineUnavailableError(RuntimeError):
    """Raised when an engine is asked for but its dependencies are missing.

    Routers translate this into a 503 rather than a 500: the request was
    well-formed and the service is simply not equipped to answer it right now.
    """

    def __init__(self, engine: str, reason: str) -> None:
        self.engine = engine
        self.reason = reason
        super().__init__(f"{engine} engine unavailable: {reason}")


def ensure_engine_paths() -> None:
    """Put the engine trees on ``sys.path``. Idempotent.

    Mirrors the repository-root ``_bootstrap.py`` that the P4 test suite uses,
    deliberately duplicated rather than imported: importing the bootstrap would
    itself require the path to already be set.
    """
    for path in _ENGINE_PATHS:
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


@lru_cache
def get_simulation() -> Any:
    """The Python flight simulation engine.

    Returns:
        A module exposing ``run_simulation(SimConfig) -> SimResult`` and the
        contract types.

    Raises:
        EngineUnavailableError: If the simulation tree cannot be imported.
    """
    ensure_engine_paths()
    try:
        from simulation.analysis.evaluation import evaluate_mission  # noqa: F401
        from simulation.contracts import SimConfig, SimResult  # noqa: F401
        from simulation.engine.runner import run_simulation  # noqa: F401
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EngineUnavailableError("simulation", str(exc)) from exc

    import types

    module = types.SimpleNamespace(
        run_simulation=run_simulation,
        evaluate_mission=evaluate_mission,
        SimConfig=SimConfig,
        SimResult=SimResult,
    )
    return module


@lru_cache
def get_search() -> Any:
    """The P4 hybrid (keyword + semantic) search engine.

    Raises:
        EngineUnavailableError: If the search tree cannot be imported.
    """
    ensure_engine_paths()
    try:
        from search.keyword.index import KeywordIndex
        from search.ranking.hybrid import HybridSearch
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EngineUnavailableError("search", str(exc)) from exc

    import types

    return types.SimpleNamespace(KeywordIndex=KeywordIndex, HybridSearch=HybridSearch)


@lru_cache
def get_ai() -> Any:
    """The P4 grounded-RAG assistant and its provider registry.

    Raises:
        EngineUnavailableError: If the AI tree cannot be imported.
    """
    ensure_engine_paths()
    try:
        from ai.assistant.space_assistant import SpaceAssistant
        from ai.grounding.rag import GroundedRAG
        from ai.providers.registry import (
            build_provider,
            describe_configuration,
            resolve_provider_name,
        )
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EngineUnavailableError("ai", str(exc)) from exc

    import types

    return types.SimpleNamespace(
        SpaceAssistant=SpaceAssistant,
        GroundedRAG=GroundedRAG,
        build_provider=build_provider,
        resolve_provider_name=resolve_provider_name,
        describe_configuration=describe_configuration,
    )


@lru_cache
def get_catalog() -> Any:
    """The platform catalog: objects, sites, science, experiments, missions, assets.

    Unlike the other engines this one has no heavy dependencies beyond pydantic,
    so in practice it is always available. It goes through the same seam anyway,
    because a router that imports ``data.catalog`` directly is a router that
    breaks when the tree moves.

    Raises:
        EngineUnavailableError: If the data tree cannot be imported.
    """
    ensure_engine_paths()
    try:
        from data.catalog import (
            build_assets,
            build_experiments,
            build_launch_sites,
            build_reference_missions,
            build_science_topics,
            build_space_objects,
            rotation_bonus_ms,
        )
        from data.catalog.science import STRANDS
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EngineUnavailableError("catalog", str(exc)) from exc

    import types

    return types.SimpleNamespace(
        build_space_objects=build_space_objects,
        build_launch_sites=build_launch_sites,
        build_science_topics=build_science_topics,
        build_experiments=build_experiments,
        build_reference_missions=build_reference_missions,
        build_assets=build_assets,
        rotation_bonus_ms=rotation_bonus_ms,
        STRANDS=STRANDS,
    )


@lru_cache
def get_environment() -> Any:
    """Live launch-site weather and the launch commit criteria.

    Raises:
        EngineUnavailableError: If the environment tree cannot be imported.
    """
    ensure_engine_paths()
    try:
        from data.environment import (
            WeatherObservation,
            WeatherService,
            assess_launch_conditions,
        )
    except ImportError as exc:  # pragma: no cover - depends on the install
        raise EngineUnavailableError("environment", str(exc)) from exc

    import types

    return types.SimpleNamespace(
        WeatherService=WeatherService,
        WeatherObservation=WeatherObservation,
        assess_launch_conditions=assess_launch_conditions,
    )


def engine_status() -> dict[str, dict[str, Any]]:
    """Which engines are importable right now, for ``/health/engines``.

    Deliberately never raises: this is the endpoint an operator checks *because*
    something is wrong, so it reports failures as data rather than becoming one.
    """
    status: dict[str, dict[str, Any]] = {}
    for name, loader in (
        ("simulation", get_simulation),
        ("search", get_search),
        ("ai", get_ai),
        ("catalog", get_catalog),
        ("environment", get_environment),
    ):
        try:
            loader()
        except EngineUnavailableError as exc:
            status[name] = {"available": False, "reason": exc.reason}
        except Exception as exc:  # noqa: BLE001 - never let this endpoint fail
            status[name] = {"available": False, "reason": type(exc).__name__}
        else:
            status[name] = {"available": True, "reason": None}
    return status
