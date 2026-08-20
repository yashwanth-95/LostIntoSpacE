"""The mission library.

Real flights, presented as engineering case studies rather than as
encyclopaedia entries. Each carries a timeline, what it discovered, the numbers
that make its vehicle comparable with something a user has built, and — where
there was one — what went wrong.

The failures are not an afterthought. Apollo 13 and Challenger are here for the
same reason the simulator explains failures at all: a mission that worked
teaches you that it was possible, and a mission that did not teaches you why.
"""

from typing import Dict, List

from ._helpers import BUNDLED, prop, text_prop
from .imagery import image_for
from .models import MissionEvent, ReferenceMission

__all__ = ["build_reference_missions", "reference_missions_by_id", "REFERENCE_MISSION_IDS"]


def _event(date: str, title: str, detail: str = "", significant: bool = False) -> MissionEvent:
    return MissionEvent(date=date, title=title, detail=detail, significant=significant)


def build_reference_missions() -> List[ReferenceMission]:
    return [
        ReferenceMission(
            id="apollo-11",
            name="Apollo 11",
            operator="NASA",
            status="completed",
            mission_type="Crewed lunar landing",
            objective="Land two people on the Moon and return them safely to Earth.",
            overview=(
                "The mission that met a deadline set eight years earlier by a president who did "
                "not live to see it. What is easy to forget is how close the landing came to "
                "being called off: the guidance computer threw 1201 and 1202 alarms during "
                "descent — it was being asked to do more than it had cycles for — and Eagle "
                "landed with about 25 seconds of propellant remaining, well into the reserve, "
                "having overflown the planned site to avoid a boulder field."
            ),
            launch_date="1969-07-16",
            end_date="1969-07-24",
            launch_vehicle="Saturn V",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna"],
            crew=["Neil Armstrong", "Buzz Aldrin", "Michael Collins"],
            timeline=[
                _event("1969-07-16", "Launch from LC-39A", "Saturn V, 2,950 tonnes on the pad.", True),
                _event("1969-07-16", "Trans-lunar injection", "The S-IVB restarts to leave Earth orbit."),
                _event("1969-07-19", "Lunar orbit insertion", "Braking burn on the far side, out of contact."),
                _event("1969-07-20", "Eagle lands", "Sea of Tranquillity, with ~25 s of propellant left.", True),
                _event("1969-07-21", "First steps", "2 hours 31 minutes outside.", True),
                _event("1969-07-24", "Splashdown", "Pacific Ocean, after an 8-day mission.", True),
            ],
            discoveries=[
                "Returned 21.5 kg of lunar samples, the first material ever brought back from another world.",
                "Left a retroreflector array still used today to measure the Earth–Moon distance to millimetres.",
                "Demonstrated that lunar dust is abrasive and pervasive — a problem every subsequent programme has had to design around.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_950_000, "kg"),
                prop("Height", 110.6, "m"),
                prop("First stage thrust", 3.4e7, "N", note="Five F-1 engines"),
                prop("Stages", 3),
                prop("Payload to trans-lunar injection", 43_500, "kg"),
                text_prop("Propellants", "RP-1/LOX first stage, LH₂/LOX second and third"),
            ],
            concept_slugs=["staging", "delta-v-budget", "thrust-to-weight"],
            image=image_for("apollo11"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="apollo-13",
            name="Apollo 13",
            operator="NASA",
            status="failed",
            mission_type="Crewed lunar landing (aborted)",
            objective="Land in the Fra Mauro highlands. Aborted after an oxygen tank ruptured.",
            overview=(
                "Fifty-six hours out, a damaged oxygen tank exploded and took most of the "
                "service module's power, oxygen and water with it. The lunar module — designed "
                "for two people for two days — became a lifeboat for three people for four, and "
                "the crew came home on a free-return trajectory around the Moon.\n\n"
                "It is studied because the failure chain is a textbook one and none of its links "
                "was exotic. A tank had been dropped during handling. A thermostat was still "
                "rated for 28 V after the spacecraft moved to 65 V. A pre-flight detanking "
                "procedure was used to work around a fault, and it welded the thermostat "
                "contacts shut and cooked the wire insulation off. Every step was recorded and "
                "individually judged acceptable."
            ),
            launch_date="1970-04-11",
            end_date="1970-04-17",
            launch_vehicle="Saturn V",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna"],
            crew=["Jim Lovell", "Jack Swigert", "Fred Haise"],
            timeline=[
                _event("1970-04-11", "Launch", "Centre engine of the second stage shuts down early; the others burn longer to compensate."),
                _event("1970-04-13", "Oxygen tank 2 ruptures", "55h 55m into the mission. 'Houston, we've had a problem.'", True),
                _event("1970-04-14", "Lunar module powered up as a lifeboat", "Designed for 2 crew for 2 days; used by 3 for 4.", True),
                _event("1970-04-15", "Free-return trajectory correction", "Burned using the LM descent engine, with no guidance platform."),
                _event("1970-04-17", "Splashdown", "All three crew recovered safely.", True),
            ],
            discoveries=[
                "Established that a lunar module could sustain three crew far beyond its design case.",
                "The Cortright report traced the loss to a damaged tank, an un-upgraded thermostat and a detanking workaround — a chain of individually acceptable decisions.",
                "Drove the redesign of the service module oxygen system on every later flight.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_949_136, "kg"),
                prop("Distance from Earth at the accident", 321_860, "km"),
                prop("Lunar module design endurance", 2, "days", note="Used for 4"),
            ],
            failures=[
                "Oxygen tank 2 ruptured after damaged wiring insulation ignited in a high-pressure oxygen environment.",
                "The tank had been dropped 5 cm during handling two years earlier and its fill line was distorted.",
                "Its thermostatic switches were never upgraded from 28 V to 65 V when the ground supply changed.",
                "A detanking workaround ran the heaters for eight hours, welding the switches shut and destroying the insulation.",
            ],
            concept_slugs=["failure-analysis", "delta-v-budget"],
            image=image_for("apollo13"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="voyager-2",
            name="Voyager 2",
            operator="NASA / JPL",
            status="active",
            mission_type="Outer planet flyby and interstellar probe",
            objective="Fly past Jupiter, Saturn, Uranus and Neptune using a rare planetary alignment.",
            overview=(
                "The Grand Tour depended on an alignment of the outer planets that recurs about "
                "every 175 years, letting one spacecraft use each planet's gravity to reach the "
                "next. Voyager 2 remains the only spacecraft to have visited Uranus or Neptune, "
                "and nearly everything known first-hand about the ice giants comes from a few "
                "hours at each.\n\n"
                "It has been operating for over 48 years on plutonium that loses about four "
                "watts a year, with instruments shut down one at a time to keep the rest alive."
            ),
            launch_date="1977-08-20",
            launch_vehicle="Titan IIIE / Centaur",
            launch_site_id="ccsfs-slc40",
            destination_ids=["jupiter", "saturn", "uranus", "neptune", "triton"],
            timeline=[
                _event("1977-08-20", "Launch", "Sixteen days before Voyager 1, on a slower trajectory."),
                _event("1979-07-09", "Jupiter flyby", "Discovered the ring system and volcanic activity on Io.", True),
                _event("1981-08-25", "Saturn flyby", "Detailed ring structure; a Titan atmosphere too thick to see through."),
                _event("1986-01-24", "Uranus flyby", "The only visit ever made. Ten new moons.", True),
                _event("1989-08-25", "Neptune flyby", "The Great Dark Spot; nitrogen geysers on Triton.", True),
                _event("2018-11-05", "Crossed the heliopause", "Entered interstellar space at 119 AU.", True),
            ],
            discoveries=[
                "Found Jupiter's ring system, which had not been suspected.",
                "Discovered 16 previously unknown moons across four planets.",
                "Measured Neptune's winds at up to 2,100 km/h, the fastest in the solar system.",
                "Found active nitrogen geysers on Triton, at −235 °C.",
            ],
            vehicle_facts=[
                prop("Launch mass", 825.5, "kg"),
                prop("Power at launch", 470, "W", note="Three RTGs"),
                prop("Power decay", -4, "W/year"),
                prop("Current speed", 15.4, "km/s"),
                prop("Distance from Sun", 138, "AU"),
            ],
            concept_slugs=["gravity-assist", "scale-of-the-universe"],
            image=image_for("voyager"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="cassini",
            name="Cassini–Huygens",
            operator="NASA / ESA / ASI",
            status="completed",
            mission_type="Saturn orbiter and Titan lander",
            objective="Study Saturn, its rings and its moons; land a probe on Titan.",
            overview=(
                "Thirteen years in the Saturn system, ended deliberately. With propellant "
                "running out, Cassini was flown into Saturn's atmosphere rather than left to "
                "drift — because it might eventually have struck Enceladus or Titan, and both "
                "may be habitable. Planetary protection meant destroying a working spacecraft."
            ),
            launch_date="1997-10-15",
            end_date="2017-09-15",
            launch_vehicle="Titan IVB / Centaur",
            launch_site_id="ccsfs-slc40",
            destination_ids=["saturn", "titan", "enceladus"],
            timeline=[
                _event("1997-10-15", "Launch", "Two Venus flybys, one Earth, one Jupiter to reach Saturn."),
                _event("2004-07-01", "Saturn orbit insertion", "A 96-minute burn through a gap in the rings.", True),
                _event("2005-01-14", "Huygens lands on Titan", "The most distant landing ever achieved.", True),
                _event("2005-11-27", "Enceladus plumes confirmed", "Water venting from the south pole.", True),
                _event("2017-04-26", "Grand Finale begins", "Twenty-two orbits between the rings and the planet."),
                _event("2017-09-15", "Atmospheric entry", "Destroyed deliberately, transmitting to the end.", True),
            ],
            discoveries=[
                "Found liquid methane lakes and seas on Titan — the only other known stable surface liquid in the solar system.",
                "Discovered plumes of ocean water erupting from Enceladus, and flew through them.",
                "Detected silica grains implying hydrothermal activity on Enceladus's ocean floor.",
                "Found seven new moons and mapped ring structure at metre scale.",
            ],
            vehicle_facts=[
                prop("Launch mass", 5712, "kg", note="Including 3,132 kg of propellant"),
                prop("Height", 6.8, "m"),
                prop("Mission duration", 19.9, "years"),
                prop("Orbits of Saturn", 294),
                prop("Distance travelled", 7.9e9, "km"),
            ],
            concept_slugs=["gravity-assist", "orbit-geometry"],
            image=image_for("cassini-craft"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="jwst",
            name="James Webb Space Telescope",
            operator="NASA / ESA / CSA",
            status="active",
            mission_type="Infrared space observatory",
            objective="Observe the earliest galaxies, star formation and exoplanet atmospheres in the infrared.",
            overview=(
                "Webb's deployment had 344 single-point failure modes — mechanisms with no "
                "backup, on an observatory 1.5 million km away that no crew could ever reach. "
                "A tennis-court-sized sunshield unfolded in five layers, eighteen mirror "
                "segments aligned to nanometres, and the whole thing cooled to 40 K purely by "
                "radiating heat into space.\n\n"
                "Every one of them worked. The launch was accurate enough that the propellant "
                "saved has roughly doubled the expected mission lifetime."
            ),
            launch_date="2021-12-25",
            launch_vehicle="Ariane 5 ECA",
            launch_site_id="kourou-ela3",
            destination_ids=["jwst"],
            timeline=[
                _event("2021-12-25", "Launch from Kourou", "An unusually precise injection saves years of propellant.", True),
                _event("2022-01-04", "Sunshield fully deployed", "Five layers, 21 × 14 m, tensioned in sequence.", True),
                _event("2022-01-24", "Arrival at L2", "Insertion into a halo orbit 1.5 million km from Earth.", True),
                _event("2022-03-11", "Mirror alignment complete", "Eighteen segments phased to a fraction of a wavelength."),
                _event("2022-07-12", "First science images released", "Including the deepest infrared image then taken.", True),
            ],
            discoveries=[
                "Identified galaxies from within a few hundred million years of the Big Bang, some more massive than models predicted.",
                "Detected carbon dioxide, water and sulphur dioxide in exoplanet atmospheres.",
                "Resolved star-forming regions previously hidden entirely behind dust.",
            ],
            vehicle_facts=[
                prop("Mass", 6200, "kg"),
                prop("Primary mirror diameter", 6.5, "m", note="18 hexagonal beryllium segments"),
                prop("Collecting area", 25.4, "m²"),
                prop("Operating temperature", 40, "K"),
                prop("Distance from Earth", 1.5e6, "km"),
                prop("Single-point failures during deployment", 344),
            ],
            concept_slugs=["light", "orbit-geometry"],
            image=image_for("jwst"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="perseverance",
            name="Mars 2020 / Perseverance",
            operator="NASA / JPL",
            status="active",
            mission_type="Mars rover and sample caching",
            objective="Search Jezero Crater for signs of ancient life and cache samples for return.",
            overview=(
                "Perseverance landed in an ancient river delta and is drilling cores into sealed "
                "tubes for a return mission that has not yet been built. It also carried two "
                "demonstrations that mattered more than they looked: MOXIE, which made "
                "breathable oxygen out of the Martian atmosphere, and Ingenuity, which flew 72 "
                "times in air one percent as dense as Earth's after being designed for five."
            ),
            launch_date="2020-07-30",
            launch_vehicle="Atlas V 541",
            launch_site_id="ccsfs-slc40",
            destination_ids=["mars", "perseverance"],
            timeline=[
                _event("2020-07-30", "Launch", "Inside a 26-month transfer window."),
                _event("2021-02-18", "Landing in Jezero Crater", "Seven minutes of entry, descent and landing, fully autonomous.", True),
                _event("2021-04-19", "Ingenuity's first flight", "The first powered flight on another world.", True),
                _event("2021-04-20", "MOXIE produces oxygen", "5.4 g from atmospheric CO₂.", True),
                _event("2021-09-06", "First sample sealed", "The beginning of a cache awaiting return."),
            ],
            discoveries=[
                "Confirmed Jezero Crater held a lake and a river delta, with sediments capable of preserving biosignatures.",
                "Found organic molecules in delta rocks — not evidence of life, but of the chemistry it needs.",
                "Demonstrated in-situ resource utilisation by producing oxygen on another planet.",
            ],
            vehicle_facts=[
                prop("Rover mass", 1025, "kg"),
                prop("Entry mass", 3440, "kg"),
                prop("Entry velocity", 5.4, "km/s"),
                prop("Peak deceleration", 12, "g"),
                prop("Landing accuracy", 5, "km", note="Ellipse major axis"),
                text_prop("Landing method", "Aeroshell, supersonic parachute, then a rocket-powered sky crane"),
            ],
            concept_slugs=["reentry-heating", "atmospheric-drag", "recovery"],
            image=image_for("perseverance"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="chandrayaan-3",
            name="Chandrayaan-3",
            operator="ISRO",
            status="completed",
            mission_type="Lunar lander and rover",
            objective="Soft-land near the lunar south pole and operate a rover.",
            overview=(
                "Chandrayaan-2's lander had crashed in 2019 after its guidance software could "
                "not correct a larger-than-expected velocity error during braking. The "
                "Chandrayaan-3 redesign is a direct response: stronger legs, a wider landing "
                "footprint, more propellant margin, more sensors, and software able to tolerate "
                "much larger deviations.\n\n"
                "It landed at 69.37°S, closer to a pole than any previous lunar landing, for a "
                "total mission cost of around $75 million."
            ),
            launch_date="2023-07-14",
            end_date="2023-09-04",
            launch_vehicle="LVM3-M4",
            launch_site_id="sriharikota-slp",
            destination_ids=["luna", "chandrayaan-3"],
            timeline=[
                _event("2023-07-14", "Launch from Sriharikota", "LVM3, India's heaviest launcher.", True),
                _event("2023-08-05", "Lunar orbit insertion", "After a series of Earth-orbit raising burns."),
                _event("2023-08-23", "Vikram lands", "69.37°S — the closest to a lunar pole yet achieved.", True),
                _event("2023-08-24", "Pragyan rover deployed", "26 kg, solar powered."),
                _event("2023-09-04", "Sleep mode at lunar sunset", "The vehicles were not designed to survive the night."),
            ],
            discoveries=[
                "Measured the lunar regolith temperature profile at the south pole, finding a much steeper gradient than expected.",
                "Confirmed sulphur in the polar soil by laser-induced breakdown spectroscopy.",
                "Recorded seismic activity with the ILSA instrument.",
            ],
            vehicle_facts=[
                prop("Total launch mass", 3900, "kg"),
                prop("Lander mass", 1752, "kg"),
                prop("Rover mass", 26, "kg"),
                prop("Landing latitude", -69.37, "°"),
                prop("Mission cost", 75e6, "USD", note="Roughly"),
            ],
            failures=[
                "Chandrayaan-2's lander crashed in 2019 when guidance could not null a larger-than-expected velocity error during the braking phase.",
                "Every major change in Chandrayaan-3 — legs, footprint, propellant margin, software tolerance — traces to that failure.",
            ],
            concept_slugs=["delta-v-budget", "guidance-navigation-control", "failure-analysis"],
            image=image_for("moon-surface"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="iss",
            name="International Space Station",
            operator="NASA / Roscosmos / ESA / JAXA / CSA",
            status="active",
            mission_type="Crewed orbital laboratory",
            objective="Maintain a permanently crewed research laboratory in low Earth orbit.",
            overview=(
                "Assembled in orbit from modules launched by two different countries on "
                "incompatible vehicles, and crewed without interruption since November 2000. "
                "Its 51.6° inclination is not a scientific choice: it is the lowest inclination "
                "reachable from Baikonur at 45.96°N, and every other design decision had to fit "
                "around it."
            ),
            launch_date="1998-11-20",
            launch_vehicle="Proton-K, Space Shuttle, Soyuz, Falcon 9",
            launch_site_id="baikonur-site1",
            destination_ids=["iss", "earth"],
            timeline=[
                _event("1998-11-20", "Zarya launched", "The first module, from Baikonur.", True),
                _event("1998-12-04", "Unity joined to Zarya", "STS-88 performs the first assembly."),
                _event("2000-11-02", "Expedition 1 arrives", "Continuous human presence begins.", True),
                _event("2011-07-21", "Assembly complete", "The final Shuttle assembly flight."),
                _event("2020-05-30", "First commercial crew", "Demo-2 restores US crew launch capability."),
            ],
            discoveries=[
                "Established that microgravity causes measurable bone density loss, driving countermeasure research for long missions.",
                "Hosts the Alpha Magnetic Spectrometer, which has recorded over 200 billion cosmic ray events.",
                "Demonstrated that international assembly of incompatible hardware in orbit is possible at all.",
            ],
            vehicle_facts=[
                prop("Mass", 419_725, "kg"),
                prop("Pressurised volume", 388, "m³"),
                prop("Orbital altitude", 408, "km"),
                prop("Orbital velocity", 7.66, "km/s"),
                prop("Inclination", 51.64, "°", note="Set by Baikonur's latitude"),
                prop("Continuous crew since", 2000, "year"),
            ],
            concept_slugs=["orbital-mechanics", "orbital-decay"],
            image=image_for("iss"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="artemis-1",
            name="Artemis I",
            operator="NASA",
            status="completed",
            mission_type="Uncrewed lunar flight test",
            objective="Test the Space Launch System and Orion on a lunar trajectory before flying crew.",
            overview=(
                "The first flight of the most powerful rocket ever launched, sending an "
                "uncrewed Orion around the Moon and back to validate the heat shield at lunar "
                "return velocity — 11 km/s, roughly 40% faster than return from low Earth orbit, "
                "and a heating rate nearly twice as high."
            ),
            launch_date="2022-11-16",
            end_date="2022-12-11",
            launch_vehicle="Space Launch System Block 1",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna"],
            timeline=[
                _event("2022-11-16", "Launch from LC-39A", "39.1 MN of thrust at liftoff.", True),
                _event("2022-11-21", "Lunar flyby", "130 km above the surface."),
                _event("2022-11-25", "Distant retrograde orbit", "432,210 km from Earth — a record for a crew-rated spacecraft.", True),
                _event("2022-12-11", "Splashdown", "Heat shield validated at 2,760 °C.", True),
            ],
            discoveries=[
                "Validated the Orion heat shield at lunar return velocity, though it eroded more than predicted.",
                "Demonstrated SLS performance within 0.3% of the predicted trajectory.",
                "Recorded radiation exposure data from mannequin-mounted dosimeters for future crews.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_608_000, "kg"),
                prop("Height", 98, "m"),
                prop("Liftoff thrust", 3.91e7, "N", note="15% more than a Saturn V"),
                prop("Payload to trans-lunar injection", 27_000, "kg"),
                prop("Re-entry velocity", 11.0, "km/s"),
                prop("Peak heat shield temperature", 2760, "°C"),
            ],
            failures=[
                "Heat shield ablation was uneven and greater than models predicted, delaying Artemis II while the cause was investigated.",
                "Two earlier launch attempts were scrubbed for a hydrogen leak and a faulty engine temperature sensor.",
            ],
            concept_slugs=["staging", "reentry-heating", "thrust-to-weight"],
            image=image_for("artemis1"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="new-horizons",
            name="New Horizons",
            operator="NASA / JHUAPL",
            status="active",
            mission_type="Kuiper Belt flyby",
            objective="Make the first close observation of Pluto and continue into the Kuiper Belt.",
            overview=(
                "There was no propellant to stop. The entire Pluto encounter — every image, "
                "every spectrum, nine and a half years of travel — had to happen in a few hours "
                "during a flyby at 13.8 km/s, executed from a stored sequence with Earth four "
                "and a half light-hours away and no possibility of intervention.\n\n"
                "It also had to survive: a collision with a particle the size of a grain of rice "
                "at that speed would have ended the mission."
            ),
            launch_date="2006-01-19",
            launch_vehicle="Atlas V 551",
            launch_site_id="ccsfs-slc40",
            destination_ids=["pluto", "new-horizons"],
            timeline=[
                _event("2006-01-19", "Launch", "The fastest Earth departure ever flown, at 16.26 km/s.", True),
                _event("2007-02-28", "Jupiter gravity assist", "Cut three years from the journey.", True),
                _event("2015-07-14", "Pluto flyby", "12,500 km at closest approach.", True),
                _event("2019-01-01", "Arrokoth flyby", "The most distant object ever visited closely.", True),
            ],
            discoveries=[
                "Found nitrogen glaciers actively flowing across Sputnik Planitia.",
                "Measured water-ice mountains up to 3.5 km high on a body expected to be geologically dead.",
                "Found Pluto's atmosphere escaping far more slowly than models predicted.",
                "Showed Arrokoth to be a contact binary — two bodies that met gently and stuck.",
            ],
            vehicle_facts=[
                prop("Launch mass", 478, "kg"),
                prop("Launch velocity", 16.26, "km/s"),
                prop("Flyby velocity at Pluto", 13.8, "km/s"),
                prop("Power at Pluto", 202, "W"),
                prop("One-way light time at Pluto", 4.5, "hours"),
            ],
            concept_slugs=["gravity-assist", "delta-v-budget", "scale-of-the-universe"],
            image=image_for("new-horizons-craft"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="hubble",
            name="Hubble Space Telescope",
            operator="NASA / ESA",
            status="active",
            mission_type="Optical and ultraviolet observatory",
            objective="Observe the universe from above the atmosphere, free of its blurring and absorption.",
            overview=(
                "Launched in 1990 with a primary mirror ground to the wrong shape by 2.2 "
                "micrometres — a null corrector had been assembled with a lens 1.3 mm out of "
                "position, and the error was consistent enough across tests that it read as "
                "correct. The first images were blurred.\n\n"
                "Because Hubble had been designed to be serviced, astronauts installed "
                "corrective optics in 1993. It went on to become the most scientifically "
                "productive instrument ever built."
            ),
            launch_date="1990-04-24",
            launch_vehicle="Space Shuttle Discovery (STS-31)",
            launch_site_id="ksc-lc39a",
            destination_ids=["hubble", "earth"],
            timeline=[
                _event("1990-04-24", "Launch on STS-31", "Deployed into a 615 km orbit.", True),
                _event("1990-06-27", "Spherical aberration confirmed", "The mirror is the wrong shape.", True),
                _event("1993-12-02", "Servicing Mission 1", "COSTAR corrective optics installed.", True),
                _event("1995-12-18", "Hubble Deep Field", "Ten days on an apparently empty patch of sky.", True),
                _event("2009-05-11", "Servicing Mission 4", "The final servicing flight."),
            ],
            discoveries=[
                "Measured the Hubble constant to within a few percent, fixing the age of the universe near 13.8 billion years.",
                "Provided evidence for the accelerating expansion of the universe, and so for dark energy.",
                "The Deep Field images found thousands of galaxies in a patch of sky that looked empty.",
                "Confirmed supermassive black holes at the centres of most large galaxies.",
            ],
            vehicle_facts=[
                prop("Mass", 11_110, "kg"),
                prop("Primary mirror diameter", 2.4, "m"),
                prop("Mirror figure error", 2.2, "µm", note="The flaw that required a servicing mission"),
                prop("Orbital altitude", 535, "km"),
                prop("Pointing stability", 0.007, "arcsec"),
                prop("Servicing missions", 5),
            ],
            failures=[
                "The primary mirror was ground to the wrong shape because the null corrector used to test it was itself misassembled by 1.3 mm.",
                "The error was consistent across tests, so it read as a correct result rather than as a fault.",
                "Two independent instruments had flagged a discrepancy and were discounted in favour of the primary test.",
            ],
            concept_slugs=["light", "orbital-decay", "failure-analysis"],
            image=image_for("hubble"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="parker-solar-probe",
            name="Parker Solar Probe",
            operator="NASA / JHUAPL",
            status="active",
            mission_type="Solar corona probe",
            objective="Fly through the Sun's corona to measure how the solar wind is accelerated.",
            overview=(
                "Reaching the Sun is harder than leaving the solar system, because Earth hands "
                "any departing spacecraft 30 km/s of orbital velocity that has to be shed. "
                "Parker uses seven Venus gravity assists to walk its perihelion down, hiding "
                "behind an 11.4 cm carbon-composite shield that runs at 1,370 °C while the "
                "instruments a metre behind it stay near room temperature."
            ),
            launch_date="2018-08-12",
            launch_vehicle="Delta IV Heavy with Star 48BV",
            launch_site_id="ccsfs-slc40",
            destination_ids=["sol", "venus", "parker-solar-probe"],
            timeline=[
                _event("2018-08-12", "Launch", "One of the highest-energy departures ever flown.", True),
                _event("2018-10-29", "Closest approach record", "Passed inside Helios 2's 1976 record."),
                _event("2021-04-28", "First entry into the corona", "The first spacecraft to touch the Sun's atmosphere.", True),
                _event("2024-12-24", "Closest perihelion", "6.1 million km from the photosphere, at 692,000 km/h.", True),
            ],
            discoveries=[
                "Found magnetic 'switchbacks' — sharp reversals in the solar wind's magnetic field.",
                "Located the Alfvén critical surface, the true boundary of the solar atmosphere.",
                "Showed the solar wind is far more structured near the Sun than it appears at Earth.",
            ],
            vehicle_facts=[
                prop("Launch mass", 685, "kg"),
                prop("Peak velocity", 192, "km/s", note="The fastest object ever built"),
                prop("Closest approach", 6.1e6, "km"),
                prop("Heat shield temperature", 1370, "°C"),
                prop("Venus gravity assists", 7),
            ],
            concept_slugs=["gravity-assist", "delta-v-budget"],
            image=image_for("parker"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="voyager-1",
            name="Voyager 1",
            operator="NASA / JPL",
            status="active",
            mission_type="Outer planet flyby and interstellar probe",
            objective="Study Jupiter and Saturn closely, then continue out of the solar system.",
            overview=(
                "Voyager 1 traded the rest of the Grand Tour for one close pass at Titan. That "
                "flyby bent it out of the ecliptic plane, ruling out Uranus and Neptune "
                "forever — a deliberate choice, made because Titan's atmosphere was judged "
                "worth more than two more planets.\n\n"
                "It is now the most distant human-made object, over 25 billion kilometres out, "
                "and still returning data on four watts a year less power than the year before."
            ),
            launch_date="1977-09-05",
            launch_vehicle="Titan IIIE / Centaur",
            launch_site_id="ccsfs-slc40",
            destination_ids=["jupiter", "saturn", "titan", "voyager-1"],
            timeline=[
                _event("1977-09-05", "Launch", "Sixteen days after Voyager 2, on a faster trajectory."),
                _event("1979-03-05", "Jupiter flyby", "Found active volcanism on Io — the first seen beyond Earth.", True),
                _event("1980-11-12", "Saturn and Titan flyby", "The Titan pass ends any chance of reaching Uranus.", True),
                _event("1990-02-14", "Pale Blue Dot", "Turned around at 6 billion km to photograph Earth.", True),
                _event("2012-08-25", "Crossed the heliopause", "The first spacecraft to enter interstellar space.", True),
                _event("2023-11-14", "Telemetry corrupted", "A failing memory chip garbles data for months; patched from 24 billion km.", True),
            ],
            discoveries=[
                "Discovered active volcanoes on Io, the first volcanic activity found beyond Earth.",
                "Measured Titan's atmosphere as denser than Earth's and predominantly nitrogen.",
                "Returned the Pale Blue Dot image, taken at Carl Sagan's urging over engineering objections.",
                "Made the first direct measurements of the interstellar medium.",
            ],
            vehicle_facts=[
                prop("Launch mass", 825.5, "kg"),
                prop("Current speed", 17.0, "km/s"),
                prop("Distance from Sun", 165, "AU"),
                prop("One-way light time", 22.9, "hours"),
                prop("Power remaining", 220, "W", note="From 470 W at launch"),
            ],
            concept_slugs=["gravity-assist", "scale-of-the-universe", "light"],
            image=image_for("voyager"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="juno",
            name="Juno",
            operator="NASA / JPL",
            status="active",
            mission_type="Jupiter polar orbiter",
            objective="Map Jupiter's gravity and magnetic fields to determine whether it has a solid core.",
            overview=(
                "Juno runs on solar panels at five astronomical units, where sunlight is 1/25th "
                "as strong as at Earth — something previously assumed to require a nuclear "
                "source. Its three arrays are 9 metres long each and generate about 500 W at "
                "Jupiter.\n\n"
                "Its 53-day polar orbit is shaped to spend most of the time far outside "
                "Jupiter's radiation belts, dipping through them briefly at perijove. Even so, "
                "the electronics sit inside a titanium vault; without it they would have died "
                "within months."
            ),
            launch_date="2011-08-05",
            launch_vehicle="Atlas V 551",
            launch_site_id="ccsfs-slc40",
            destination_ids=["jupiter", "io", "europa", "ganymede"],
            timeline=[
                _event("2011-08-05", "Launch", "An Earth gravity assist in 2013 supplies the rest of the energy."),
                _event("2016-07-04", "Jupiter orbit insertion", "A 35-minute burn, executed autonomously inside the radiation belts.", True),
                _event("2016-08-27", "First close pass", "4,200 km above the cloud tops."),
                _event("2021-06-07", "Ganymede flyby", "The closest approach to Ganymede since Galileo.", True),
                _event("2022-09-29", "Europa flyby", "352 km, returning the sharpest images since 2000.", True),
            ],
            discoveries=[
                "Found Jupiter's core to be dilute and fuzzy rather than a sharp rocky centre — contradicting formation models.",
                "Photographed polygonal cyclone arrays at both poles, arranged with unexplained regularity.",
                "Measured atmospheric bands extending thousands of kilometres deep rather than being surface features.",
                "Found the magnetic field far more irregular than predicted, with a localised 'Great Blue Spot'.",
            ],
            vehicle_facts=[
                prop("Launch mass", 3625, "kg"),
                prop("Solar array span", 20, "m"),
                prop("Power at Jupiter", 500, "W", note="14 kW would be available at Earth"),
                prop("Radiation vault wall", 1, "cm", note="Titanium, ~200 kg"),
                prop("Perijove altitude", 4200, "km"),
            ],
            concept_slugs=["orbit-geometry", "gravity-assist", "gravity"],
            image=image_for("juno-craft"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="curiosity",
            name="Mars Science Laboratory / Curiosity",
            operator="NASA / JPL",
            status="active",
            mission_type="Mars rover",
            objective="Determine whether Gale Crater ever offered conditions capable of supporting microbial life.",
            overview=(
                "Curiosity was too heavy for the airbag landings that had worked before, so JPL "
                "built the sky crane: a descent stage that hovered on eight throttleable engines "
                "and winched the rover to the surface on cables before flying off to crash at a "
                "safe distance.\n\n"
                "It could not be tested end to end on Earth. The full sequence — heat shield, "
                "supersonic parachute, powered descent, winch, flyaway — had to work first time, "
                "autonomously, with a 14-minute one-way light delay. It did."
            ),
            launch_date="2011-11-26",
            launch_vehicle="Atlas V 541",
            launch_site_id="ccsfs-slc40",
            destination_ids=["mars", "curiosity"],
            timeline=[
                _event("2011-11-26", "Launch", "Within a 26-month transfer window."),
                _event("2012-08-06", "Sky crane landing", "Seven minutes of terror, executed with no human input.", True),
                _event("2013-03-12", "Habitability confirmed", "Gale Crater once held a freshwater lake.", True),
                _event("2014-09-11", "Reached Mount Sharp", "Beginning the climb through the sedimentary record."),
                _event("2018-06-07", "Organic molecules found", "Preserved in 3-billion-year-old mudstone.", True),
            ],
            discoveries=[
                "Confirmed Gale Crater held a long-lived freshwater lake with the chemistry life needs.",
                "Found complex organic molecules preserved in ancient mudstone.",
                "Detected seasonal methane variations that remain unexplained.",
                "Measured surface radiation levels, establishing the dose a crewed mission would receive.",
            ],
            vehicle_facts=[
                prop("Rover mass", 899, "kg"),
                prop("Entry mass", 3893, "kg"),
                prop("Entry velocity", 5.8, "km/s"),
                prop("Parachute diameter", 21.5, "m", note="Deployed at Mach 1.7"),
                prop("Landing ellipse", 20, "km", note="Major axis - a tenth of earlier missions'"),
                prop("Distance driven", 34, "km"),
            ],
            concept_slugs=["reentry-heating", "recovery", "guidance-navigation-control"],
            image=image_for("curiosity"),
            sources=[BUNDLED],
        ),
    ]


REFERENCE_MISSION_IDS = [
    "apollo-11", "apollo-13", "voyager-2", "cassini", "jwst", "perseverance",
    "chandrayaan-3", "iss", "artemis-1", "new-horizons", "hubble",
    "parker-solar-probe", "voyager-1", "juno", "curiosity",
]


def reference_missions_by_id() -> Dict[str, ReferenceMission]:
    return {m.id: m for m in build_reference_missions()}
