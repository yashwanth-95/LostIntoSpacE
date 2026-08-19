"""Shared fixtures: a realistic index built from seeds and recorded archive data."""

import json
import pathlib
from datetime import datetime, timezone

import pytest

from data.models import Asteroid, DocumentRecord, Planet, SpaceStation
from data.normalization.celestrak import normalize_gp_record
from data.normalization.exoplanet import normalize_exoplanet_row
from data.normalization.jpl import normalize_sbdb_object
from data.normalization.nasa import normalize_eonet_event, normalize_ntrs_citation
from data.provenance import POLICIES, apply_freshness
from data.seeds import build_concepts, build_missions
from data.sources import build_source
from data.sources.base import SourceRecord
from search.keyword import KeywordIndex

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)

_FIXTURES = pathlib.Path(__file__).parent.parent.parent / "data" / "tests" / "fixtures"


def load(name):
    with open(str(_FIXTURES / name), encoding="utf-8") as handle:
        return json.load(handle)


def _record(source_name, payload, record_id=None):
    source = build_source(source_name)
    return SourceRecord(
        source_name=source_name,
        source_record_id=record_id,
        payload=payload,
        source_reference=source.build_source_reference(record_id=record_id),
    )


def build_corpus():
    """Every record type the product searches, from seeds and real fixtures."""
    records = []
    records.extend(build_concepts())
    records.extend(build_missions())

    ceres, _ = normalize_sbdb_object(_record("jpl_sbdb", load("sbdb_ceres.json")))
    bennu, _ = normalize_sbdb_object(_record("jpl_sbdb", load("sbdb_bennu.json")))
    records.extend([ceres, bennu])

    iss, _ = normalize_gp_record(_record("celestrak_gp", load("celestrak_iss.json")[0]))
    records.append(iss)

    for row in load("celestrak_gps_ops.json"):
        satellite, _ = normalize_gp_record(_record("celestrak_gp", row))
        records.append(satellite)

    planet, star, _ = normalize_exoplanet_row(
        _record(
            "nasa_exoplanet_archive",
            dict(load("exoplanet_pscomppars_kepler22b.json")[0], _table="pscomppars"),
        )
    )
    records.extend([planet, star])

    event, _ = normalize_eonet_event(
        _record("nasa_eonet", load("eonet_events.json")["events"][0])
    )
    records.append(event)

    document, _ = normalize_ntrs_citation(
        _record("nasa_ntrs", load("ntrs_search.json")["results"][0])
    )
    records.append(document)

    #: Freshness is assigned by the pipeline, so mirror that here — the index
    #: must never decide it for itself.
    for record in records:
        source = record.primary_source
        if source is not None:
            apply_freshness(record, POLICIES.get(source.source_name)
                            or POLICIES["bundled_reference"], now=NOW)
    return records


@pytest.fixture(scope="session")
def corpus():
    return build_corpus()


@pytest.fixture(scope="session")
def index(corpus):
    engine = KeywordIndex()
    engine.add_records(corpus)
    return engine
