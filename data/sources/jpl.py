"""JPL Solar System Dynamics adapters.

Two sources with different jobs:

* `JplSbdbSource`     — the Small-Body Database: identifiers, orbital elements,
  uncertainties, classification and physical parameters for asteroids and comets.
* `JplHorizonsSource` — the Horizons system: ephemerides and state vectors
  computed on request for a specific target, observer, epoch and frame.

These are the project's **primary scientific authority** for small-body orbits
and for ephemerides respectively. Where any other source disagrees with JPL on
those quantities, JPL wins.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts.provenance import SourceType

from ..normalization.parsing import clean_text
from .base import (
    Capability,
    SourceInfo,
    SourceQuery,
    SourceRecord,
    SourceResultPage,
    SpaceDataSource,
)
from .config import ProviderConfig, RateLimitConfig, RetryConfig
from .errors import SourceNotFoundError, SourceResponseError

__all__ = ["JplSbdbSource", "JplHorizonsSource", "HorizonsRequest"]

_JPL_ATTRIBUTION = "NASA/JPL Solar System Dynamics"

#: JPL asks API users to keep request rates modest rather than publishing a hard
#: numeric quota. One request per second is well inside anything documented.
_JPL_POLICY = (
    "JPL's SSD/CNEOS API guidance asks for reasonable request rates rather than "
    "publishing a fixed quota; requests are self-limited to roughly one per second."
)


class JplSbdbSource(SpaceDataSource):
    """JPL Small-Body Database lookup and query."""

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="jpl_sbdb",
            base_url="https://ssd-api.jpl.nasa.gov",
            timeout_seconds=30.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=1.0),
            rate_limit=RateLimitConfig(
                requests_per_second=1.0,
                max_concurrent=2,
                policy_note=_JPL_POLICY,
            ),
            docs_url="https://ssd-api.jpl.nasa.gov/doc/sbdb.html",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="jpl_sbdb",
            display_name="JPL Small-Body Database",
            source_type=SourceType.PRIMARY_SCIENTIFIC,
            authority_note=(
                "Primary authority for small-body orbital elements, uncertainties "
                "and physical parameters."
            ),
            provider_organization="NASA/JPL",
            base_url=self.config.base_url,
            docs_url="https://ssd-api.jpl.nasa.gov/doc/sbdb.html",
            capabilities=[
                Capability.SEARCH,
                Capability.FETCH_BY_ID,
                Capability.ORBITAL_ELEMENTS,
                Capability.PHYSICAL_PARAMETERS,
                Capability.CLOSE_APPROACHES,
            ],
            provides=[
                "small-body identifiers (SPK-ID, designation, number)",
                "osculating heliocentric orbital elements with uncertainties",
                "orbit covariance where published",
                "orbit classification and fit quality",
                "physical parameters (diameter, albedo, H, rotation period)",
            ],
            does_not_provide=[
                "planets, moons or stars",
                "artificial satellites",
                "individual astrometric observations (use the MPC)",
                "time-series ephemerides (use Horizons)",
            ],
            license="Public domain (U.S. Government work)",
            attribution=_JPL_ATTRIBUTION,
            rate_limit_note=_JPL_POLICY,
            implemented=True,
        )

    def health_probe(self):
        # Cheapest meaningful call: look up a body that has existed since 1801.
        return ("/sbdb.api", {"sstr": "Ceres"})

    SBDB_PATH = "/sbdb.api"
    SBDB_QUERY_PATH = "/sbdb_query.api"

    async def fetch_by_id(
        self,
        identifier: str,
        physical_parameters: bool = True,
        covariance: bool = True,
        discovery: bool = True,
        full_precision: bool = True,
        **kwargs
    ) -> Optional[SourceRecord]:
        """Look up one small body by designation, name, SPK-ID or number.

        Full precision and covariance are requested by default: truncating an
        orbit solution to display precision would make the stored uncertainties
        meaningless, and covariance is the main reason to consult SBDB at all.
        """
        self.require_capability(Capability.FETCH_BY_ID)
        search = clean_text(identifier)
        if not search:
            raise SourceResponseError(
                "a small-body lookup needs a designation or name", source_name=self.name
            )

        params: Dict[str, Any] = {"sstr": search}
        if physical_parameters:
            params["phys-par"] = "1"
        if covariance:
            params["cov"] = "mat"
        if discovery:
            params["discovery"] = "1"
        if full_precision:
            params["full-prec"] = "1"

        response = await self._client.get(self.SBDB_PATH, params=params)
        payload = response.json()

        # SBDB answers an unmatched lookup with a 200 and a message, not a 404.
        if "object" not in payload:
            message = payload.get("message") or payload.get("code") or "no object returned"
            if payload.get("list") or payload.get("count"):
                raise SourceResponseError(
                    "ambiguous designation {0!r}: SBDB matched multiple objects".format(
                        search
                    ),
                    source_name=self.name,
                    url=response.url,
                )
            raise SourceNotFoundError(
                "SBDB has no object matching {0!r} ({1})".format(search, message),
                source_name=self.name,
                url=response.url,
            )

        obj = payload["object"]
        version = (payload.get("signature") or {}).get("version")
        return SourceRecord(
            source_name=self.name,
            source_record_id=clean_text(obj.get("spkid")) or clean_text(obj.get("des")),
            payload=payload,
            source_reference=self.build_source_reference(
                response,
                record_id=clean_text(obj.get("spkid")),
                version=version,
            ),
            retrieved_at=response.retrieved_at,
        )

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Look up a single body by name or designation.

        SBDB's lookup endpoint resolves one object; it is not a free-text
        search engine. `sbdb_query.api` exists for constraint-based queries and
        is a separate, deliberately unexposed surface until a caller needs it.
        """
        self.require_capability(Capability.SEARCH)
        term = clean_text(query.identifier) or clean_text(query.text)
        if not term:
            raise SourceResponseError(
                "an SBDB search needs a designation or name", source_name=self.name
            )
        try:
            record = await self.fetch_by_id(term)
        except SourceNotFoundError:
            return SourceResultPage(
                source_name=self.name,
                records=[],
                total_available=0,
                offset=query.offset,
                unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            )
        return SourceResultPage(
            source_name=self.name,
            records=[record] if record else [],
            total_available=1 if record else 0,
            offset=query.offset,
            unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            retrieved_at=record.retrieved_at,
        )


class JplHorizonsSource(SpaceDataSource):
    """JPL Horizons ephemeris service.

    Horizons *computes* a result for the request it is given, so the request is
    part of the result: target, observer/centre, epoch range, step size,
    reference frame and units all have to be stored alongside the numbers, or
    the numbers cannot be interpreted or reproduced.
    """

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="jpl_horizons",
            base_url="https://ssd.jpl.nasa.gov",
            #: Horizons computes on demand and can be slow for long spans.
            timeout_seconds=60.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=2.0, max_backoff_seconds=30.0),
            rate_limit=RateLimitConfig(
                requests_per_second=0.5,
                max_concurrent=1,
                policy_note=(
                    _JPL_POLICY
                    + " Horizons requests are computationally expensive, so they are "
                    "limited further and never issued concurrently."
                ),
            ),
            docs_url="https://ssd-api.jpl.nasa.gov/doc/horizons.html",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="jpl_horizons",
            display_name="JPL Horizons",
            source_type=SourceType.PRIMARY_SCIENTIFIC,
            authority_note=(
                "Primary authority for ephemerides and state vectors. Results are "
                "computed for the exact request made and are only meaningful together "
                "with that request's frame, centre and epoch."
            ),
            provider_organization="NASA/JPL",
            base_url=self.config.base_url,
            docs_url="https://ssd-api.jpl.nasa.gov/doc/horizons.html",
            capabilities=[Capability.EPHEMERIS, Capability.FETCH_BY_ID],
            provides=[
                "state vectors (position and velocity) for a target and centre",
                "observer tables and orbital-element output",
                "explicit reference frame, time scale and units",
            ],
            does_not_provide=[
                "a searchable catalogue",
                "observations",
                "physical parameters as a primary product",
            ],
            license="Public domain (U.S. Government work)",
            attribution=_JPL_ATTRIBUTION,
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    HORIZONS_PATH = "/api/horizons.api"

    def health_probe(self):
        return (
            self.HORIZONS_PATH,
            {"format": "json", "COMMAND": "'499'", "OBJ_DATA": "'NO'",
             "MAKE_EPHEM": "'NO'"},
        )

    async def fetch_vectors(self, request: "HorizonsRequest") -> SourceRecord:
        """Request state vectors for one target relative to one centre.

        The whole request is echoed into the returned record, because a Horizons
        result is only interpretable — and only reproducible — alongside the
        target, centre, frame, units and epoch range that produced it.
        """
        self.require_capability(Capability.EPHEMERIS)
        params = request.to_params()

        response = await self._client.get(self.HORIZONS_PATH, params=params)
        payload = response.json()

        if "error" in payload:
            raise SourceResponseError(
                "Horizons rejected the request: {0}".format(
                    str(payload["error"]).strip()[:300]
                ),
                source_name=self.name,
                url=response.url,
            )
        result = payload.get("result")
        if not result:
            raise SourceResponseError(
                "Horizons response contains no result block",
                source_name=self.name,
                url=response.url,
            )
        if "$$SOE" not in result:
            raise SourceResponseError(
                "Horizons result contains no ephemeris block ($$SOE marker missing); "
                "the request may have set MAKE_EPHEM='NO'",
                source_name=self.name,
                url=response.url,
            )

        return SourceRecord(
            source_name=self.name,
            source_record_id=request.command.strip("'"),
            payload={"result": result, "request": params},
            source_reference=self.build_source_reference(
                response,
                record_id=request.command.strip("'"),
                version=(payload.get("signature") or {}).get("version"),
            ),
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch vectors for `identifier` over the requested window."""
        request = HorizonsRequest(command=identifier, **kwargs)
        return await self.fetch_vectors(request)


class HorizonsRequest(BaseModel):
    """A Horizons query, stored verbatim alongside its result.

    Field names mirror Horizons' own parameter names so a stored request can be
    replayed against the API without translation. Horizons requires string
    values to be single-quoted, which `to_params` applies.
    """

    model_config = ConfigDict(extra="forbid")

    #: Target body. Horizons IDs: '499' Mars, '301' Moon, 'Ceres'.
    command: str = Field(min_length=1)
    #: Observer/centre. '500@0' is the solar-system barycentre,
    #: '500@399' the Earth's centre, '@sun' the Sun's centre.
    center: str = "500@0"
    start_time: str = Field(min_length=1)
    stop_time: str = Field(min_length=1)
    step_size: str = "1 d"
    #: 'VECTORS' for Cartesian states, 'ELEMENTS' for osculating elements,
    #: 'OBSERVER' for an observer table.
    ephem_type: str = "VECTORS"
    #: 'ECLIPTIC' or 'FRAME' (equatorial).
    ref_plane: str = "ECLIPTIC"
    ref_system: str = "ICRF"
    #: 'KM-S' or 'AU-D'. Stored so the parser never has to guess units.
    out_units: str = "KM-S"
    #: '2' returns position and velocity.
    vec_table: str = "2"
    obj_data: str = "NO"

    @field_validator("command", "center", "start_time", "stop_time", "step_size")
    @classmethod
    def _clean(cls, value: str) -> str:
        text = clean_text(value)
        if not text:
            raise ValueError("value must not be blank")
        return text.strip("'")

    @model_validator(mode="after")
    def _check(self) -> "HorizonsRequest":
        if self.ephem_type not in ("VECTORS", "ELEMENTS", "OBSERVER", "APPROACH"):
            raise ValueError("unsupported ephem_type {0!r}".format(self.ephem_type))
        if self.out_units not in ("KM-S", "AU-D", "KM-D"):
            raise ValueError("unsupported out_units {0!r}".format(self.out_units))
        if self.ref_plane not in ("ECLIPTIC", "FRAME", "BODY EQUATOR"):
            raise ValueError("unsupported ref_plane {0!r}".format(self.ref_plane))
        return self

    def to_params(self) -> Dict[str, str]:
        """Horizons query parameters, with the quoting the API requires."""
        def quoted(value: str) -> str:
            return "'{0}'".format(value)

        return {
            "format": "json",
            "COMMAND": quoted(self.command),
            "CENTER": quoted(self.center),
            "MAKE_EPHEM": quoted("YES"),
            "EPHEM_TYPE": quoted(self.ephem_type),
            "START_TIME": quoted(self.start_time),
            "STOP_TIME": quoted(self.stop_time),
            "STEP_SIZE": quoted(self.step_size),
            "REF_PLANE": quoted(self.ref_plane),
            "REF_SYSTEM": quoted(self.ref_system),
            "OUT_UNITS": quoted(self.out_units),
            "VEC_TABLE": quoted(self.vec_table),
            "OBJ_DATA": quoted(self.obj_data),
        }
