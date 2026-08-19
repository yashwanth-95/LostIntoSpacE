"""Analysis of simulation results.

Person 3 owns the simulation engine; nothing here touches it or reimplements
any physics. This package reads P3's output and explains it against retrieved
scientific references, keeping what the simulator did strictly separate from
why it happens.
"""

from .failure_analysis import FAILURE_SYSTEM_PROMPT, FailureAnalyzer
from .simulation_view import (
    DOCUMENTED_EVENT_TYPES,
    FAILURE_RULES,
    MODEL_FIDELITY,
    SimulationEventView,
    SimulationResultView,
    TelemetrySample,
    parse_simulation_result,
)

__all__ = [
    "FailureAnalyzer",
    "FAILURE_SYSTEM_PROMPT",
    "parse_simulation_result",
    "SimulationResultView",
    "SimulationEventView",
    "TelemetrySample",
    "MODEL_FIDELITY",
    "FAILURE_RULES",
    "DOCUMENTED_EVENT_TYPES",
]
