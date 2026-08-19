"""CelesTrak adapter — current satellite orbital elements.

**Authority.** CelesTrak is a *secondary operational* source, not a primary
scientific one. Its GP element sets are the right thing for "where is the ISS
roughly now"; they are not comparable to a JPL ephemeris and must never be
presented as such. Records are tagged `SECONDARY_OPERATIONAL_ORBIT_FEED`.

**Element theory.** GP/OMM data carries SGP4 mean elements in the TEME frame.
Those are not osculating Keplerian elements: feeding them to a two-body
propagator, or averaging them with JPL elements, produces silent nonsense. The
canonical model records `ElementTheory.SGP4_MEAN` and refuses the combination.

**Update policy.** CelesTrak's current guidance is that GP data updates every
two hours, and that users should retrieve only what they need and only once per
update. Both halves are honoured: the freshness policy sets a two-hour cache TTL,
and the adapter offers targeted queries rather than whole-catalogue pulls.
"""

from typing import Any, Dict, List, Optional

from contracts.provenance import SourceType

from ..normalization.parsing import clean_text, parse_datetime
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

__all__ = ["CelestrakSource", "PROVENANCE_LABEL", "GP_FORMATS", "GP_QUERY_KEYS"]

#: Response formats the GP endpoint supports. JSON is used because it is the
#: OMM field set in a form we do not have to parse by column position.
GP_FORMATS = ("JSON", "JSON-PRETTY", "XML", "KVN", "CSV", "TLE", "3LE")

#: Query keys the GP endpoint accepts. Exactly one may be used per request.
GP_QUERY_KEYS = ("CATNR", "INTDES", "GROUP", "NAME", "SPECIAL")

#: The label every CelesTrak-derived orbit record carries, so the distinction
#: from a primary scientific source survives into storage and into the UI.
PROVENANCE_LABEL = "SECONDARY_OPERATIONAL_ORBIT_FEED"


class CelestrakSource(SpaceDataSource):
    """CelesTrak GP/OMM query interface."""

    GP_PATH = "/NORAD/elements/gp.php"

    def __init__(self, *args, **kwargs):
        super(CelestrakSource, self).__init__(*args, **kwargs)
        self._last_response = None

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="celestrak_gp",
            base_url="https://celestrak.org",
            timeout_seconds=30.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=1.0),
            rate_limit=RateLimitConfig(
                requests_per_second=0.5,
                max_concurrent=1,
                policy_note=(
                    "CelesTrak guidance: GP data is updated every two hours; retrieve "
                    "only what you need and only once per update. Enforced by a "
                    "two-hour cache TTL in the freshness policy plus a low request rate."
                ),
            ),
            docs_url="https://celestrak.org/NORAD/documentation/gp-data-formats.php",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="celestrak_gp",
            display_name="CelesTrak GP/OMM",
            source_type=SourceType.SECONDARY_OPERATIONAL,
            authority_note=(
                "Secondary operational orbit feed. Suitable for current satellite "
                "element sets; NOT equivalent to a primary scientific source such as "
                "JPL, and not a precise ephemeris."
            ),
            provider_organization="CelesTrak",
            base_url=self.config.base_url,
            docs_url="https://celestrak.org/NORAD/documentation/gp-data-formats.php",
            capabilities=[
                Capability.SEARCH,
                Capability.FETCH_BY_ID,
                Capability.ORBITAL_ELEMENTS,
            ],
            provides=[
                "current SGP4 mean elements (GP) for catalogued satellites",
                "OMM-formatted element sets",
                "NORAD catalog number and international designator",
                "drag terms (B*, mean motion derivatives)",
                "constellation and special-interest group feeds",
            ],
            does_not_provide=[
                "precise ephemerides",
                "osculating Keplerian elements",
                "natural small bodies",
                "covariance",
            ],
            license="CelesTrak data, used under its published terms",
            attribution="Orbital data from CelesTrak (celestrak.org)",
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        # Single-object query — the smallest useful request the API supports.
        return (self.GP_PATH, {"CATNR": "25544", "FORMAT": "json"})

    async def _gp_query(self, key: str, value: str) -> List[Dict[str, Any]]:
        """Issue one GP query and return the OMM rows.

        Exactly one selector is sent per request. CelesTrak asks users to
        retrieve only what they need, so there is deliberately no "fetch the
        whole catalogue" path here.
        """
        if key not in GP_QUERY_KEYS:
            raise SourceResponseError(
                "unsupported GP query key {0!r}; the endpoint accepts {1}".format(
                    key, ", ".join(GP_QUERY_KEYS)
                ),
                source_name=self.name,
            )
        response = await self._client.get(
            self.GP_PATH, params={key: value, "FORMAT": "JSON"}
        )
        text = response.text.strip()

        # A miss is answered with a plain-text notice and a 200, not a 404.
        if not text or text.lower().startswith("no gp data found"):
            raise SourceNotFoundError(
                "CelesTrak has no GP data for {0}={1!r}".format(key, value),
                source_name=self.name,
                url=response.url,
            )

        payload = response.json()
        if not isinstance(payload, list):
            raise SourceResponseError(
                "expected a JSON array of OMM records from the GP endpoint",
                source_name=self.name,
                url=response.url,
            )
        self._last_response = response
        return payload

    def _to_records(self, rows) -> List[SourceRecord]:
        response = self._last_response
        records = []
        for row in rows:
            catalog_number = row.get("NORAD_CAT_ID")
            records.append(
                SourceRecord(
                    source_name=self.name,
                    source_record_id=None if catalog_number is None else str(catalog_number),
                    payload=row,
                    source_reference=self.build_source_reference(
                        response,
                        record_id=None if catalog_number is None else str(catalog_number),
                        #: The element-set epoch, which is what freshness is
                        #: judged against — not when we downloaded it.
                        source_timestamp=parse_datetime(row.get("EPOCH")),
                    ),
                    retrieved_at=response.retrieved_at,
                )
            )
        return records

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch one satellite's current element set by NORAD catalog number."""
        self.require_capability(Capability.FETCH_BY_ID)
        catalog_number = clean_text(identifier)
        if not catalog_number or not catalog_number.isdigit():
            raise SourceResponseError(
                "a GP lookup needs a numeric NORAD catalog number, got {0!r}".format(
                    identifier
                ),
                source_name=self.name,
            )
        rows = await self._gp_query("CATNR", catalog_number)
        records = self._to_records(rows)
        return records[0] if records else None

    async def fetch_group(self, group: str) -> SourceResultPage:
        """Fetch a named constellation or special-interest group.

        Group names are CelesTrak's own, e.g. `gps-ops`, `starlink`,
        `stations`, `active`.
        """
        self.require_capability(Capability.SEARCH)
        name = clean_text(group)
        if not name:
            raise SourceResponseError("a group query needs a group name",
                                      source_name=self.name)
        rows = await self._gp_query("GROUP", name)
        records = self._to_records(rows)
        return SourceResultPage(
            source_name=self.name,
            records=records,
            total_available=len(records),
            query_echo={"GROUP": name, "FORMAT": "JSON"},
            retrieved_at=self._last_response.retrieved_at,
        )

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Look up satellites by catalog number, designator, group or name."""
        self.require_capability(Capability.SEARCH)

        selector = None
        if query.identifier and clean_text(query.identifier).isdigit():
            selector = ("CATNR", clean_text(query.identifier))
        elif query.extra.get("group"):
            selector = ("GROUP", str(query.extra["group"]))
        elif query.extra.get("international_designator"):
            selector = ("INTDES", str(query.extra["international_designator"]))
        elif query.identifier:
            selector = ("INTDES", clean_text(query.identifier))
        elif query.extra.get("special"):
            selector = ("SPECIAL", str(query.extra["special"]))
        elif query.text:
            selector = ("NAME", clean_text(query.text))

        if selector is None:
            raise SourceResponseError(
                "a GP query needs a catalog number, international designator, group, "
                "special-interest list or name; whole-catalogue pulls are refused",
                source_name=self.name,
            )

        try:
            rows = await self._gp_query(selector[0], selector[1])
        except SourceNotFoundError:
            return SourceResultPage(
                source_name=self.name,
                records=[],
                total_available=0,
                query_echo={selector[0]: selector[1]},
            )

        records = self._to_records(rows)
        return SourceResultPage(
            source_name=self.name,
            records=records[query.offset:query.offset + query.limit],
            total_available=len(records),
            offset=query.offset,
            unsupported_filters=self._unsupported(
                query,
                ["text", "identifier", "group", "international_designator", "special"],
            ),
            query_echo={selector[0]: selector[1], "FORMAT": "JSON"},
            retrieved_at=self._last_response.retrieved_at,
        )
