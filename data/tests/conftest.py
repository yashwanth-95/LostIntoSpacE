"""Shared fixtures for data-layer tests."""

from datetime import datetime, timezone

import pytest

from contracts.provenance import SourceReference, SourceType


@pytest.fixture
def jpl_source():
    return SourceReference(
        source_name="jpl_sbdb",
        source_type=SourceType.PRIMARY_SCIENTIFIC,
        source_url="https://ssd-api.jpl.nasa.gov/sbdb.api",
        source_record_id="2000001",
        retrieved_at=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
        source_version="sbdb-1.3",
        attribution="NASA/JPL Small-Body Database",
    )


@pytest.fixture
def celestrak_source():
    return SourceReference(
        source_name="celestrak_gp",
        source_type=SourceType.SECONDARY_OPERATIONAL,
        source_url="https://celestrak.org/NORAD/elements/gp.php",
        source_record_id="25544",
        retrieved_at=datetime(2026, 8, 18, 13, 0, tzinfo=timezone.utc),
        attribution="CelesTrak GP data",
    )


@pytest.fixture
def bundled_source():
    return SourceReference(
        source_name="bundled_reference",
        source_type=SourceType.BUNDLED_REFERENCE,
        retrieved_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
