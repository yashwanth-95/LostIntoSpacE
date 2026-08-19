"""Normalizers for NASA source records.

Each function takes a `SourceRecord` and returns a canonical model with
provenance attached and a `DataLineage` describing how it got there.

Deliberate scoping decisions, per the rule "do not force unrelated NASA products
into `SpaceObject`":

* An **EONET event** becomes a `NaturalEvent`, not a `SpaceObject`.
* An **NTRS citation** becomes a `DocumentRecord`, not a `SpaceObject`.
* A **NeoWs object** does become an `Asteroid`, because it genuinely is one —
  but its orbital elements are recorded with `SourceType.AGENCY_PUBLIC_API`
  authority, so JPL SBDB will outrank them at conflict-resolution time.
"""

from typing import Optional, Tuple

from data.models import (
    Asteroid,
    CoordinateSystem,
    DataStatus,
    DiscoveryInfo,
    DocumentAuthor,
    DocumentLink,
    DocumentRecord,
    ElementTheory,
    EventCategory,
    EventGeometry,
    EventSource,
    FrameContext,
    NaturalEvent,
    ObservationType,
    OrbitalElements,
    OrbitRecord,
    OriginType,
    PhysicalProperties,
    Quantity,
    ReferenceFrame,
    TimeScale,
    make_canonical_id,
)
from data.provenance import DataLineage, LineageBuilder, TransformationType

from .parsing import (
    clean_text,
    julian_date_to_datetime,
    make_quantity,
    parse_bool,
    parse_date,
    parse_datetime,
    parse_float,
    parse_int,
)

__all__ = [
    "normalize_neows_object",
    "normalize_eonet_event",
    "normalize_ntrs_citation",
]

_MODULE = "data.normalization.nasa"


def normalize_neows_object(record) -> Tuple[Asteroid, DataLineage]:
    """NeoWs object -> canonical `Asteroid` (plus an `OrbitRecord` when present)."""
    payload = record.payload
    reference = record.source_reference
    designation = clean_text(payload.get("designation"))
    name = clean_text(payload.get("name")) or designation or str(payload.get("id"))
    canonical_id = make_canonical_id("asteroid", designation or name)

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read NeoWs object payload", module=_MODULE)

    # -- physical parameters ------------------------------------------------
    diameter = None
    estimated = (payload.get("estimated_diameter") or {}).get("kilometers") or {}
    low = parse_float(estimated.get("estimated_diameter_min"))
    high = parse_float(estimated.get("estimated_diameter_max"))
    if low is not None and high is not None:
        # NeoWs publishes a range, not a measurement. Recording the midpoint
        # with a half-width uncertainty preserves both ends honestly; recording
        # only the midpoint would imply a precision that does not exist.
        midpoint = (low + high) / 2.0
        diameter = Quantity(
            value=midpoint,
            unit="km",
            uncertainty=(high - low) / 2.0,
            source=reference,
        )
        builder.normalized(
            TransformationType.UNIT_CONVERSION,
            "estimated diameter range {0}-{1} km -> midpoint with half-width "
            "uncertainty".format(low, high),
            module=_MODULE,
            inputs=["estimated_diameter.kilometers"],
            output="physical.diameter",
            output_value=midpoint,
        )

    physical = PhysicalProperties(
        diameter=diameter,
        absolute_magnitude=make_quantity(
            payload.get("absolute_magnitude_h"), "mag", source=reference
        ),
    )

    orbital = payload.get("orbital_data") or {}
    moid = make_quantity(orbital.get("minimum_orbit_intersection"), "au", source=reference)

    asteroid = Asteroid(
        canonical_id=canonical_id,
        name=name,
        aliases=[value for value in (designation, clean_text(payload.get("name_limited")))
                 if value and value != name],
        object_type=Asteroid.model_fields["object_type"].default,
        designation=designation,
        spk_id=clean_text(payload.get("neo_reference_id")),
        number=parse_int(designation) if (designation or "").isdigit() else None,
        orbit_class=clean_text((orbital.get("orbit_class") or {}).get("orbit_class_type")),
        is_near_earth_object=True,
        is_potentially_hazardous=parse_bool(payload.get("is_potentially_hazardous_asteroid")),
        earth_moid=moid,
        physical=physical,
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        reference_urls=[
            url for url in [clean_text(payload.get("nasa_jpl_url"))] if url
        ],
        source_specific={
            "is_sentry_object": payload.get("is_sentry_object"),
            "orbit_id": orbital.get("orbit_id"),
            "orbit_uncertainty": orbital.get("orbit_uncertainty"),
            "jupiter_tisserand_invariant": orbital.get("jupiter_tisserand_invariant"),
        },
    )

    orbit = _neows_orbit(orbital, canonical_id, reference, record, builder)
    if orbit is not None:
        asteroid.orbits = [orbit]

    builder.validated("canonical Asteroid constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return asteroid, builder.build()


def _neows_orbit(orbital, object_id, reference, record, builder) -> Optional[OrbitRecord]:
    """Build an `OrbitRecord` from a NeoWs `orbital_data` block.

    NeoWs re-publishes JPL's osculating heliocentric solution. The frame is
    recorded explicitly rather than assumed, and the record is attributed to
    NeoWs so JPL SBDB — the actual authority — outranks it later.
    """
    if not orbital:
        return None
    epoch = julian_date_to_datetime(orbital.get("epoch_osculation"))
    if epoch is None:
        return None

    builder.normalized(
        TransformationType.EPOCH_CONVERSION,
        "epoch_osculation JD -> UTC datetime",
        module=_MODULE,
        inputs=["orbital_data.epoch_osculation"],
        output="orbits[0].epoch",
        input_value=orbital.get("epoch_osculation"),
        output_value=epoch.isoformat(),
    )
    builder.normalized(
        TransformationType.FRAME_ANNOTATION,
        "annotated as heliocentric osculating Keplerian elements (NeoWs republishes "
        "JPL's solution and does not state the frame in the payload)",
        module=_MODULE,
        output="orbits[0].frame",
    )

    equinox = clean_text(orbital.get("equinox")) or ""
    frame = ReferenceFrame.J2000 if equinox.upper().startswith("J2000") else (
        ReferenceFrame.UNKNOWN
    )

    elements = OrbitalElements(
        semi_major_axis=make_quantity(orbital.get("semi_major_axis"), "au", source=reference),
        eccentricity=make_quantity(orbital.get("eccentricity"), "1", source=reference),
        inclination=make_quantity(orbital.get("inclination"), "deg", source=reference),
        ascending_node_longitude=make_quantity(
            orbital.get("ascending_node_longitude"), "deg", source=reference
        ),
        argument_of_periapsis=make_quantity(
            orbital.get("perihelion_argument"), "deg", source=reference
        ),
        mean_anomaly=make_quantity(orbital.get("mean_anomaly"), "deg", source=reference),
        periapsis_distance=make_quantity(
            orbital.get("perihelion_distance"), "au", source=reference
        ),
        apoapsis_distance=make_quantity(
            orbital.get("aphelion_distance"), "au", source=reference
        ),
        orbital_period=make_quantity(orbital.get("orbital_period"), "d", source=reference),
        mean_motion=make_quantity(orbital.get("mean_motion"), "deg/day", source=reference),
        periapsis_time=julian_date_to_datetime(orbital.get("perihelion_time")),
    )

    from data.models import OrbitFitInfo

    fit = OrbitFitInfo(
        observations_used=parse_int(orbital.get("observations_used")),
        data_arc_days=parse_float(orbital.get("data_arc_in_days")),
        first_observation=parse_datetime(orbital.get("first_observation_date")),
        last_observation=parse_datetime(orbital.get("last_observation_date")),
        condition_code=clean_text(orbital.get("orbit_uncertainty")),
        solution_date=parse_datetime(orbital.get("orbit_determination_date")),
        solution_id=clean_text(orbital.get("orbit_id")),
    )

    return OrbitRecord(
        canonical_id="{0}:orbit:neows-{1}".format(object_id, epoch.strftime("%Y%m%d")),
        object_canonical_id=object_id,
        source_designation=clean_text(orbital.get("orbit_id")),
        epoch=epoch,
        frame=FrameContext(
            origin_type=OriginType.HELIOCENTRIC,
            center_body="sun",
            reference_frame=frame,
            coordinate_system=CoordinateSystem.KEPLERIAN,
            #: JPL osculating epochs are TDB.
            time_scale=TimeScale.TDB,
        ),
        element_theory=ElementTheory.OSCULATING_KEPLERIAN,
        elements=elements,
        fit=fit,
        orbit_class=clean_text((orbital.get("orbit_class") or {}).get("orbit_class_type")),
        orbit_class_description=clean_text(
            (orbital.get("orbit_class") or {}).get("orbit_class_description")
        ),
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        data_status=DataStatus.CONFIRMED,
    )


def normalize_eonet_event(record) -> Tuple[NaturalEvent, DataLineage]:
    """EONET event -> canonical `NaturalEvent`. Never a `SpaceObject`."""
    payload = record.payload
    reference = record.source_reference
    event_id = clean_text(payload.get("id")) or "unknown"
    canonical_id = make_canonical_id("natural-event", event_id)

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read EONET event payload", module=_MODULE)

    geometries = []
    for entry in payload.get("geometry") or []:
        moment = parse_datetime(entry.get("date"))
        if moment is None:
            continue
        magnitude_unit = clean_text(entry.get("magnitudeUnit"))
        magnitude_value = parse_float(entry.get("magnitudeValue"))
        magnitude = None
        if magnitude_value is not None and magnitude_unit:
            # Event magnitudes use units outside any physical system ("acres",
            # "NM"), so the number is stored dimensionless with the source's
            # own unit label preserved beside it.
            magnitude = Quantity(value=magnitude_value, unit="1", source=reference)
        geometries.append(
            EventGeometry(
                date=moment,
                geometry_type=clean_text(entry.get("type")) or "Point",
                coordinates=list(entry.get("coordinates") or []),
                magnitude=magnitude,
                magnitude_unit_label=magnitude_unit,
            )
        )

    if geometries:
        builder.normalized(
            TransformationType.EPOCH_CONVERSION,
            "geometry timestamps -> UTC datetimes",
            module=_MODULE,
            inputs=["geometry[].date"],
            output="geometries[].date",
        )

    event = NaturalEvent(
        canonical_id=canonical_id,
        name=clean_text(payload.get("title")) or event_id,
        description=clean_text(payload.get("description")),
        categories=[
            EventCategory(id=clean_text(item.get("id")), title=clean_text(item.get("title")))
            for item in payload.get("categories") or []
            if clean_text(item.get("id"))
        ],
        event_sources=[
            EventSource(id=clean_text(item.get("id")), url=clean_text(item.get("url")))
            for item in payload.get("sources") or []
            if clean_text(item.get("id"))
        ],
        geometries=geometries,
        closed_at=parse_datetime(payload.get("closed")),
        link=clean_text(payload.get("link")),
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
    )
    builder.validated("canonical NaturalEvent constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return event, builder.build()


def normalize_ntrs_citation(record) -> Tuple[DocumentRecord, DataLineage]:
    """NTRS citation -> canonical `DocumentRecord`. Never a `SpaceObject`."""
    payload = record.payload
    reference = record.source_reference
    citation_id = str(payload.get("id"))
    canonical_id = make_canonical_id("document", "ntrs-{0}".format(citation_id))

    builder = LineageBuilder(canonical_id)
    builder.fetched(reference, module=_MODULE)
    builder.parsed("read NTRS citation payload", module=_MODULE)

    authors = []
    for entry in payload.get("authorAffiliations") or []:
        meta = entry.get("meta") or {}
        author = meta.get("author") or {}
        organization = meta.get("organization") or {}
        name = clean_text(author.get("name"))
        if not name:
            continue
        authors.append(
            DocumentAuthor(
                name=name,
                organization=clean_text(organization.get("name")),
                location=clean_text(organization.get("location")),
                sequence=parse_int(entry.get("sequence")),
            )
        )

    publication_date = None
    for publication in payload.get("publications") or []:
        publication_date = parse_date(publication.get("publicationDate"))
        if publication_date is not None:
            break
    if publication_date is None:
        publication_date = parse_date(payload.get("distributionDate"))

    copyright_block = payload.get("copyright") or {}
    determination = clean_text(copyright_block.get("determinationType"))
    #: Full-text indexing is permitted only when the source states the work is
    #: US-Government public-use. Everything else stays metadata-only.
    full_text_ok = determination == "GOV_PUBLIC_USE_PERMITTED"

    links = []
    for download in payload.get("downloads") or []:
        url = (download.get("links") or {}).get("pdf") or (
            download.get("links") or {}
        ).get("original")
        if not url:
            continue
        links.append(
            DocumentLink(
                url=url,
                mime_type=clean_text(download.get("mimetype")),
                label=clean_text(download.get("name")),
                full_text_permitted=full_text_ok,
            )
        )

    if determination:
        builder.add(
            TransformationType.VALIDATION,
            "copyright determination {0!r} -> full_text_permitted={1}".format(
                determination, full_text_ok
            ),
            module=_MODULE,
            output="links[].full_text_permitted",
        )

    identifiers = [
        value
        for value in (clean_text(item) for item in payload.get("otherReportNumbers") or [])
        if value
    ]
    legacy = (payload.get("legacyMeta") or {}).get("accessionNumber")
    if clean_text(legacy):
        identifiers.append(clean_text(legacy))

    document = DocumentRecord(
        canonical_id=canonical_id,
        name=clean_text(payload.get("title")) or "NTRS {0}".format(citation_id),
        abstract=clean_text(payload.get("abstract")),
        authors=authors,
        publisher=clean_text((payload.get("center") or {}).get("name")),
        publication_date=publication_date,
        document_type=clean_text(payload.get("stiType")),
        document_type_label=clean_text(payload.get("stiTypeDetails")),
        identifiers=identifiers,
        subject_categories=[
            value
            for value in (clean_text(item) for item in payload.get("subjectCategories") or [])
            if value
        ],
        distribution=clean_text(payload.get("distribution")),
        copyright_determination=determination,
        links=links,
        is_lessons_learned=bool(payload.get("isLessonsLearned")),
        source_created_at=parse_datetime(payload.get("created")),
        source_updated_at=parse_datetime(payload.get("modified")),
        data_status=DataStatus.CONFIRMED,
        retrieved_at=record.retrieved_at,
        source_references=[reference],
        source_specific={"ntrs_id": citation_id, "status": payload.get("status")},
    )
    builder.validated("canonical DocumentRecord constructed and validated", module=_MODULE)
    builder.finalized(module=_MODULE)
    return document, builder.build()
