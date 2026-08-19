"""Earth-observation product records.

A Sentinel scene is a *product in a catalogue*, not a space object. It gets its
own record type so the catalogue metadata that matters — mission, instrument,
processing level, acquisition time, footprint, access conditions — is modelled
properly rather than squeezed into `SpaceObject`.

`AccessStatus` is a first-class field. Several EO archives are
authorization-gated, and "you are not entitled to this product" is a different
answer from "this product does not exist". Conflating them misleads the user.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from contracts._time import as_utc

from .base import NamedRecord, require_dimensions
from .enums import ObjectType
from .units import Dimension, Quantity

__all__ = ["AccessStatus", "ProductFootprint", "EOProduct"]

_D = Dimension


class AccessStatus(str, Enum):
    """Whether this project can actually retrieve the product's data."""

    #: Downloadable without credentials.
    OPEN = "OPEN"
    #: Requires an account; credentials are configured and appear valid.
    AUTHORIZED = "AUTHORIZED"
    #: Requires an account; no credentials are configured.
    CREDENTIALS_REQUIRED = "CREDENTIALS_REQUIRED"
    #: Credentials exist but this dataset is not entitled to this account.
    NOT_ENTITLED = "NOT_ENTITLED"
    #: Catalogue metadata only; the product itself is not offered here.
    METADATA_ONLY = "METADATA_ONLY"
    #: Moved to long-term storage; retrieval needs a restore request first.
    OFFLINE = "OFFLINE"
    UNKNOWN = "UNKNOWN"


class ProductFootprint(BaseModel):
    """The ground area a product covers."""

    model_config = ConfigDict(extra="forbid")

    #: Well-known-text geometry exactly as the catalogue published it.
    wkt: Optional[str] = None
    #: GeoJSON geometry, when the catalogue supplies one.
    geojson: Optional[Dict[str, Any]] = None
    #: Spatial reference identifier, e.g. 4326.
    srid: Optional[int] = None

    @model_validator(mode="after")
    def _check(self) -> "ProductFootprint":
        if self.wkt is None and self.geojson is None:
            raise ValueError("a footprint needs either wkt or geojson")
        return self


class EOProduct(NamedRecord):
    """One Earth-observation product in a provider's catalogue."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    record_type: str = "eo_product"
    object_type: ObjectType = ObjectType.EO_PRODUCT

    #: Mission or collection name, e.g. "SENTINEL-2", "NISAR".
    mission: Optional[str] = None
    #: Specific platform within the mission, e.g. "S2B".
    platform: Optional[str] = None
    instrument: Optional[str] = None
    #: Provider's product type code, e.g. "S2MSI2A".
    product_type: Optional[str] = None
    #: Processing level as the provider states it, e.g. "S2MSI2A", "L2A".
    processing_level: Optional[str] = None
    #: Provider's operational/acquisition mode, e.g. "INS-NOBS", "IW".
    operational_mode: Optional[str] = None

    #: Start and end of the sensing window.
    acquisition_start: Optional[datetime] = None
    acquisition_end: Optional[datetime] = None
    #: When the provider published the product to its catalogue.
    published_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None

    footprint: Optional[ProductFootprint] = None
    #: Percentage cloud cover, where the provider reports it.
    cloud_cover: Optional[Quantity] = None

    absolute_orbit_number: Optional[int] = None
    relative_orbit_number: Optional[int] = None
    orbit_direction: Optional[str] = None
    #: Grid/tile identifier, e.g. a Sentinel-2 MGRS tile.
    tile_id: Optional[str] = None

    #: Provider's own product identifier (a UUID for Copernicus).
    product_id: Optional[str] = None
    #: Where the product can be requested. Never carries a credential.
    access_url: Optional[str] = None
    access_status: AccessStatus = AccessStatus.UNKNOWN
    #: Size in bytes as reported by the catalogue.
    content_length: Optional[int] = None
    processor_version: Optional[str] = None

    #: Provider attributes with no canonical field, kept verbatim.
    attributes: Dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "acquisition_start", "acquisition_end", "published_at", "processed_at"
    )
    @classmethod
    def _utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return as_utc(value)

    @model_validator(mode="after")
    def _check(self) -> "EOProduct":
        require_dimensions(self, {"cloud_cover": _D.DIMENSIONLESS})
        if self.acquisition_start and self.acquisition_end:
            if self.acquisition_start > self.acquisition_end:
                raise ValueError("acquisition_start is after acquisition_end")
        if self.cloud_cover is not None:
            percent = self.cloud_cover.to("percent").value
            if percent < 0.0 or percent > 100.0:
                raise ValueError(
                    "cloud cover {0}% is outside [0, 100]".format(percent)
                )
        if self.content_length is not None and self.content_length < 0:
            raise ValueError("content_length must not be negative")
        return self

    def temporal_anchor(self) -> Optional[datetime]:
        """An EO product's content describes when it was acquired."""
        return self.acquisition_start or self.published_at or self.valid_at

    @property
    def is_retrievable(self) -> bool:
        """Whether the product data itself can be fetched right now."""
        return self.access_status in (AccessStatus.OPEN, AccessStatus.AUTHORIZED)

    def access_explanation(self) -> str:
        """Plain statement of why the data is or is not available.

        Shown to users instead of an empty result, so an authorization gap is
        never mistaken for missing data.
        """
        if self.access_status is AccessStatus.OPEN:
            return "Product data is openly downloadable."
        if self.access_status is AccessStatus.AUTHORIZED:
            return "Product data is downloadable with the configured account."
        if self.access_status is AccessStatus.CREDENTIALS_REQUIRED:
            return (
                "Product metadata is available, but downloading the data requires "
                "an account with the provider. No credentials are configured."
            )
        if self.access_status is AccessStatus.NOT_ENTITLED:
            return (
                "The configured account is not entitled to this dataset. This is an "
                "authorization limit, not an absence of data."
            )
        if self.access_status is AccessStatus.METADATA_ONLY:
            return "Only catalogue metadata is offered for this product."
        if self.access_status is AccessStatus.OFFLINE:
            return (
                "The product is in long-term storage and must be restored by the "
                "provider before it can be downloaded."
            )
        return "Access conditions for this product are not known."
