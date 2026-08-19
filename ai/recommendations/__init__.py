"""MVP recommendation engine: rules plus semantic similarity."""

from .engine import SIGNAL_WEIGHTS, RecommendationEngine, RecommendationRequest

__all__ = ["RecommendationEngine", "RecommendationRequest", "SIGNAL_WEIGHTS"]
