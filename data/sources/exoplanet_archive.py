"""NASA Exoplanet Archive adapter.

The archive's planetary-systems tables are served through a TAP (Table Access
Protocol) endpoint and queried with ADQL. Two tables matter here:

* `ps`         — one row per planet *per published reference*, so a planet can
  appear many times with different parameter values.
* `pscomppars` — one composite row per planet, assembled by the archive from the
  literature. Convenient, but explicitly a composite rather than a single
  self-consistent published solution.

Query safety is a first-class concern: ADQL is SQL-shaped, and the archive is a
public service. No user-supplied SQL fragment reaches it. See
`data/sources/adql.py`.
"""

import re
from typing import Any, Dict, List, Optional

from contracts.provenance import SourceType

from ..normalization.parsing import clean_text
from .adql import AdqlError, AdqlQuery, Comparison, Predicate
from .base import (
    Capability,
    SourceInfo,
    SourceQuery,
    SourceRecord,
    SourceResultPage,
    SpaceDataSource,
)
from .config import ProviderConfig, RateLimitConfig, RetryConfig
from .errors import SourceResponseError

__all__ = [
    "ExoplanetArchiveSource",
    "PS_TABLE",
    "PSCOMPPARS_TABLE",
    "PS_COLUMNS",
    "PSCOMPPARS_COLUMNS",
    "DEFAULT_PLANET_COLUMNS",
]

PS_TABLE = "ps"
PSCOMPPARS_TABLE = "pscomppars"

#: Columns this project reads. Deliberately a subset: an allow-list is only
#: useful if it is smaller than the table.
#:
#: `*err1` is the upper error bar and `*err2` the lower (published negative).
DEFAULT_PLANET_COLUMNS = (
    "pl_name",
    "hostname",
    "pl_rade", "pl_radeerr1", "pl_radeerr2",
    "pl_bmasse", "pl_bmasseerr1", "pl_bmasseerr2",
    "pl_orbper", "pl_orbpererr1", "pl_orbpererr2",
    "pl_orbsmax", "pl_orbsmaxerr1", "pl_orbsmaxerr2",
    "pl_orbeccen", "pl_orbeccenerr1", "pl_orbeccenerr2",
    "pl_orbincl",
    "pl_eqt",
    "pl_insol",
    "disc_year",
    "discoverymethod",
    "disc_facility",
    "sy_pnum",
    "st_teff",
    "st_rad",
    "st_mass",
    "st_met",
    "st_metratio",
    "st_spectype",
    "sy_dist",
    "sy_vmag",
)

#: `ps` additionally carries per-row disposition and provenance columns, because
#: it holds one row per published reference rather than one row per planet.
PS_ONLY_COLUMNS = (
    "soltype",
    "default_flag",
    "pl_controv_flag",
    "pl_refname",
    "st_refname",
    "sy_refname",
    "rowupdate",
    "pl_pubdate",
    "releasedate",
)

PS_COLUMNS = tuple(DEFAULT_PLANET_COLUMNS) + PS_ONLY_COLUMNS
PSCOMPPARS_COLUMNS = tuple(DEFAULT_PLANET_COLUMNS)

#: Allow-list per table, checked before a query is sent.
TABLE_COLUMNS = {
    PS_TABLE: PS_COLUMNS,
    PSCOMPPARS_TABLE: PSCOMPPARS_COLUMNS,
}

#: The archive reports query errors as a VOTable document, not JSON.
_VOTABLE_ERROR = re.compile(
    r'QUERY_STATUS"\s*value="ERROR"\s*>\s*(?P<message>.*?)\s*</INFO>', re.DOTALL
)


class ExoplanetArchiveSource(SpaceDataSource):
    """NASA Exoplanet Archive TAP service."""

    TAP_SYNC_PATH = "/TAP/sync"

    def __init__(self, *args, **kwargs):
        super(ExoplanetArchiveSource, self).__init__(*args, **kwargs)
        #: Held so `search` can attach provenance from the response that
        #: produced the rows, rather than fabricating a new one.
        self._last_response = None

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="nasa_exoplanet_archive",
            base_url="https://exoplanetarchive.ipac.caltech.edu",
            #: TAP queries against `ps` can be slow when the predicate is broad.
            timeout_seconds=60.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=2.0),
            rate_limit=RateLimitConfig(
                requests_per_second=0.5,
                max_concurrent=1,
                policy_note=(
                    "The archive asks that queries be specific and that bulk needs be "
                    "met by downloading a full table rather than by many small "
                    "queries. Requests are self-limited and never concurrent."
                ),
            ),
            docs_url="https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="nasa_exoplanet_archive",
            display_name="NASA Exoplanet Archive",
            source_type=SourceType.PRIMARY_SCIENTIFIC,
            authority_note=(
                "Sole authority for exoplanet parameters and dispositions in this "
                "project. Candidate dispositions are never promoted to confirmed "
                "locally."
            ),
            provider_organization="NASA Exoplanet Science Institute / IPAC",
            base_url=self.config.base_url,
            docs_url="https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html",
            capabilities=[
                Capability.SEARCH,
                Capability.FETCH_BY_ID,
                Capability.EXOPLANETS,
                Capability.PHYSICAL_PARAMETERS,
                Capability.ORBITAL_ELEMENTS,
            ],
            provides=[
                "confirmed planet parameters (radius, mass, period, semi-major axis)",
                "eccentricity and inclination where measured",
                "host-star parameters",
                "discovery method, year and facility",
                "per-parameter reference and asymmetric uncertainties",
            ],
            does_not_provide=[
                "Solar System bodies",
                "artificial satellites",
                "ephemerides",
                "raw photometry or light curves",
            ],
            attribution=(
                "This research has made use of the NASA Exoplanet Archive, which is "
                "operated by the California Institute of Technology, under contract "
                "with the National Aeronautics and Space Administration under the "
                "Exoplanet Exploration Program."
            ),
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        return (
            self.TAP_SYNC_PATH,
            {"query": "select count(*) from ps", "format": "json"},
        )

    # -- query execution ---------------------------------------------------
    async def run_query(self, query: AdqlQuery) -> List[Dict[str, Any]]:
        """Validate, send and parse one ADQL query.

        The query is checked against the table's column allow-list before it
        leaves this process, so an unknown column is a local error rather than
        an `ORA-00904` from a shared public service.
        """
        allowed = TABLE_COLUMNS.get(query.table)
        if allowed is None:
            raise AdqlError(
                "table {0!r} is not in the allow-list; permitted tables are "
                "{1}".format(query.table, ", ".join(sorted(TABLE_COLUMNS)))
            )
        query.validate_against(allowed)

        response = await self._client.get(
            self.TAP_SYNC_PATH,
            params={"query": query.render(), "format": "json"},
            #: The archive answers a bad query with 400 and a VOTable body, so
            #: 400 is accepted here in order to surface its message.
            expected_status=(200, 400),
        )

        if response.status_code == 400 or "VOTABLE" in response.text[:200].upper():
            match = _VOTABLE_ERROR.search(response.text)
            detail = match.group("message").strip() if match else response.text[:200]
            raise SourceResponseError(
                "the Exoplanet Archive rejected the query: {0}".format(detail),
                source_name=self.name,
                status_code=response.status_code,
                url=response.url,
            )

        payload = response.json()
        if not isinstance(payload, list):
            raise SourceResponseError(
                "expected a JSON array of rows from the TAP service",
                source_name=self.name,
                url=response.url,
            )
        self._last_response = response
        return payload

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Find planets by name, host star or discovery year.

        Defaults to `pscomppars`, the archive's one-row-per-planet composite
        table. Pass `extra={"table": "ps"}` for the per-reference table, which
        is where `soltype` and `default_flag` live.
        """
        self.require_capability(Capability.SEARCH)

        table = str(query.extra.get("table", PSCOMPPARS_TABLE)).lower()
        if table not in TABLE_COLUMNS:
            raise AdqlError(
                "table {0!r} is not in the allow-list; permitted tables are "
                "{1}".format(table, ", ".join(sorted(TABLE_COLUMNS)))
            )

        predicates: List[Predicate] = []
        if query.identifier:
            predicates.append(Predicate(column="pl_name", value=clean_text(query.identifier)))
        elif query.text:
            #: `like` with a caller-supplied pattern is still safe: the value is
            #: quoted as a literal, so `%` is a wildcard but a quote is not a
            #: statement terminator.
            predicates.append(
                Predicate(
                    column="pl_name",
                    operator=Comparison.LIKE,
                    value="%{0}%".format(clean_text(query.text)),
                )
            )
        if query.extra.get("hostname"):
            predicates.append(
                Predicate(column="hostname", value=str(query.extra["hostname"]))
            )
        if query.extra.get("discovery_year"):
            predicates.append(
                Predicate(column="disc_year", value=int(query.extra["discovery_year"]))
            )
        if query.extra.get("default_only") and table == PS_TABLE:
            predicates.append(Predicate(column="default_flag", value=1))

        if not predicates:
            raise SourceResponseError(
                "an exoplanet search needs a planet name, host star or discovery "
                "year; unfiltered table scans are refused",
                source_name=self.name,
            )

        adql = AdqlQuery(
            table=table,
            columns=list(TABLE_COLUMNS[table]),
            predicates=predicates,
            limit=query.limit,
            order_by="pl_name",
        )
        rows = await self.run_query(adql)
        response = self._last_response

        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=clean_text(row.get("pl_name")),
                payload=dict(row, _table=table),
                source_reference=self.build_source_reference(
                    response, record_id=clean_text(row.get("pl_name"))
                ),
                retrieved_at=response.retrieved_at,
            )
            for row in rows
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            total_available=len(records),
            offset=query.offset,
            unsupported_filters=self._unsupported(
                query,
                ["text", "identifier", "table", "hostname", "discovery_year",
                 "default_only"],
            ),
            query_echo={"adql": adql.render(), "table": table},
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(
        self, identifier: str, table: str = PSCOMPPARS_TABLE, **kwargs
    ) -> Optional[SourceRecord]:
        """Fetch one planet by its exact archive name, e.g. `Kepler-22 b`."""
        self.require_capability(Capability.FETCH_BY_ID)
        name = clean_text(identifier)
        if not name:
            raise SourceResponseError(
                "a planet lookup needs a name", source_name=self.name
            )
        page = await self.search(
            SourceQuery(identifier=name, limit=1, extra={"table": table})
        )
        return page.records[0] if page.records else None
