"""Normalizer for Copernicus OData product records.

Produces an `EOProduct`. Deliberately metadata-only: the record describes the
product and says how it could be obtained, but nothing here downloads it. A
single Sentinel-2 scene is hundreds of megabytes, and pulling one during an
ingestion pass would be both slow and pointless — the search layer indexes
metadata, not pixels.
"""

from typing import Any, Dict, Optional, Tuple

from data.models import (
    AccessStatus,
    DataStatus,
    EOProduct,
    ProductFootprint,
    Quantity,
    make_canonical_id,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import clean_text, make_quantity, parse_datetime, parse_int

__all__ = ["normalize_copernicus_product", "extract_attributes"]

_MODULE = "data.normalization.esa"


def extract_attributes(product: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten the OData `Attributes` array into a plain mapping.

    Copernicus returns attributes as a list of `{Name, Value, ValueType}`
    objects. Keeping them as a list would make every downstream lookup a scan.
    """
    attributes: Dict[str, Any] = {}
    for entry in product.get("Attributes") or []:
        name = clean_text(entry.get("Name"))
        if name:
            attributes[name] = entry.get("Value")
    return attributes


def normalize_copernicus_product(
    record, has_credentials: bool = False
) -> Tuple[EOProduct, DataLineage]:
    """One OData product -> canonical `EOProduct`."""
    product: Dict[str, Any] = record.payload
    reference = record.source_reference

    product_id = clean_text(product.get("Id"))
    name = clean_text(product.get("Name")) or product_id
    if not name:
        raise ValueError("Copernicus product has neither Id nor Name")

    canonical_id = make_canonical_id("eo-product", "copernicus-{0}".format(product_id or name))
    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)

    attributes = extract_attributes(product)
    builder.parsed(
        "flattened {0} OData attribute(s) into a mapping".format(len(attributes)),
        module=_MODULE,
        inputs=["Attributes"],
        output="attributes",
    )

    content_date = product.get("ContentDate") or {}
    acquisition_start = parse_datetime(
        content_date.get("Start") or attributes.get("beginningDateTime")
    )
    acquisition_end = parse_datetime(
        content_date.get("End") or attributes.get("endingDateTime")
    )

    footprint = None
    wkt = clean_text(product.get("Footprint"))
    geojson = product.get("GeoFootprint")
    if wkt or geojson:
        footprint = ProductFootprint(
            wkt=wkt,
            geojson=geojson if isinstance(geojson, dict) else None,
            #: Copernicus embeds the SRID in the WKT prefix.
            srid=4326 if wkt and "SRID=4326" in wkt else None,
        )

    cloud_cover = make_quantity(
        attributes.get("cloudCover"), "percent", source=reference
    )
    if cloud_cover is not None:
        builder.normalized(
            TransformationType.UNIT_CONVERSION,
            "cloudCover {0} recorded as a percentage".format(attributes.get("cloudCover")),
            module=_MODULE,
            inputs=["Attributes.cloudCover"],
            output="cloud_cover",
        )

    access_status, access_note = _access_status(product, has_credentials)
    builder.add(
        TransformationType.VALIDATION,
        access_note,
        module=_MODULE,
        output="access_status",
    )

    platform_short = clean_text(attributes.get("platformShortName"))
    serial = clean_text(attributes.get("platformSerialIdentifier"))
    platform = None
    if platform_short and serial:
        platform = "{0}{1}".format(platform_short, serial)
    elif platform_short:
        platform = platform_short

    eo_product = EOProduct(
        canonical_id=canonical_id,
        name=name,
        mission=platform_short,
        platform=platform,
        instrument=clean_text(attributes.get("instrumentShortName")),
        product_type=clean_text(attributes.get("productType")),
        processing_level=clean_text(attributes.get("processingLevel")),
        operational_mode=clean_text(attributes.get("operationalMode")),
        acquisition_start=acquisition_start,
        acquisition_end=acquisition_end,
        published_at=parse_datetime(product.get("PublicationDate")),
        processed_at=parse_datetime(attributes.get("processingDate")),
        footprint=footprint,
        cloud_cover=cloud_cover,
        absolute_orbit_number=parse_int(attributes.get("orbitNumber")),
        relative_orbit_number=parse_int(attributes.get("relativeOrbitNumber")),
        orbit_direction=clean_text(attributes.get("orbitDirection")),
        tile_id=clean_text(attributes.get("tileId")),
        product_id=product_id,
        access_url=_product_url(product_id),
        access_status=access_status,
        content_length=parse_int(product.get("ContentLength")),
        processor_version=clean_text(attributes.get("processorVersion")),
        attributes=attributes,
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={
            "s3_path": clean_text(product.get("S3Path")),
            "origin": clean_text(attributes.get("origin")),
            "online": product.get("Online"),
            "eviction_date": clean_text(product.get("EvictionDate")),
            "content_type": clean_text(product.get("ContentType")),
        },
    )
    builder.validated("canonical EOProduct constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return eo_product, builder.build()


def _product_url(product_id: Optional[str]) -> Optional[str]:
    """The catalogue URL for a product. Never carries a credential."""
    if not product_id:
        return None
    return (
        "https://catalogue.dataspace.copernicus.eu/odata/v1/Products({0})".format(
            product_id
        )
    )


def _access_status(product, has_credentials: bool):
    """Decide the access status, and say why.

    Copernicus catalogue search is open; downloading the product needs an
    account. When a product is not `Online` it has moved to long-term storage
    and needs a restore request first — which is a different problem again.
    """
    online = product.get("Online")
    if online is False:
        return (
            AccessStatus.OFFLINE,
            "product is not Online; it is in long-term storage and needs a restore "
            "request before download",
        )
    if has_credentials:
        return (
            AccessStatus.AUTHORIZED,
            "credentials are configured, so the product data can be downloaded",
        )
    return (
        AccessStatus.CREDENTIALS_REQUIRED,
        "catalogue metadata is open, but downloading the product requires a "
        "Copernicus Data Space account; none is configured",
    )
