"""Grounded AI answering and simulation failure analysis.

Separate from ``ai/service.py``, which persists conversations and messages and
deliberately calls no model. This module is the other half: it runs P4's
grounded-RAG pipeline and its failure analyser. Neither writes to the database
— a caller that wants the exchange kept posts it to ``/conversations``.

Grounding, not chat
-------------------
Every answer is assembled from retrieved evidence and carries the sources it
used. When the corpus has nothing relevant, the pipeline says so rather than
inventing an answer — a property the engine's own security tests assert.

Which provider answers
----------------------
Chosen by the P4 registry from the environment. On an install with no LLM
credentials configured, the registry resolves to its `extractive` provider,
which composes answers out of retrieved passages rather than generating prose.
That is a real, useful, honest fallback, and the response says which provider
produced it so nothing is presented as more than it is.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from src.core.engines import EngineUnavailableError, ensure_engine_paths, get_ai
from src.core.exceptions import AppError, BadRequestError
from src.search.service import _engine as _search_engine

logger = logging.getLogger("api.ai")


def _unavailable(exc: Exception) -> AppError:
    return AppError(503, "AI_ENGINE_UNAVAILABLE", "The AI assistant is not available")


@lru_cache(maxsize=1)
def _provider() -> Any:
    """The configured AI provider, built once per process."""
    ensure_engine_paths()
    return get_ai().build_provider()


@lru_cache(maxsize=1)
def _assistant() -> Any:
    """The domain assistant over the grounded RAG pipeline.

    ``project_client`` is deliberately left as ``None``. The assistant's own
    docstring warns that a project client shared across users is exactly how
    project data leaks, and there is no per-call token. Project-scoped context
    needs a per-request client and is not wired here.
    """
    ai = get_ai()
    return ai.SpaceAssistant(ai.GroundedRAG(_search_engine(), _provider()))


@lru_cache(maxsize=1)
def _failure_analyzer() -> Any:
    ensure_engine_paths()
    from ai.analysis.failure_analysis import FailureAnalyzer

    return FailureAnalyzer(_search_engine(), _provider())


def provider_info() -> dict[str, Any]:
    """Which provider is configured, for the client to display honestly."""
    try:
        return get_ai().describe_configuration()
    except EngineUnavailableError as exc:
        raise _unavailable(exc) from exc


async def ask(question: str) -> dict[str, Any]:
    """
    Answer one question, grounded in the knowledge corpus.

    Args:
        question: The user's question.

    Returns:
        The engine's ``AIResponse`` as a JSON-safe dict, including citations,
        confidence, and diagnostics.

    Raises:
        AppError: 503 if the AI engine is unavailable.
    """
    try:
        assistant = _assistant()
    except EngineUnavailableError as exc:
        raise _unavailable(exc) from exc
    except Exception as exc:  # noqa: BLE001 - a build failure is a 503, not a 500
        logger.exception("assistant construction failed")
        raise _unavailable(exc) from exc

    response = await assistant.ask(question)
    return response.model_dump(mode="json")


async def explain_failure(
    simulation_result: dict[str, Any],
    *,
    vehicle_description: str | None = None,
    mission_description: str | None = None,
) -> dict[str, Any]:
    """
    Explain why a simulated flight went wrong.

    This is the workflow the product is built around: a run fails, its
    telemetry and failure records are handed here, relevant engineering
    knowledge is retrieved, and the answer separates what the *simulation*
    computed from what the *sources* say. The analysis carries an explicit
    list of the simulation's own limitations, so a modelled failure is never
    presented as a real-world finding.

    Args:
        simulation_result: A ``SimResult`` payload from ``/simulations/run``.
        vehicle_description: Optional free text about the vehicle.
        mission_description: Optional free text about the mission.

    Returns:
        The engine's ``FailureAnalysis`` as a JSON-safe dict.

    Raises:
        BadRequestError: If the payload is not a readable simulation result.
        AppError: 503 if the AI engine is unavailable.
    """
    try:
        analyzer = _failure_analyzer()
        ensure_engine_paths()
        from ai.analysis.simulation_view import parse_simulation_result
    except EngineUnavailableError as exc:
        raise _unavailable(exc) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("failure analyzer construction failed")
        raise _unavailable(exc) from exc

    try:
        view = parse_simulation_result(simulation_result)
    except Exception as exc:  # noqa: BLE001 - a bad payload is the caller's problem
        raise BadRequestError(f"Unreadable simulation result: {exc}") from exc

    analysis = await analyzer.analyze(
        view,
        vehicle_description=vehicle_description,
        mission_description=mission_description,
    )
    return analysis.model_dump(mode="json")
