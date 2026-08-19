"""Space-object schemas - the P2/P4 read boundary.

P4 owns ingestion (external APIs, normalization, provenance tagging) and
writes rows directly via `database/seeds/` loaders. P2 owns only the read API
over whatever is in the table, which is why there is no create/update/delete
schema here: the API works identically whether P4's ingestion has run or the
rows came from bundled fallback data.

`physical_data`, `orbital_data`, and `discovery` are JSONB passed through
verbatim - their shape varies by object category (a star and a spacecraft
share almost no fields) and P4 defines it.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SpaceObjectSummary(BaseModel):
    """List view - omits the heavy JSONB blobs so a catalog page stays small."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    category: str
    subcategory: str | None
    description: str | None
    images: list[Any]
    source: str | None


class SpaceObjectDetail(SpaceObjectSummary):
    physical_data: dict[str, Any] | None
    orbital_data: dict[str, Any] | None
    discovery: dict[str, Any] | None
    source_id: str | None
    last_updated: datetime | None
    created_at: datetime
