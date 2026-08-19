"""ESA / Copernicus adapter.

There is no single universal "ESA space data API", so this adapter targets one
specific, documented service: the Copernicus Data Space Ecosystem catalogue,
which exposes Sentinel ground-segment products through an OData REST interface.

**Metadata first.** Sentinel products are large — a single scene can be
gigabytes. This adapter discovers and filters *product metadata* only. Nothing
here downloads a product; that requires an authenticated session and belongs
behind an explicit user action, not inside an ingestion pass.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

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

__all__ = ["CopernicusSource", "COLLECTIONS", "odata_literal"]

#: Collections this adapter will query. An allow-list, for the same reason the
#: Exoplanet Archive has one: an OData `$filter` is a query language, and a
#: caller must not be able to compose arbitrary predicates against a shared
#: public service.
COLLECTIONS = (
    "SENTINEL-1",
    "SENTINEL-2",
    "SENTINEL-3",
    "SENTINEL-5P",
    "SENTINEL-6",
    "LANDSAT-5",
    "LANDSAT-7",
    "LANDSAT-8",
)


def odata_literal(value: str) -> str:
    """Quote a string as an OData literal, escaping embedded quotes.

    OData uses the SQL convention of doubling a single quote. Control
    characters are refused rather than escaped.
    """
    text = str(value)
    if "\n" in text or "\r" in text or "\x00" in text:
        raise SourceResponseError(
            "OData literals must not contain control characters",
            source_name="esa_copernicus",
        )
    return "'{0}'".format(text.replace("'", "''"))


class CopernicusSource(SpaceDataSource):
    """Copernicus Data Space Ecosystem OData product catalogue."""

    PRODUCTS_PATH = "/odata/v1/Products"

    @classmethod
    def default_config(cls) -> ProviderConfig:
        return ProviderConfig(
            name="esa_copernicus",
            base_url="https://catalogue.dataspace.copernicus.eu",
            timeout_seconds=45.0,
            retry=RetryConfig(max_attempts=3, backoff_factor=1.5),
            rate_limit=RateLimitConfig(
                requests_per_second=2.0,
                max_concurrent=2,
                policy_note=(
                    "The Copernicus Data Space Ecosystem applies per-account quotas "
                    "and throttling on catalogue and download endpoints. Catalogue "
                    "queries are self-limited; product download is out of scope here."
                ),
            ),
            #: Catalogue search is open; *downloading* a product needs an account.
            requires_auth=False,
            api_key_env=("COPERNICUS_ACCESS_TOKEN", "LIS_ESA_COPERNICUS_API_KEY"),
            api_key_header="Authorization",
            docs_url="https://documentation.dataspace.copernicus.eu/APIs/OData.html",
        )

    def get_source_info(self) -> SourceInfo:
        return SourceInfo(
            name="esa_copernicus",
            display_name="Copernicus Data Space Ecosystem (OData)",
            source_type=SourceType.EO_CATALOGUE,
            authority_note=(
                "Earth-observation product catalogue. Authoritative for Sentinel "
                "product metadata; not a source of astronomical or orbital data."
            ),
            provider_organization="ESA / European Commission Copernicus Programme",
            base_url=self.config.base_url,
            docs_url="https://documentation.dataspace.copernicus.eu/APIs/OData.html",
            capabilities=[Capability.SEARCH, Capability.FETCH_BY_ID, Capability.EO_PRODUCTS],
            provides=[
                "Sentinel product metadata",
                "mission, instrument and processing level",
                "sensing/acquisition time",
                "product footprint geometry",
                "cloud cover where the product reports it",
                "product identifier and catalogue URL",
            ],
            does_not_provide=[
                "space objects or orbital elements",
                "product pixel data without an authenticated download",
                "non-Copernicus ESA science archives",
            ],
            license="Copernicus data, free and open under the Copernicus licence",
            attribution="Contains modified Copernicus Sentinel data",
            requires_auth=False,
            rate_limit_note=self.config.rate_limit.policy_note,
            implemented=True,
        )

    def health_probe(self):
        return (self.PRODUCTS_PATH, {"$top": "1"})

    def __init__(self, *args, **kwargs):
        super(CopernicusSource, self).__init__(*args, **kwargs)
        self._last_response = None

    def _build_filter(self, query: SourceQuery) -> str:
        """Compose an OData `$filter` from validated pieces only.

        There is deliberately no way to pass a raw filter string through: each
        clause is built here from a typed input.
        """
        clauses: List[str] = []

        collection = query.extra.get("collection")
        if collection is not None:
            name = str(collection).upper()
            if name not in COLLECTIONS:
                raise SourceResponseError(
                    "collection {0!r} is not in the allow-list; permitted "
                    "collections are {1}".format(collection, ", ".join(COLLECTIONS)),
                    source_name=self.name,
                )
            clauses.append("Collection/Name eq {0}".format(odata_literal(name)))

        if query.start_time is not None:
            clauses.append(
                "ContentDate/Start gt {0}".format(_odata_datetime(query.start_time))
            )
        if query.end_time is not None:
            clauses.append(
                "ContentDate/Start lt {0}".format(_odata_datetime(query.end_time))
            )

        if query.text:
            clauses.append("contains(Name,{0})".format(odata_literal(clean_text(query.text))))
        if query.identifier:
            clauses.append("Name eq {0}".format(odata_literal(clean_text(query.identifier))))

        product_type = query.extra.get("product_type")
        if product_type is not None:
            clauses.append(
                "Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' "
                "and att/OData.CSC.StringAttribute/Value eq {0})".format(
                    odata_literal(str(product_type))
                )
            )

        max_cloud = query.extra.get("max_cloud_cover")
        if max_cloud is not None:
            value = float(max_cloud)
            if not 0.0 <= value <= 100.0:
                raise SourceResponseError(
                    "max_cloud_cover must be a percentage in [0, 100]",
                    source_name=self.name,
                )
            clauses.append(
                "Attributes/OData.CSC.DoubleAttribute/any(att:att/Name eq 'cloudCover' "
                "and att/OData.CSC.DoubleAttribute/Value le {0})".format(value)
            )

        geometry = query.extra.get("intersects_wkt")
        if geometry is not None:
            clauses.append(
                "OData.CSC.Intersects(area=geography'SRID=4326;{0}')".format(
                    _validate_wkt(str(geometry))
                )
            )

        if not clauses:
            raise SourceResponseError(
                "a Copernicus search needs at least one filter (collection, time "
                "window, name or geometry); unfiltered catalogue scans are refused",
                source_name=self.name,
            )
        return " and ".join(clauses)

    async def search(self, query: SourceQuery) -> SourceResultPage:
        """Discover products. Metadata only — nothing is downloaded here."""
        self.require_capability(Capability.SEARCH)

        params: Dict[str, Any] = {
            "$filter": self._build_filter(query),
            "$top": query.limit,
            "$expand": "Attributes",
            "$orderby": "ContentDate/Start desc",
        }
        if query.offset:
            params["$skip"] = query.offset

        response = await self._client.get(self.PRODUCTS_PATH, params=params)
        payload = response.json()
        products = payload.get("value")
        if products is None:
            raise SourceResponseError(
                "Copernicus response has no 'value' array",
                source_name=self.name,
                url=response.url,
            )
        self._last_response = response

        records = [
            SourceRecord(
                source_name=self.name,
                source_record_id=clean_text(product.get("Id")),
                payload=product,
                source_reference=self.build_source_reference(
                    response, record_id=clean_text(product.get("Id"))
                ),
                retrieved_at=response.retrieved_at,
            )
            for product in products
        ]
        return SourceResultPage(
            source_name=self.name,
            records=records,
            offset=query.offset,
            #: OData paginates by continuation link rather than a total count.
            next_cursor=clean_text(payload.get("@odata.nextLink")),
            unsupported_filters=self._unsupported(
                query,
                ["text", "identifier", "start_time", "end_time", "collection",
                 "product_type", "max_cloud_cover", "intersects_wkt"],
            ),
            query_echo={"$filter": params["$filter"], "$top": query.limit},
            retrieved_at=response.retrieved_at,
        )

    async def fetch_page(self, next_link: str) -> SourceResultPage:
        """Follow an OData continuation link returned by a previous page."""
        link = clean_text(next_link)
        if not link or not link.startswith(self.config.base_url):
            raise SourceResponseError(
                "a continuation link must point at {0}".format(self.config.base_url),
                source_name=self.name,
            )
        response = await self._client.get(link[len(self.config.base_url):])
        payload = response.json()
        self._last_response = response
        return SourceResultPage(
            source_name=self.name,
            records=[
                SourceRecord(
                    source_name=self.name,
                    source_record_id=clean_text(product.get("Id")),
                    payload=product,
                    source_reference=self.build_source_reference(
                        response, record_id=clean_text(product.get("Id"))
                    ),
                    retrieved_at=response.retrieved_at,
                )
                for product in payload.get("value") or []
            ],
            next_cursor=clean_text(payload.get("@odata.nextLink")),
            retrieved_at=response.retrieved_at,
        )

    async def fetch_by_id(self, identifier: str, **kwargs) -> Optional[SourceRecord]:
        """Fetch one product's metadata by its catalogue UUID."""
        self.require_capability(Capability.FETCH_BY_ID)
        product_id = clean_text(identifier)
        if not product_id:
            raise SourceResponseError(
                "a product lookup needs a product id", source_name=self.name
            )
        response = await self._client.get(
            "{0}({1})".format(self.PRODUCTS_PATH, odata_literal(product_id)),
            params={"$expand": "Attributes"},
        )
        payload = response.json()
        if not isinstance(payload, dict) or "Id" not in payload:
            raise SourceNotFoundError(
                "no Copernicus product with id {0!r}".format(product_id),
                source_name=self.name,
                url=response.url,
            )
        return SourceRecord(
            source_name=self.name,
            source_record_id=clean_text(payload.get("Id")),
            payload=payload,
            source_reference=self.build_source_reference(
                response, record_id=clean_text(payload.get("Id"))
            ),
            retrieved_at=response.retrieved_at,
        )


def _odata_datetime(moment: datetime) -> str:
    """Render a datetime in the form the OData filter expects."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.000Z")


#: Geometry types accepted in an intersects filter.
_WKT_TYPES = ("POLYGON", "MULTIPOLYGON", "POINT", "LINESTRING")


def _validate_wkt(value: str) -> str:
    """Accept only a recognised WKT geometry, with no embedded quotes."""
    text = " ".join(str(value).split())
    if "'" in text or ";" in text:
        raise SourceResponseError(
            "WKT geometry must not contain quotes or semicolons",
            source_name="esa_copernicus",
        )
    if not any(text.upper().startswith(kind) for kind in _WKT_TYPES):
        raise SourceResponseError(
            "unsupported WKT geometry; expected one of {0}".format(", ".join(_WKT_TYPES)),
            source_name="esa_copernicus",
        )
    return text
