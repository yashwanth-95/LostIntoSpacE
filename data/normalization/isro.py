"""Normalizer for Bhoonidhi STAC items.

Produces an `EOProduct`, the same canonical type Copernicus products use, so the
search layer treats Indian and European EO metadata identically.

Access status is set from what is actually true for this session: metadata was
retrieved with a token, so the product is `AUTHORIZED`; without one, nothing
would have been retrieved at all. There is no path here that reports an
authorization gap as an empty catalogue.
"""

from typing import Any, Dict, Optional, Tuple

from data.models import (
    AccessStatus,
    DataStatus,
    EOProduct,
    ProductFootprint,
    make_canonical_id,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import clean_text, make_quantity, parse_datetime, parse_int

__all__ = ["normalize_bhoonidhi_item"]

_MODULE = "data.normalization.isro"

#: STAC property names the adapter reads, with the canonical field each feeds.
#: Bhoonidhi follows STAC conventions plus mission-specific extensions, so both
#: spellings are checked rather than assuming one.
_PLATFORM_KEYS = ("platform", "satellite", "mission", "sat:platform_international_designator")
_INSTRUMENT_KEYS = ("instruments", "instrument", "sensor")
_PRODUCT_TYPE_KEYS = ("product_type", "productType", "sar:product_type", "product")
_LEVEL_KEYS = ("processing_level", "processingLevel", "processing:level", "level")
_MODE_KEYS = ("sar:instrument_mode", "instrument_mode", "mode", "acquisition_mode")


def _first(properties: Dict[str, Any], keys) -> Optional[str]:
    """First non-empty value among `keys`, joining lists into a string."""
    for key in keys:
        if key not in properties:
            continue
        value = properties[key]
        if isinstance(value, (list, tuple)):
            joined = ", ".join(str(item) for item in value if item)
            if joined:
                return joined
        else:
            text = clean_text(value)
            if text:
                return text
    return None


def normalize_bhoonidhi_item(
    record, has_credentials: bool = True
) -> Tuple[EOProduct, DataLineage]:
    """One Bhoonidhi STAC feature -> canonical `EOProduct`."""
    feature: Dict[str, Any] = record.payload
    reference = record.source_reference

    item_id = clean_text(feature.get("id"))
    if not item_id:
        raise ValueError("Bhoonidhi item has no id")
    collection = clean_text(feature.get("collection"))
    properties: Dict[str, Any] = feature.get("properties") or {}

    canonical_id = make_canonical_id("eo-product", "bhoonidhi-{0}".format(item_id))
    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed(
        "read STAC feature {0!r} from collection {1!r}".format(item_id, collection),
        module=_MODULE,
    )

    #: STAC uses a single `datetime`, or a `start_datetime`/`end_datetime` pair
    #: for products covering an interval.
    acquisition_start = parse_datetime(
        properties.get("start_datetime") or properties.get("datetime")
    )
    acquisition_end = parse_datetime(
        properties.get("end_datetime") or properties.get("datetime")
    )

    footprint = None
    geometry = feature.get("geometry")
    if isinstance(geometry, dict) and geometry.get("type"):
        footprint = ProductFootprint(geojson=geometry, srid=4326)
        builder.normalized(
            TransformationType.FIELD_MAPPING,
            "STAC geometry ({0}) recorded as the product footprint".format(
                geometry.get("type")
            ),
            module=_MODULE,
            inputs=["geometry"],
            output="footprint",
        )

    cloud_cover = make_quantity(
        properties.get("eo:cloud_cover", properties.get("cloud_cover")),
        "percent",
        source=reference,
    )

    access_status = (
        AccessStatus.AUTHORIZED if has_credentials else AccessStatus.CREDENTIALS_REQUIRED
    )
    builder.add(
        TransformationType.VALIDATION,
        "access status {0}: Bhoonidhi metadata is only retrievable with an "
        "authorized account, so an unauthorized session yields no record at all "
        "rather than an empty one".format(access_status.value),
        module=_MODULE,
        output="access_status",
    )

    product = EOProduct(
        canonical_id=canonical_id,
        name=clean_text(properties.get("title")) or item_id,
        description=clean_text(properties.get("description")),
        mission=_first(properties, ("mission", "constellation")) or collection,
        platform=_first(properties, _PLATFORM_KEYS),
        instrument=_first(properties, _INSTRUMENT_KEYS),
        product_type=_first(properties, _PRODUCT_TYPE_KEYS),
        processing_level=_first(properties, _LEVEL_KEYS),
        operational_mode=_first(properties, _MODE_KEYS),
        acquisition_start=acquisition_start,
        acquisition_end=acquisition_end,
        published_at=parse_datetime(properties.get("published") or properties.get("created")),
        processed_at=parse_datetime(properties.get("updated")),
        footprint=footprint,
        cloud_cover=cloud_cover,
        absolute_orbit_number=parse_int(
            properties.get("sat:absolute_orbit", properties.get("orbit_number"))
        ),
        relative_orbit_number=parse_int(
            properties.get("sat:relative_orbit", properties.get("relative_orbit_number"))
        ),
        orbit_direction=clean_text(
            properties.get("sat:orbit_state", properties.get("orbit_direction"))
        ),
        tile_id=clean_text(properties.get("tile_id") or properties.get("grid:code")),
        product_id=item_id,
        access_url=_download_url(feature, item_id, collection),
        access_status=access_status,
        attributes={
            key: value
            for key, value in properties.items()
            if value is not None
        },
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={
            "collection": collection,
            "stac_type": clean_text(feature.get("type")),
            "assets": sorted((feature.get("assets") or {}).keys()),
            "authorization_note": (
                "Product retrieval requires an authorized Bhoonidhi account; "
                "request access from bhoonidhi@nrsc.gov.in."
            ),
        },
    )
    builder.validated("canonical EOProduct constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return product, builder.build()


def _download_url(feature, item_id, collection) -> Optional[str]:
    """The product's own link, or the documented download endpoint.

    Never carries a credential: the token travels in the `Authorization`
    header, not in the URL.
    """
    for link in feature.get("links") or []:
        if str(link.get("rel", "")).lower() in ("self", "canonical"):
            href = clean_text(link.get("href"))
            if href:
                return href
    if item_id and collection:
        return "https://bhoonidhi-api.nrsc.gov.in/download?id={0}&collection={1}".format(
            item_id, collection
        )
    return None
