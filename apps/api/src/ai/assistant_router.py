"""Grounded AI routes.

Public, like search and simulation: a visitor should be able to ask a question
and get a sourced answer before creating an account. Conversation *persistence*
(``/conversations``) stays authenticated, because that is per-user data.
"""

from typing import Annotated, Any

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from src.ai.assistant_service import ask, explain_failure, provider_info
from src.core.engines import ensure_engine_paths
from src.core.envelope import success_envelope
from src.schemas.common import ErrorResponse, SuccessResponse

router = APIRouter()


def _envelope_models() -> tuple[Any, Any]:
    """Publish P4's own ``AIResponse`` and ``FailureAnalysis`` as the response
    models, so citations, confidence, and the simulation-limitation list all
    appear in the schema rather than as an untyped bag."""
    try:
        ensure_engine_paths()
        from contracts.ai import AIResponse
        from contracts.analysis import FailureAnalysis
    except ImportError:  # pragma: no cover - depends on the install
        return None, None

    class AskResponse(BaseModel):
        """`{"status": "success", "data": <AIResponse>}`."""

        status: str = "success"
        data: AIResponse

    class FailureAnalysisResponse(BaseModel):
        """`{"status": "success", "data": <FailureAnalysis>}`."""

        status: str = "success"
        data: FailureAnalysis

    return AskResponse, FailureAnalysisResponse


_ASK_MODEL, _ANALYSIS_MODEL = _envelope_models()


class ProviderConfiguration(BaseModel):
    """Which AI provider is configured, and which are available."""

    selected_provider: str
    available: list[str]
    selection_env: str
    keys: dict[str, Any]


_AI_RESPONSES: dict = {
    503: {"model": ErrorResponse, "description": "The AI engine is unavailable"},
}

_EXPLAIN_RESPONSES: dict = {
    400: {"model": ErrorResponse, "description": "The simulation result is unreadable"},
    503: {"model": ErrorResponse, "description": "The AI engine is unavailable"},
}


class AskRequest(BaseModel):
    """A question for the assistant, with what the client is currently showing.

    `context` is deliberately untyped here. Its shape is the client's current
    view — the rocket being built, the flight just flown, the conditions at the
    pad — and pinning it to a schema in the API would mean editing three files
    every time the builder gains a field. It is rendered by
    ``ai.context.workbench``, which reads only the keys it knows, sanitizes all
    free text, and ignores everything else.

    The size cap is the real defence: without it this endpoint would accept an
    arbitrarily large blob and hand it to a model.
    """

    question: Annotated[str, Field(min_length=3, max_length=1000)]
    context: dict[str, Any] | None = Field(
        default=None,
        description="The client's current state: rocket, mission, weather, simulation, evaluation.",
    )

    @field_validator("context")
    @classmethod
    def _cap_context_size(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """Reject a context large enough to be an attack rather than a page state.

        A full telemetry series is megabytes; a workbench context is a few
        kilobytes. Anything past 64 KB is not what this field is for.
        """
        if value is None:
            return None
        import json

        encoded = json.dumps(value, default=str)
        if len(encoded) > 64_000:
            raise ValueError("context is too large; send a summary, not raw telemetry")
        return value


class ExplainFailureRequest(BaseModel):
    """A finished simulation to explain."""

    #: A SimResult payload, as returned by POST /simulations/run.
    simulation_result: dict[str, Any]
    vehicle_description: str | None = Field(default=None, max_length=2000)
    mission_description: str | None = Field(default=None, max_length=2000)


@router.post("/ask", response_model=_ASK_MODEL, responses=_AI_RESPONSES, tags=["ai"])
async def ask_question(payload: AskRequest) -> dict:
    """Answer a space or engineering question.

    The answer is assembled from retrieved evidence and cites what it used. If
    the corpus holds nothing relevant, the assistant says so instead of
    inventing an answer.

    When the client sends `context`, the user's own rocket, flight and launch
    conditions are added to that evidence — so "why did my rocket fail?" is
    answered from the failure record of the flight they just watched, with the
    measured value and the threshold it crossed, rather than from the general
    theory of why rockets fail.
    """
    return success_envelope(await ask(payload.question, payload.context))


@router.post(
    "/explain-failure",
    response_model=_ANALYSIS_MODEL,
    responses=_EXPLAIN_RESPONSES,
    tags=["ai"],
)
async def explain_simulation_failure(payload: ExplainFailureRequest) -> dict:
    """Explain why a simulated flight failed, grounded in retrieved sources.

    The response separates what the simulation computed from what the sources
    say, and lists the simulation's own limitations, so a modelled outcome is
    never read as a statement about a real vehicle.
    """
    return success_envelope(
        await explain_failure(
            payload.simulation_result,
            vehicle_description=payload.vehicle_description,
            mission_description=payload.mission_description,
        )
    )


@router.get(
    "/provider",
    response_model=SuccessResponse[ProviderConfiguration],
    responses=_AI_RESPONSES,
    tags=["ai"],
)
async def provider() -> dict:
    """Which AI provider is configured on this server.

    Published so the interface can be honest about what is answering — an
    install with no LLM credentials falls back to an extractive provider that
    composes answers from retrieved passages rather than generating prose.
    """
    return success_envelope(provider_info())
