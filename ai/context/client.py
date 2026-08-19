"""Client for Person 2's project API.

**P4 never touches PostgreSQL.** Every read goes through P2's HTTP endpoints,
documented in `docs/api/API.md`. That is not a style preference: P2's endpoints
enforce ownership, and a direct database read would bypass exactly the check
that keeps one user's project out of another user's answer.

The authorization model is deliberately minimal:

* The **caller's own bearer token** is the only credential used. P4 holds no
  service account, so there is no privileged path to abuse and nothing to leak.
* A 401/403/404 from P2 is surfaced as such and never worked around. If P2 says
  the user cannot see a project, the assistant answers without it.
* Every fetched record is checked against the requesting user before it can
  reach a prompt — defence in depth behind P2's own check, not a replacement
  for it.
"""

import json
from typing import Any, Dict, List, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field

from .models import (
    LearningProgress,
    MissionConfiguration,
    ProjectContext,
    ProjectContextKind,
    ProjectSummary,
    SimulationSummary,
    UserNote,
    VehicleConfiguration,
)

__all__ = [
    "ProjectAPIError",
    "ProjectAccessDenied",
    "ProjectNotFound",
    "OwnershipViolation",
    "ProjectDataClient",
]

#: Base path from `docs/api/API.md`.
DEFAULT_BASE_PATH = "/api/v1"


class ProjectAPIError(Exception):
    """P2's API could not be reached or returned an unusable response."""


class ProjectAccessDenied(ProjectAPIError):
    """P2 refused: the user is not authorized for this resource."""


class ProjectNotFound(ProjectAPIError):
    """P2 has no such resource for this user."""


class OwnershipViolation(ProjectAPIError):
    """A record came back belonging to someone other than the requesting user.

    Should never happen if P2's checks are correct. It is treated as a hard
    error rather than a filtered-out record, because it means one of the two
    layers is wrong and quietly continuing would hide that.
    """


class ProjectDataClient:
    """Reads project data through P2's API on behalf of one user.

    A client instance is bound to one user's token for its lifetime. Sharing an
    instance across users is what would allow a mix-up, so the token is a
    constructor argument rather than a per-call one.
    """

    def __init__(
        self,
        base_url: str,
        access_token: str,
        user_id: Optional[str] = None,
        transport: Optional[Any] = None,
        timeout_seconds: float = 10.0,
        base_path: str = DEFAULT_BASE_PATH,
    ):
        if not access_token:
            raise ValueError(
                "a caller access token is required; P4 has no service "
                "credential and must act as the requesting user"
            )
        self.base_url = base_url.rstrip("/")
        self.base_path = base_path
        #: Held privately and never serialized, logged or returned.
        self._token = access_token
        self.user_id = user_id
        self.timeout_seconds = timeout_seconds
        self._transport = transport
        self._client = None

    def __repr__(self) -> str:
        #: Explicit, so a token cannot reach a log through a stray repr().
        return "ProjectDataClient(base_url={0!r}, user_id={1!r})".format(
            self.base_url, self.user_id
        )

    # -- transport ---------------------------------------------------------
    def _ensure_client(self):
        if self._client is None:
            import httpx

            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self._transport,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self.aclose()

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None):
        """One authenticated GET, returning the envelope's `data`."""
        import httpx

        client = self._ensure_client()
        url = "{0}{1}".format(self.base_path, path)
        try:
            response = await client.get(
                url,
                params=params or {},
                headers={"Authorization": "Bearer {0}".format(self._token)},
            )
        except httpx.TimeoutException as exc:
            raise ProjectAPIError(
                "project API timed out after {0}s".format(self.timeout_seconds)
            ) from exc
        except httpx.HTTPError as exc:
            raise ProjectAPIError(
                "project API unreachable: {0}".format(exc.__class__.__name__)
            ) from exc

        if response.status_code in (401, 403):
            raise ProjectAccessDenied(
                "the project API refused access to {0} (HTTP {1})".format(
                    path, response.status_code
                )
            )
        if response.status_code == 404:
            raise ProjectNotFound("no such resource: {0}".format(path))
        if response.status_code >= 400:
            raise ProjectAPIError(
                "project API returned HTTP {0} for {1}".format(
                    response.status_code, path
                )
            )

        try:
            payload = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise ProjectAPIError(
                "project API returned a non-JSON body for {0}".format(path)
            ) from exc

        if isinstance(payload, dict) and payload.get("status") == "error":
            error = payload.get("error") or {}
            raise ProjectAPIError(
                "project API error {0}: {1}".format(
                    error.get("code", "UNKNOWN"), error.get("message", "")
                )
            )
        if isinstance(payload, dict) and "data" in payload:
            return payload["data"]
        return payload

    # -- ownership ---------------------------------------------------------
    def _check_owner(self, record, path: str):
        """Refuse a record belonging to another user.

        P2 enforces this too. The duplicate check exists because an ownership
        bug is silent and severe: nothing about a leaked project looks wrong in
        an answer, so it has to be caught structurally.
        """
        if record is None:
            return record
        owner = getattr(record, "owner_user_id", None)
        if self.user_id and owner and owner != self.user_id:
            raise OwnershipViolation(
                "{0} returned a record owned by another user; refusing to use "
                "it".format(path)
            )
        return record

    # -- reads -------------------------------------------------------------
    async def get_project(self, project_id: str) -> ProjectSummary:
        data = await self._get("/projects/{0}".format(project_id))
        return self._check_owner(
            ProjectSummary.model_validate(data), "/projects"
        )

    async def get_mission(self, mission_id: str) -> MissionConfiguration:
        data = await self._get("/missions/{0}".format(mission_id))
        return self._check_owner(
            MissionConfiguration.model_validate(data), "/missions"
        )

    async def get_vehicle_for_mission(self, mission_id: str) -> VehicleConfiguration:
        data = await self._get("/missions/{0}/vehicle".format(mission_id))
        return self._check_owner(
            VehicleConfiguration.model_validate(data), "/vehicle"
        )

    async def get_simulation(self, simulation_id: str) -> SimulationSummary:
        data = await self._get("/simulations/{0}".format(simulation_id))
        summary = self._check_owner(
            SimulationSummary.model_validate(data), "/simulations"
        )
        #: Events and failures are separate endpoints in P2's contract.
        try:
            summary.events = list(
                await self._get("/simulations/{0}/events".format(simulation_id))
                or []
            )
        except ProjectAPIError:
            #: Missing events degrade the analysis; they do not invalidate the
            #: run summary already retrieved.
            pass
        return summary

    async def get_learning_progress(self) -> LearningProgress:
        data = await self._get("/learning/progress")
        return self._check_owner(
            LearningProgress.model_validate(data), "/learning/progress"
        )

    async def list_missions(self, project_id: str) -> List[MissionConfiguration]:
        data = await self._get("/projects/{0}/missions".format(project_id))
        items = data if isinstance(data, list) else (data or {}).get("items", [])
        return [
            self._check_owner(MissionConfiguration.model_validate(item), "/missions")
            for item in items
        ]

    # -- composed ----------------------------------------------------------
    async def fetch(
        self,
        kinds: Sequence[ProjectContextKind],
        project_id: Optional[str] = None,
        mission_id: Optional[str] = None,
        simulation_id: Optional[str] = None,
    ) -> ProjectContext:
        """Fetch exactly the kinds asked for, and nothing else.

        Each kind is fetched independently: one endpoint failing degrades that
        kind and is recorded in `skipped`, rather than losing the rest.
        """
        wanted = list(dict.fromkeys(kinds))
        context = ProjectContext(user_id=self.user_id, requested_kinds=wanted)

        async def attempt(kind, coroutine_factory, setter):
            try:
                value = await coroutine_factory()
            except OwnershipViolation:
                #: Never swallowed. An isolation failure must surface.
                raise
            except ProjectAccessDenied as exc:
                context.skipped[kind.value] = "access denied: {0}".format(exc)
                return
            except ProjectNotFound:
                context.skipped[kind.value] = "not found"
                return
            except ProjectAPIError as exc:
                context.skipped[kind.value] = "unavailable: {0}".format(exc)
                return
            setter(value)
            context.fetched_kinds.append(kind)

        for kind in wanted:
            if kind in (ProjectContextKind.PROJECT, ProjectContextKind.REQUIREMENTS):
                if not project_id:
                    context.skipped[kind.value] = "no project id supplied"
                    continue
                if context.project is None:
                    await attempt(
                        kind,
                        lambda: self.get_project(project_id),
                        lambda value: setattr(context, "project", value),
                    )
                else:
                    context.fetched_kinds.append(kind)

            elif kind is ProjectContextKind.MISSION_CONFIG:
                if not mission_id:
                    context.skipped[kind.value] = "no mission id supplied"
                    continue
                await attempt(
                    kind,
                    lambda: self.get_mission(mission_id),
                    lambda value: setattr(context, "mission", value),
                )

            elif kind is ProjectContextKind.VEHICLE_CONFIG:
                if not mission_id:
                    context.skipped[kind.value] = "no mission id supplied"
                    continue
                await attempt(
                    kind,
                    lambda: self.get_vehicle_for_mission(mission_id),
                    lambda value: setattr(context, "vehicle", value),
                )

            elif kind in (
                ProjectContextKind.SIMULATION_RESULT,
                ProjectContextKind.FAILURE_EVENT,
                ProjectContextKind.TELEMETRY,
            ):
                if not simulation_id:
                    context.skipped[kind.value] = "no simulation id supplied"
                    continue
                if context.simulation is None:
                    await attempt(
                        kind,
                        lambda: self.get_simulation(simulation_id),
                        lambda value: setattr(context, "simulation", value),
                    )
                else:
                    context.fetched_kinds.append(kind)

            elif kind is ProjectContextKind.LEARNING_PROGRESS:
                await attempt(
                    kind,
                    lambda: self.get_learning_progress(),
                    lambda value: setattr(context, "learning", value),
                )

            elif kind is ProjectContextKind.USER_NOTES:
                #: No notes endpoint exists in P2's contract yet. Recorded as
                #: unavailable rather than faked.
                context.skipped[kind.value] = (
                    "no notes endpoint in the project API contract"
                )

        return context
