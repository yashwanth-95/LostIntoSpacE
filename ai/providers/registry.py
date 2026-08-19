"""Provider selection and configuration.

Which provider runs is decided by environment variables, at construction, on
the server. Nothing here accepts a credential as an argument.

**No vendor SDK is installed by this project.** The repository has no AI
dependency, and the audit found no existing provider to reuse, so adding one is
a decision for the team rather than a side effect of this work. The interface
and the registry are ready for it: implementing a vendor adapter means adding
one file under `ai/providers/` and one entry to `_BUILDERS`, with no change
anywhere above.
"""

import os
from typing import Any, Callable, Dict, List, Optional

from .base import AIProvider, AIProviderAuthError, ProviderInfo
from .mock import ExtractiveProvider, MockAIProvider

__all__ = [
    "AI_PROVIDER_ENV",
    "available_providers",
    "build_provider",
    "resolve_provider_name",
    "describe_configuration",
]

#: Selects the provider. Unset means "choose automatically".
AI_PROVIDER_ENV = "LIS_AI_PROVIDER"

#: Provider name -> the environment variables that would supply its key.
#: Listed so `describe_configuration` can report what is available without
#: reading, logging or returning any value.
_KEY_ENV: Dict[str, List[str]] = {
    "mock": [],
    "extractive": [],
}

_BUILDERS: Dict[str, Callable[..., AIProvider]] = {
    "mock": lambda **kwargs: MockAIProvider(**kwargs),
    "extractive": lambda **kwargs: ExtractiveProvider(**kwargs),
}


def available_providers() -> List[str]:
    return sorted(_BUILDERS)


def resolve_provider_name(requested: Optional[str] = None) -> str:
    """Decide which provider to use.

    Order: explicit argument, then the environment variable, then the offline
    fallback. The fallback is `extractive` rather than an error, so a
    deployment without an AI key still serves grounded — if terse — answers.
    """
    name = (requested or os.environ.get(AI_PROVIDER_ENV) or "").strip().lower()
    if name:
        if name not in _BUILDERS:
            raise ValueError(
                "unknown AI provider {0!r}; available: {1}".format(
                    name, ", ".join(available_providers())
                )
            )
        return name
    return "extractive"


def build_provider(name: Optional[str] = None, **kwargs) -> AIProvider:
    """Construct a provider by name."""
    resolved = resolve_provider_name(name)
    return _BUILDERS[resolved](**kwargs)


def describe_configuration() -> Dict[str, Any]:
    """Report what is configured, without exposing any credential.

    Returns whether a key is *present*, never the key, never a prefix of it,
    and never its length — all of which leak into logs and screenshots.
    """
    resolved = resolve_provider_name()
    report: Dict[str, Any] = {
        "selected_provider": resolved,
        "available": available_providers(),
        "selection_env": AI_PROVIDER_ENV,
        "keys": {},
    }
    for provider, variables in _KEY_ENV.items():
        report["keys"][provider] = {
            "env_vars": variables,
            "configured": any(
                bool(os.environ.get(variable, "").strip()) for variable in variables
            ),
        }
    return report
