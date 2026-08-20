"""The catalog must stay internally consistent.

Cross-references between objects, missions, topics, experiments and launch
sites are written by hand, so they rot by hand too. These tests exist because a
dangling id does not fail loudly — it renders as an empty panel, which reads as
a design decision rather than as a bug.
"""

import pytest

from data.catalog import (
    build_assets,
    build_experiments,
    build_launch_sites,
    build_reference_missions,
    build_science_topics,
    build_space_objects,
    rotation_bonus_ms,
)
from data.catalog.imagery import IMAGERY
from data.catalog.launch_sites import EQUATORIAL_ROTATION_MS


@pytest.fixture(scope="module")
def catalog():
    return {
        "objects": build_space_objects(),
        "sites": build_launch_sites(),
        "topics": build_science_topics(),
        "experiments": build_experiments(),
        "missions": build_reference_missions(),
        "assets": build_assets(),
    }


# ── Identity ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "key,attribute",
    [
        ("objects", "id"),
        ("sites", "id"),
        ("topics", "slug"),
        ("experiments", "id"),
        ("missions", "id"),
        ("assets", "id"),
    ],
)
def test_ids_are_unique(catalog, key, attribute):
    ids = [getattr(item, attribute) for item in catalog[key]]
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, "duplicate {0}: {1}".format(attribute, duplicates)


# ── Cross-references ──────────────────────────────────────────


def test_object_parents_and_relations_resolve(catalog):
    known = {o.id for o in catalog["objects"]}
    for obj in catalog["objects"]:
        if obj.parent_id is not None:
            assert obj.parent_id in known, "{0} has unknown parent {1}".format(
                obj.id, obj.parent_id
            )
        for related in obj.related_ids:
            assert related in known, "{0} relates to unknown {1}".format(obj.id, related)


def test_object_missions_and_concepts_resolve(catalog):
    missions = {m.id for m in catalog["missions"]}
    slugs = {t.slug for t in catalog["topics"]}
    for obj in catalog["objects"]:
        for mission in obj.mission_ids:
            assert mission in missions, "{0} cites unknown mission {1}".format(obj.id, mission)
        for slug in obj.concept_slugs:
            assert slug in slugs, "{0} cites unknown topic {1}".format(obj.id, slug)


def test_topic_prerequisites_and_links_resolve(catalog):
    slugs = {t.slug for t in catalog["topics"]}
    objects = {o.id for o in catalog["objects"]}
    experiments = {e.id for e in catalog["experiments"]}
    for topic in catalog["topics"]:
        for prerequisite in topic.prerequisites:
            assert prerequisite in slugs, "{0} needs unknown {1}".format(topic.slug, prerequisite)
            assert prerequisite != topic.slug, "{0} is its own prerequisite".format(topic.slug)
        for object_id in topic.object_ids:
            assert object_id in objects, "{0} cites unknown object {1}".format(
                topic.slug, object_id
            )
        for experiment_id in topic.experiment_ids:
            assert experiment_id in experiments, "{0} cites unknown experiment {1}".format(
                topic.slug, experiment_id
            )


def test_experiment_topics_resolve(catalog):
    slugs = {t.slug for t in catalog["topics"]}
    for experiment in catalog["experiments"]:
        for slug in experiment.topic_slugs:
            assert slug in slugs, "{0} cites unknown topic {1}".format(experiment.id, slug)


def test_mission_references_resolve(catalog):
    objects = {o.id for o in catalog["objects"]}
    sites = {s.id for s in catalog["sites"]}
    slugs = {t.slug for t in catalog["topics"]}
    for mission in catalog["missions"]:
        if mission.launch_site_id:
            assert mission.launch_site_id in sites, "{0} launched from unknown {1}".format(
                mission.id, mission.launch_site_id
            )
        for destination in mission.destination_ids:
            assert destination in objects, "{0} targets unknown {1}".format(
                mission.id, destination
            )
        for slug in mission.concept_slugs:
            assert slug in slugs, "{0} cites unknown topic {1}".format(mission.id, slug)


# ── Content quality ───────────────────────────────────────────


def test_every_object_can_be_drawn(catalog):
    """An object with no appearance data cannot be rendered in the field."""
    for obj in catalog["objects"]:
        assert obj.appearance.radius_km > 0, obj.id
        assert obj.appearance.base_color.startswith("#"), obj.id
        assert obj.tagline and len(obj.tagline) > 20, obj.id
        assert obj.overview and len(obj.overview) > 80, obj.id


def test_every_object_carries_provenance(catalog):
    for obj in catalog["objects"]:
        assert obj.sources, "{0} has no source".format(obj.id)


def test_images_have_handwritten_alt_text():
    """Alt text that merely repeats the title is not alt text."""
    for key, image in IMAGERY.items():
        assert image.alt, "{0} has no alt text".format(key)
        assert image.alt != image.title, "{0}'s alt text is just its title".format(key)
        assert len(image.alt) > 25, "{0}'s alt text describes nothing".format(key)


def test_image_urls_are_verified_nasa_assets():
    """No hotlinking to arbitrary hosts, and nothing over plain http."""
    for key, image in IMAGERY.items():
        assert image.url.startswith("https://images-assets.nasa.gov/"), key
        assert image.credit, "{0} has no credit".format(key)


def test_topics_teach_something_specific(catalog):
    for topic in catalog["topics"]:
        assert topic.sections, "{0} has no content".format(topic.slug)
        assert topic.outcomes, "{0} states no outcomes".format(topic.slug)
        assert topic.summary and len(topic.summary) > 40, topic.slug


def test_experiments_control_their_variables(catalog):
    """An experiment that does not say what it held constant is a demonstration."""
    for experiment in catalog["experiments"]:
        assert experiment.controls, "{0} lists no controls".format(experiment.id)
        assert experiment.measures, "{0} measures nothing".format(experiment.id)
        assert experiment.hypothesis, "{0} states no hypothesis".format(experiment.id)
        assert len(experiment.explanation) > 150, "{0}'s explanation is thin".format(
            experiment.id
        )


def test_interactive_figures_declare_their_variables(catalog):
    for topic in catalog["topics"]:
        if topic.interactive is None:
            continue
        spec = topic.interactive
        assert spec.parameters, "{0}'s figure has no controls".format(topic.slug)
        assert spec.outputs, "{0}'s figure computes nothing".format(topic.slug)
        keys = [p.key for p in spec.parameters]
        assert len(keys) == len(set(keys)), "{0} has duplicate control keys".format(topic.slug)
        for parameter in spec.parameters:
            assert parameter.min < parameter.max, "{0}.{1}".format(topic.slug, parameter.key)
            assert parameter.min <= parameter.default <= parameter.max, "{0}.{1}".format(
                topic.slug, parameter.key
            )


# ── Physics the catalog itself asserts ────────────────────────


def test_launch_site_rotation_bonus_follows_the_cosine_law(catalog):
    """Latitude is the field that drives mission design, so it must be right."""
    for site in catalog["sites"]:
        expected = rotation_bonus_ms(site.latitude_deg)
        assert site.earth_rotation_bonus_ms == pytest.approx(expected, abs=0.05), site.id
        # No site can reach an inclination below its own latitude without a
        # plane change.
        assert site.min_inclination_deg == pytest.approx(abs(site.latitude_deg), abs=0.01)


def test_rotation_bonus_endpoints():
    assert rotation_bonus_ms(0.0) == pytest.approx(EQUATORIAL_ROTATION_MS)
    assert rotation_bonus_ms(90.0) == pytest.approx(0.0, abs=1e-9)
    # Kourou's entire reason for existing.
    assert rotation_bonus_ms(5.239) > 463.0


def test_earth_matches_the_constants_the_simulation_uses(catalog):
    """The catalog and the physics engine must agree about Earth."""
    earth = next(o for o in catalog["objects"] if o.id == "earth")
    values = {p.label: p.value for p in earth.physical}
    assert values["Mean radius"] == pytest.approx(6371.0, rel=1e-4)
    assert values["Gravitational parameter μ"] == pytest.approx(3.986e14, rel=1e-3)
    assert values["Surface gravity"] == pytest.approx(9.807, rel=1e-3)
