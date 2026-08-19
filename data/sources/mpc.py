"""Minor Planet Center adapters.

The MPC is the IAU's clearing house for minor-planet astrometry. Two distinct
products, kept in two adapters because conflating them is a scientific error:

* `MpcOrbitsSource`       — fitted orbital elements with uncertainty/covariance.
* `MpcObservationsSource` — individual astrometric observations.

An observation is a measurement of where an object appeared from one site at one
instant. It is **not** an orbit. Only the Orbits API publishes orbital
solutions, and only its output may become an `OrbitRecord`.
"""

from typing import Any, Dict, List, Optional, Sequence

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

__all__ = [
    "MPC_BASE_URL",
    "MpcOrbitsSource",
    "MpcObservationsSource",
    "OBSERVATION_FORMATS",
]

#: Output formats the Observations API accepts. `ADES_DF` returns structured
#: records; `OBS80` and `XML` return the punched-card and ADES-XML renditions.
#: Structured records are used, because parsing a fixed-column format we do not
#: control is an avoidable source of silent error.
OBSERVATION_FORMATS = ("ADES_DF", "OBS80", "OBS_DF", "XML")

#: Documented host for the MPC's data APIs.
MPC_BASE_URL = "https://data.minorplanetcenter.net"

_MPC_ATTRIBUTION = "IAU Minor Planet Center"

_MPC_POLICY = (
    "The MPC asks users to query considerately and to avoid bulk scraping of the "
    "API where a published data file would serve. Requests are self-limited to "
    "roughly one per second with no concurrency."
)


def _mpc_config(name: str) -> ProviderConfig:
    return ProviderConfig(
        name=name,
        base_url=MPC_BASE_URL,
        timeout_seconds=45.0,
        retry=RetryConfig(max_attempts=3, backoff_factor=1.0),
        rate_limit=RateLimitConfig(
            requests_per_second=1.0,
            max_concurrent=1,
            policy_note=_MPC_POLICY,
        ),
        docs_url="https://minorplanetcenter.net/",
    )


class MpcOrbitsSource(SpaceDataSource):
    """MPC Orbits API — documented endpoint `/api/get-orb`.

    Publishes orbital elements together with uncertainty and, where available,
    covariance. That covariance is the reason to prefer the MPC over other
    sources for asteroid orbit *uncertainty* specifically.
    """

    ORBITS_PATH = "/api/get-orb"

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return _mpc_config("mpc_orbits")

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="mpc_orbits",
            display_name="Minor Planet Center Orbits API",
            source_type=SourceType.PRIMARY_SCIENTIFIC,
            authority_note=(
                "Primary authority for minor-planet orbit uncertainty and covariance. "
                "Cross-checked against JPL SBDB for the elements themselves."
            ),
            provider_organization="IAU Minor Planet Center",
            base_url=self.config.base_url,
            docs_url="https://minorplanetcenter.net/",
            capabilities=[
                Capability.FETCH_BY_ID,
                Capability.SEARCH,
                Capability.ORBITAL_ELEMENTS,
            ],
            provides=[
                "orbital elements for numbered and unnumbered minor planets",
                "element uncertainties and covariance where published",
                "epoch and orbit-fit metadata",
                "packed and unpacked designations",
            ],
            does_not_provide=[
                "ephemerides",
                "planets, moons, stars or artificial satellites",
                "physical parameters as a primary product",
            ],
            attribution=_MPC_ATTRIBUTION,
            rate_limit_note=_MPC_POLICY,
            implemented=True,
        )

    def health_probe(self):
        return (self.ORBITS_PATH, {"desig": "Ceres", "json": 1})

    async def health_check(self):
        """Probe with the JSON body the API requires.

        The MPC data APIs accept a GET carrying a JSON body; a plain GET is
        answered with a content-type error, so the default probe would report a
        healthy provider as broken.
        """
        try:
            response = await self._client.request(
                "GET", self.ORBITS_PATH, json_body={"desig": "Ceres"}
            )
        except Exception as exc:  # noqa: BLE001 - health checks report, never raise
            from .base import HealthStatus

            return HealthStatus(
                source_name=self.name,
                healthy=False,
                detail="{0}: {1}".format(exc.__class__.__name__, exc),
            )
        from .base import HealthStatus

        return HealthStatus(
            source_name=self.name,
            healthy=True,
            status_code=response.status_code,
            latency_seconds=response.elapsed_seconds,
            detail="reachable",
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch the MPC orbit solution for one designation.

        Example designations: `Ceres`, `101955` (Bennu), `2024 YR4`.
        """
        self.require_capability(Capability.FETCH_BY_ID)
        designation = clean_text(identifier)
        if not designation:
            raise SourceResponseError(
                "an orbit lookup needs a designation", source_name=self.name
            )

        response = await self._client.request(
            "GET", self.ORBITS_PATH, json_body={"desig": designation}
        )
        payload = response.json()
        entries = _first_populated(payload, "mpc_orb")
        if not entries:
            raise SourceNotFoundError(
                "the MPC has no orbit solution for {0!r}".format(designation),
                source_name=self.name,
                url=response.url,
            )

        orbit = entries[0] if isinstance(entries, list) else entries
        designation_data = orbit.get("designation_data") or {}
        record_id = (
            clean_text(designation_data.get("permid"))
            or clean_text(designation_data.get("unpacked_primary_provisional_designation"))
            or designation
        )
        version = (orbit.get("software_data") or {}).get("mpcorb_version")
        return SourceRecord(
            source_name=self.name,
            source_record_id=record_id,
            payload=orbit,
            source_reference=self.build_source_reference(
                response, record_id=record_id, version=clean_text(version)
            ),
            retrieved_at=response.retrieved_at,
        )

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Resolve one designation. The Orbits API is a lookup, not a search."""
        self.require_capability(Capability.SEARCH)
        term = clean_text(query.identifier) or clean_text(query.text)
        if not term:
            raise SourceResponseError(
                "an MPC orbit search needs a designation", source_name=self.name
            )
        try:
            record = await self.fetch_by_id(term)
        except SourceNotFoundError:
            return SourceResultPage(
                source_name=self.name,
                records=[],
                total_available=0,
                unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            )
        return SourceResultPage(
            source_name=self.name,
            records=[record],
            total_available=1,
            unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            retrieved_at=record.retrieved_at,
        )


def _first_populated(payload: Any, key: str) -> Optional[Any]:
    """Find the first non-empty `key` in an MPC response.

    The API answers with a list of result objects, several of which are empty
    placeholders for element sets it did not compute.
    """
    candidates: Sequence
    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = [payload]
    else:
        return None
    for entry in candidates:
        if not isinstance(entry, dict):
            continue
        value = entry.get(key)
        if value:
            return value
    return None


class MpcObservationsSource(SpaceDataSource):
    """MPC Observations API — documented endpoint `/api/get-obs`.

    Every record from this adapter becomes an `Observation`, never an
    `OrbitRecord`. The canonical `Observation` model has no fields for orbital
    elements, so the distinction is enforced by the type system rather than by
    convention.
    """

    OBSERVATIONS_PATH = "/api/get-obs"

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return _mpc_config("mpc_observations")

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="mpc_observations",
            display_name="Minor Planet Center Observations API",
            source_type=SourceType.PRIMARY_SCIENTIFIC,
            authority_note=(
                "Sole authority for minor-planet astrometric observations. "
                "Observations are measurements, never orbital solutions."
            ),
            provider_organization="IAU Minor Planet Center",
            base_url=self.config.base_url,
            docs_url="https://minorplanetcenter.net/",
            capabilities=[
                Capability.FETCH_BY_ID,
                Capability.SEARCH,
                Capability.OBSERVATIONS,
            ],
            provides=[
                "individual astrometric observations",
                "observatory codes and observation times",
                "reported magnitudes and bands",
                "submission and catalogue metadata",
            ],
            does_not_provide=[
                "orbital elements",
                "orbit determinations of any kind",
                "ephemerides",
            ],
            attribution=_MPC_ATTRIBUTION,
            rate_limit_note=_MPC_POLICY,
            implemented=True,
        )

    def health_probe(self):
        return (self.OBSERVATIONS_PATH, {"desig": "Ceres", "json": 1})

    async def health_check(self):
        from .base import HealthStatus

        try:
            response = await self._client.request(
                "GET",
                self.OBSERVATIONS_PATH,
                json_body={"desigs": ["Ceres"], "output_format": ["OBS_DF"]},
            )
        except Exception as exc:  # noqa: BLE001 - health checks report, never raise
            return HealthStatus(
                source_name=self.name,
                healthy=False,
                detail="{0}: {1}".format(exc.__class__.__name__, exc),
            )
        return HealthStatus(
            source_name=self.name,
            healthy=True,
            status_code=response.status_code,
            latency_seconds=response.elapsed_seconds,
            detail="reachable",
        )

    async def fetch_by_id(
        self, identifier: str, output_format: str = "ADES_DF", **kwargs
    ) -> Optional[SourceRecord]:
        """Fetch the observations the MPC holds for one designation.

        Returns the whole observation set as one `SourceRecord`; the normalizer
        expands it into individual `Observation` records. The MPC does not
        paginate this endpoint, so an object with a long arc returns a large
        payload — callers should expect that and cache accordingly.
        """
        self.require_capability(Capability.FETCH_BY_ID)
        designation = clean_text(identifier)
        if not designation:
            raise SourceResponseError(
                "an observation lookup needs a designation", source_name=self.name
            )
        if output_format not in OBSERVATION_FORMATS:
            raise SourceResponseError(
                "unsupported observation format {0!r}; the API accepts {1}".format(
                    output_format, ", ".join(OBSERVATION_FORMATS)
                ),
                source_name=self.name,
            )

        response = await self._client.request(
            "GET",
            self.OBSERVATIONS_PATH,
            json_body={"desigs": [designation], "output_format": [output_format]},
        )
        payload = response.json()
        rows = _first_populated(payload, output_format)
        if not rows:
            raise SourceNotFoundError(
                "the MPC returned no observations for {0!r}".format(designation),
                source_name=self.name,
                url=response.url,
            )

        return SourceRecord(
            source_name=self.name,
            source_record_id=designation,
            payload={"format": output_format, "designation": designation, "rows": rows},
            source_reference=self.build_source_reference(response, record_id=designation),
            retrieved_at=response.retrieved_at,
        )

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Resolve observations for one designation."""
        self.require_capability(Capability.SEARCH)
        term = clean_text(query.identifier) or clean_text(query.text)
        if not term:
            raise SourceResponseError(
                "an MPC observation search needs a designation", source_name=self.name
            )
        try:
            record = await self.fetch_by_id(term)
        except SourceNotFoundError:
            return SourceResultPage(
                source_name=self.name,
                records=[],
                total_available=0,
                unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            )
        return SourceResultPage(
            source_name=self.name,
            records=[record],
            total_available=len(record.payload.get("rows") or []),
            unsupported_filters=self._unsupported(query, ["text", "identifier"]),
            retrieved_at=record.retrieved_at,
        )
