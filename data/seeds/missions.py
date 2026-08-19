"""A small reference mission catalogue.

`BUNDLED_REFERENCE` provenance: these are widely published facts, curated here
so the search and AI layers have missions to retrieve without depending on a
live API. They are never presented as archive data, and the freshness policy for
`bundled_reference` forbids describing them as live.

Deliberately small. This is a seed for search and demo reliability, not an
attempt to mirror an agency catalogue.
"""

from datetime import date, datetime, timezone
from typing import List

from contracts.provenance import SourceReference, SourceType

from ..models.mission import Mission, MissionOutcome
from ..models.enums import MissionStatus, MissionType

__all__ = ["BUNDLED_SOURCE", "build_missions", "MISSION_SLUGS"]

BUNDLED_SOURCE = SourceReference(
    source_name="bundled_reference",
    source_type=SourceType.BUNDLED_REFERENCE,
    retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    attribution="Curated reference data bundled with LostIntoSpacE",
)


def _mission(slug: str, **kwargs) -> Mission:
    kwargs.setdefault("canonical_id", "mission:{0}".format(slug))
    kwargs.setdefault("source_references", [BUNDLED_SOURCE])
    kwargs.setdefault("retrieved_at", BUNDLED_SOURCE.retrieved_at)
    launch_date = kwargs.get("launch_date")
    if launch_date is not None:
        kwargs.setdefault(
            "valid_at",
            datetime(launch_date.year, launch_date.month, launch_date.day,
                     tzinfo=timezone.utc),
        )
    return Mission(**kwargs)


def build_missions() -> List[Mission]:
    """The curated mission set."""
    return [
        _mission(
            "apollo-11",
            name="Apollo 11",
            aliases=["AS-506"],
            agency="NASA",
            mission_type=MissionType.CREWED,
            launch_date=date(1969, 7, 16),
            end_date=date(1969, 7, 24),
            crew=["Neil Armstrong", "Michael Collins", "Buzz Aldrin"],
            objectives=["Perform a crewed lunar landing and return safely to Earth"],
            target_canonical_ids=["moon:luna"],
            launch_vehicle_canonical_id="launch-vehicle:saturn-v",
            topics=["lunar", "crewed", "apollo", "landing"],
            description=(
                "The first mission to land humans on the Moon. The lunar module "
                "Eagle touched down in the Sea of Tranquility on 20 July 1969."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["First crewed lunar landing", "First lunar sample return"],
            ),
        ),
        _mission(
            "apollo-13",
            name="Apollo 13",
            agency="NASA",
            mission_type=MissionType.CREWED,
            launch_date=date(1970, 4, 11),
            end_date=date(1970, 4, 17),
            crew=["James Lovell", "Jack Swigert", "Fred Haise"],
            objectives=["Land in the Fra Mauro highlands"],
            target_canonical_ids=["moon:luna"],
            topics=["lunar", "crewed", "apollo", "failure", "anomaly"],
            description=(
                "An oxygen tank ruptured two days after launch, forcing the crew to "
                "abandon the landing and use the lunar module as a lifeboat."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.PARTIAL_FAILURE,
                achievements=["Crew returned safely after a critical failure"],
                anomalies=[
                    "Oxygen tank 2 ruptured during a routine stir, disabling the "
                    "service module's power and life support"
                ],
                published_lessons=[
                    "Damaged tank heater wiring during ground testing went undetected",
                    "Crew survival depended on using the lunar module beyond its "
                    "design case",
                ],
            ),
        ),
        _mission(
            "artemis-1",
            name="Artemis I",
            aliases=["Artemis 1"],
            agency="NASA",
            mission_type=MissionType.ORBITER,
            launch_date=date(2022, 11, 16),
            end_date=date(2022, 12, 11),
            objectives=[
                "Demonstrate the Space Launch System and Orion in a lunar flyby",
                "Qualify Orion's heat shield at lunar re-entry speeds",
            ],
            target_canonical_ids=["moon:luna"],
            launch_vehicle_canonical_id="launch-vehicle:sls",
            topics=["lunar", "artemis", "uncrewed test", "re-entry"],
            description=(
                "The first integrated flight of SLS and Orion, an uncrewed mission "
                "around the Moon and back."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["Orion returned at lunar re-entry velocity"],
            ),
        ),
        _mission(
            "voyager-2",
            name="Voyager 2",
            agency="NASA",
            mission_type=MissionType.FLYBY,
            launch_date=date(1977, 8, 20),
            objectives=["Survey the outer planets and their moons"],
            target_canonical_ids=[
                "planet:jupiter", "planet:saturn", "planet:uranus", "planet:neptune",
            ],
            topics=["interplanetary", "flyby", "gravity assist", "outer planets",
                    "jupiter"],
            description=(
                "The only spacecraft to visit Uranus and Neptune, using a sequence "
                "of gravity assists made possible by a rare planetary alignment."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.EXTENDED,
                achievements=[
                    "First and only flybys of Uranus and Neptune",
                    "Entered interstellar space",
                ],
            ),
        ),
        _mission(
            "galileo",
            name="Galileo",
            agency="NASA",
            mission_type=MissionType.ORBITER,
            launch_date=date(1989, 10, 18),
            end_date=date(2003, 9, 21),
            objectives=["Orbit Jupiter and study its atmosphere and moons"],
            target_canonical_ids=["planet:jupiter"],
            topics=["jupiter", "orbiter", "outer planets", "atmospheric probe"],
            description=(
                "The first spacecraft to orbit Jupiter, and the first to release an "
                "atmospheric entry probe into a giant planet."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["First Jupiter orbiter", "First giant-planet probe"],
                anomalies=["The high-gain antenna failed to deploy fully"],
            ),
        ),
        _mission(
            "juno",
            name="Juno",
            agency="NASA",
            mission_type=MissionType.ORBITER,
            launch_date=date(2011, 8, 5),
            objectives=["Determine Jupiter's interior structure and magnetic field"],
            target_canonical_ids=["planet:jupiter"],
            topics=["jupiter", "orbiter", "polar orbit", "magnetosphere"],
            description=(
                "A polar-orbiting Jupiter mission studying the planet's gravity "
                "field, magnetic field and deep atmosphere."
            ),
            outcome=MissionOutcome(status=MissionStatus.EXTENDED),
        ),
        _mission(
            "curiosity",
            name="Mars Science Laboratory (Curiosity)",
            aliases=["Curiosity", "MSL"],
            agency="NASA",
            mission_type=MissionType.ROVER,
            launch_date=date(2011, 11, 26),
            objectives=["Assess whether Gale Crater ever offered habitable conditions"],
            target_canonical_ids=["planet:mars"],
            topics=["mars", "rover", "astrobiology", "landing"],
            description=(
                "A nuclear-powered Mars rover landed by the sky-crane manoeuvre in "
                "Gale Crater in August 2012."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.EXTENDED,
                achievements=["Confirmed ancient habitable environments in Gale Crater"],
            ),
        ),
        _mission(
            "perseverance",
            name="Mars 2020 (Perseverance)",
            aliases=["Perseverance", "Mars 2020"],
            agency="NASA",
            mission_type=MissionType.ROVER,
            launch_date=date(2020, 7, 30),
            objectives=[
                "Seek signs of ancient microbial life in Jezero Crater",
                "Cache samples for later return",
            ],
            target_canonical_ids=["planet:mars"],
            topics=["mars", "rover", "sample return", "astrobiology"],
            description=(
                "A Mars rover collecting and caching samples in Jezero Crater, and "
                "carrying the Ingenuity helicopter."
            ),
            outcome=MissionOutcome(status=MissionStatus.ACTIVE),
        ),
        _mission(
            "chandrayaan-3",
            name="Chandrayaan-3",
            aliases=["CH-3"],
            agency="ISRO",
            mission_type=MissionType.LANDER,
            launch_date=date(2023, 7, 14),
            objectives=[
                "Demonstrate a safe soft landing near the lunar south pole",
                "Demonstrate rover mobility",
            ],
            target_canonical_ids=["moon:luna"],
            launch_vehicle_canonical_id="launch-vehicle:lvm3",
            topics=["lunar", "lander", "isro", "south pole"],
            description=(
                "India's third lunar mission, which landed the Vikram lander and "
                "Pragyan rover near the lunar south pole in August 2023."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=[
                    "First soft landing near the lunar south pole",
                ],
            ),
        ),
        _mission(
            "cassini",
            name="Cassini-Huygens",
            aliases=["Cassini"],
            agency="NASA",
            partner_agencies=["NASA", "ESA", "ASI"],
            mission_type=MissionType.ORBITER,
            launch_date=date(1997, 10, 15),
            end_date=date(2017, 9, 15),
            objectives=["Study Saturn, its rings and its moons"],
            target_canonical_ids=["planet:saturn"],
            topics=["saturn", "orbiter", "gravity assist", "titan", "outer planets"],
            description=(
                "A Saturn orbiter that used four gravity assists to reach the "
                "system, and delivered ESA's Huygens probe to Titan."
            ),
            outcome=MissionOutcome(
                status=MissionStatus.COMPLETED,
                achievements=["First Saturn orbiter", "First outer-planet moon landing"],
            ),
        ),
    ]


MISSION_SLUGS = [
    "apollo-11", "apollo-13", "artemis-1", "voyager-2", "galileo", "juno",
    "curiosity", "perseverance", "chandrayaan-3", "cassini",
]
