"""The mission library.

Real flights, with their timelines, their engineering numbers, and — given
equal billing — what went wrong. A mission library that records only successes
teaches the wrong thing about spaceflight, where the interesting engineering is
almost always in the failure reports.

`vehicle_facts` exists so a learner can hold a real vehicle's numbers next to
the one they just built. Seeing that a Saturn V had a liftoff thrust-to-weight
of 1.16 is more useful than being told 1.2–1.5 is the target range.
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
                "Apollo 11 was flown on hardware that had never done the full job before, by a "
                "crew who had rehearsed only parts of it. The descent nearly did not happen: "
                "the guidance computer threw 1202 and 1201 program alarms during the final "
                "approach — an executive overflow caused by a rendezvous radar switch left in "
                "the wrong position — and a 26-year-old engineer in Mission Control had to "
                "recognise, within seconds, that the alarms were survivable.\n\n"
                "Armstrong then flew past the planned site, which was strewn with boulders, and "
                "landed with about 25 seconds of propellant margin remaining."
            ),
            launch_date="1969-07-16",
            end_date="1969-07-24",
            launch_vehicle="Saturn V (AS-506)",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna", "earth"],
            crew=["Neil Armstrong", "Michael Collins", "Buzz Aldrin"],
            timeline=[
                _event("1969-07-16", "Launch", "Lifted off from LC-39A at 13:32 UTC.", True),
                _event("1969-07-16", "Trans-lunar injection", "S-IVB reignited for 5 minutes 47 seconds."),
                _event("1969-07-19", "Lunar orbit insertion", "Service module engine, on the far side, out of contact."),
                _event("1969-07-20", "Lunar module separation", "Eagle undocked from Columbia."),
                _event("1969-07-20", "Landing", "Sea of Tranquillity, with roughly 25 seconds of propellant left.", True),
                _event("1969-07-21", "First step", "Armstrong onto the surface at 02:56 UTC.", True),
                _event("1969-07-21", "Ascent", "The ascent engine had no backup. It lit."),
                _event("1969-07-24", "Splashdown", "Pacific Ocean, 24 kilometres from the recovery ship.", True),
            ],
            discoveries=[
                "Returned 21.5 kg of lunar samples, establishing that the Moon is depleted in volatiles and probably formed from Earth material.",
                "Deployed a laser retroreflector still used today to measure the Earth–Moon distance to millimetre precision.",
                "Demonstrated that lunar dust is abrasive and electrostatically clinging — a problem every subsequent mission has had to design around.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_970_000, "kg"),
                prop("Height", 110.6, "m"),
                prop("Liftoff thrust", 34_500, "kN", note="Five F-1 engines"),
                prop("Liftoff TWR", 1.16, note="Deliberately low: the vehicle is enormous and the structure is not free"),
                prop("Stages", 3),
                prop("Payload to trans-lunar injection", 43_500, "kg"),
                text_prop("Propellants", "RP-1/LOX first stage, LH₂/LOX upper stages"),
            ],
            failures=[
                "The guidance computer raised 1202 and 1201 alarms during descent, caused by a rendezvous radar switch left in the wrong position flooding it with data. The computer's priority scheduling shed the low-priority work and kept flying — a design decision that saved the landing.",
                "The planned landing site turned out to be a boulder field. Armstrong took manual control and flew four kilometres downrange, arriving with about 25 seconds of propellant margin.",
                "A circuit-breaker needed to arm the ascent engine was broken off by a bulky suit backpack. Aldrin pushed it closed with a felt-tip pen.",
            ],
            concept_slugs=["delta-v-budget", "staging", "guidance-navigation-control"],
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
                "Fifty-six hours out, an oxygen tank exploded and took most of the service "
                "module's power, water and oxygen with it. The lunar module — designed to keep "
                "two people alive for two days — became a lifeboat for three people for four.\n\n"
                "The root cause traced back years: the tank had been dropped during handling, "
                "and a voltage mismatch during a pre-launch test had damaged its thermostat, "
                "allowing internal wiring insulation to melt. The failure was the last link in a "
                "chain that had been forming since the tank was built."
            ),
            launch_date="1970-04-11",
            end_date="1970-04-17",
            launch_vehicle="Saturn V (AS-508)",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna", "earth"],
            crew=["Jim Lovell", "Jack Swigert", "Fred Haise"],
            timeline=[
                _event("1970-04-11", "Launch", "Centre engine of the second stage shut down two minutes early; the others burned longer to compensate."),
                _event("1970-04-13", "Oxygen tank 2 ruptures", "55 hours 55 minutes in. 'Houston, we've had a problem.'", True),
                _event("1970-04-13", "Landing abandoned", "Power conserved; the crew move into the lunar module."),
                _event("1970-04-14", "Free-return trajectory", "Lunar module descent engine burned to bend the path back toward Earth.", True),
                _event("1970-04-15", "CO₂ scrubber improvised", "Square command module cartridges adapted to round lunar module sockets, using suit hoses, plastic bags and tape.", True),
                _event("1970-04-17", "Splashdown", "South Pacific, all three crew unharmed.", True),
            ],
            discoveries=[
                "Established the free-return trajectory as a survivable abort mode, which every subsequent lunar mission planned around.",
                "The Apollo 13 review board's findings reshaped how NASA reviewed test procedures and single-point failures.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_949_000, "kg"),
                prop("Peak distance from Earth", 400_171, "km", note="A crewed distance record that still stands"),
                prop("Lunar module design life", 2, "days", note="It supported three people for four"),
                prop("Power available after the failure", 20, "%", note="Of nominal command module power"),
            ],
            failures=[
                "Oxygen tank 2 ruptured after damaged thermostat contacts allowed the internal wiring to overheat and ignite. The tank had been dropped in handling years earlier, and a 65 V ground supply had been applied to a 28 V thermostat during a pre-launch detanking.",
                "The rupture also disabled oxygen tank 1 and two of three fuel cells, removing the command module's power, water and breathing oxygen at once.",
                "Carbon dioxide rose toward dangerous levels because the lunar module's scrubbers were not sized for three people. The fix was improvised from materials aboard and relayed by voice.",
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
            mission_type="Outer planet flyby, now interstellar",
            objective="Fly past Jupiter, Saturn, Uranus and Neptune, then leave the solar system.",
            overview=(
                "The Grand Tour depended on an alignment of the outer planets that recurs about "
                "every 175 years. Voyager 2 used each encounter to bend its path toward the next, "
                "arriving at Neptune twelve years after launch within a few minutes of the "
                "predicted time.\n\n"
                "Almost everything known first-hand about Uranus and Neptune comes from a few "
                "hours of these flybys, and no spacecraft has been back to either since."
            ),
            launch_date="1977-08-20",
            launch_vehicle="Titan IIIE / Centaur",
            launch_site_id="ccsfs-slc40",
            destination_ids=["jupiter", "saturn", "uranus", "neptune", "triton"],
            timeline=[
                _event("1977-08-20", "Launch", "Sixteen days before Voyager 1, on a slower trajectory.", True),
                _event("1979-07-09", "Jupiter flyby", "Discovered volcanic activity on Io and the ring system.", True),
                _event("1981-08-25", "Saturn flyby", "A scan-platform gearbox seized shortly afterwards and was recovered."),
                _event("1986-01-24", "Uranus flyby", "Ten new moons; a magnetic field tilted 59° from the rotation axis.", True),
                _event("1989-08-25", "Neptune flyby", "Great Dark Spot; nitrogen geysers on Triton.", True),
                _event("2018-11-05", "Interstellar space", "Crossed the heliopause, six years after Voyager 1.", True),
            ],
            discoveries=[
                "The only close observations ever made of Uranus and Neptune.",
                "Active nitrogen geysers on Triton — evidence of geology on a body at −235 °C.",
                "Ten previously unknown moons of Uranus and six of Neptune.",
                "Measured the heliopause from a second location, showing it is not spherically symmetric.",
            ],
            vehicle_facts=[
                prop("Launch mass", 825.5, "kg"),
                prop("Power at launch", 470, "W", note="Three radioisotope thermoelectric generators"),
                prop("Power decline", -4, "W/year", note="Instruments are switched off one by one to compensate"),
                prop("High-gain antenna", 3.7, "m"),
                prop("Current distance from Sun", 138, "AU"),
                prop("Round-trip light time", 38, "hours"),
            ],
            failures=[
                "The primary radio receiver failed in 1978. The backup has a damaged tracking loop capacitor, so every command since has had to be sent at a frequency corrected for the spacecraft's temperature and Doppler shift.",
                "The scan platform seized after the Saturn encounter. Engineers traced it to lubricant starvation and recovered the mechanism by moving it slowly, which is why the Uranus imaging sequence worked at all.",
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
            objective="Orbit Saturn, study its rings and moons, and land a probe on Titan.",
            overview=(
                "Cassini spent thirteen years in the Saturn system and ended by deliberately "
                "flying into the planet. That was a planetary-protection decision: with "
                "propellant nearly gone, an uncontrolled spacecraft might eventually have struck "
                "Enceladus or Titan, and Cassini had itself found the evidence that those moons "
                "might be habitable.\n\n"
                "It also carried Huygens, which descended through Titan's atmosphere in 2005 — "
                "the most distant landing ever achieved."
            ),
            launch_date="1997-10-15",
            end_date="2017-09-15",
            launch_vehicle="Titan IVB / Centaur",
            launch_site_id="ccsfs-slc40",
            destination_ids=["saturn", "titan", "enceladus"],
            timeline=[
                _event("1997-10-15", "Launch", "Followed by Venus, Venus, Earth and Jupiter gravity assists.", True),
                _event("2004-07-01", "Saturn orbit insertion", "A 96-minute burn, through a gap in the rings.", True),
                _event("2005-01-14", "Huygens lands on Titan", "Returned data from the surface for 72 minutes.", True),
                _event("2005-11-27", "Enceladus plumes confirmed", "Water vapour and ice venting from the south pole.", True),
                _event("2015-10-28", "Plume flythrough", "Sampled the plume directly at 49 km altitude."),
                _event("2017-04-26", "Grand Finale begins", "Twenty-two orbits between the rings and the planet.", True),
                _event("2017-09-15", "Atmospheric entry", "Transmitted until it burned up, to protect the moons.", True),
            ],
            discoveries=[
                "Liquid methane lakes and seas on Titan — the only other body known to have stable surface liquid.",
                "Water plumes from Enceladus containing salts, silica and organic molecules, implying hydrothermal activity on the ocean floor.",
                "Seven new moons, and the vertical structure of the rings measured directly.",
                "Determined that the rings are far younger than Saturn itself, probably 10 to 100 million years old.",
            ],
            vehicle_facts=[
                prop("Launch mass", 5712, "kg", note="Including 3132 kg of propellant"),
                prop("Huygens probe mass", 320, "kg"),
                prop("Power", 885, "W", note="At launch; 663 W by end of mission"),
                prop("Distance travelled", 7.9e9, "km"),
                prop("Orbits of Saturn", 294),
            ],
            failures=[
                "A design error in Huygens' radio receiver would have lost most of the descent data: the Doppler shift from Cassini's relative motion had not been accounted for in the receiver bandwidth. Discovered four years after launch, in flight, and fixed by changing Cassini's trajectory so the relative velocity fell within the receiver's range.",
                "One of Huygens' two data channels was lost at Titan because a command to switch on its receiver was omitted, taking with it half the descent imaging.",
            ],
            concept_slugs=["gravity-assist", "orbit-geometry"],
            image=image_for("cassini-craft"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="new-horizons",
            name="New Horizons",
            operator="NASA / APL",
            status="active",
            mission_type="Kuiper Belt flyby",
            objective="Make the first close observations of Pluto, then continue into the Kuiper Belt.",
            overview=(
                "New Horizons had one chance. There was no propellant to enter orbit, so the "
                "entire Pluto encounter had to happen during a flyby at 13.8 km/s, executed from "
                "a stored command sequence with Earth four and a half light-hours away.\n\n"
                "It worked. The spacecraft then took sixteen months to send the data home at "
                "about 2 kilobits per second."
            ),
            launch_date="2006-01-19",
            launch_vehicle="Atlas V 551",
            launch_site_id="ccsfs-slc40",
            destination_ids=["pluto", "jupiter"],
            timeline=[
                _event("2006-01-19", "Launch", "The fastest Earth departure ever flown, at 16.26 km/s.", True),
                _event("2007-02-28", "Jupiter gravity assist", "Cut three years from the journey.", True),
                _event("2015-07-04", "Computer anomaly", "Safe mode ten days before encounter; recovered in three days.", True),
                _event("2015-07-14", "Pluto flyby", "Closest approach 12,472 km, at 13.8 km/s.", True),
                _event("2016-10-25", "Data return complete", "Sixteen months to downlink the encounter."),
                _event("2019-01-01", "Arrokoth flyby", "The most distant object ever visited closely.", True),
            ],
            discoveries=[
                "Nitrogen glaciers actively flowing across Sputnik Planitia — a surface far younger than anyone expected.",
                "Water-ice mountains up to 3.5 km high, implying a rigid crust.",
                "A layered atmosphere extending far further from Pluto than models predicted.",
                "Arrokoth is a contact binary of two flattened lobes, evidence for gentle accretion in the early solar system.",
            ],
            vehicle_facts=[
                prop("Launch mass", 478, "kg"),
                prop("Launch velocity", 16.26, "km/s", note="Relative to Earth"),
                prop("Power at Pluto", 202, "W"),
                prop("Data rate at Pluto", 2, "kbit/s"),
                prop("Flyby speed", 13.8, "km/s"),
            ],
            failures=[
                "Ten days before the Pluto encounter the main computer entered safe mode, caused by a command sequence that asked it to compress a large file while simultaneously receiving the encounter timeline. Recovery took three days of the remaining ten, and the fault was understood well enough to guarantee it would not recur during the flyby itself.",
            ],
            concept_slugs=["gravity-assist", "delta-v-budget", "scale-of-the-universe"],
            image=image_for("new-horizons-craft"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="jwst",
            name="James Webb Space Telescope",
            operator="NASA / ESA / CSA",
            status="active",
            mission_type="Infrared space observatory",
            objective="Observe the earliest galaxies, star formation, and exoplanet atmospheres in the infrared.",
            overview=(
                "Webb had 344 single-point failure modes during deployment, every one of which "
                "had to work with no possibility of repair. The sunshield unfolded to the size of "
                "a tennis court, eighteen mirror segments aligned to within nanometres, and the "
                "observatory cooled to its operating temperature entirely by radiating heat away.\n\n"
                "The launch was so accurate that the propellant saved on trajectory correction "
                "roughly doubled the expected mission lifetime."
            ),
            launch_date="2021-12-25",
            launch_vehicle="Ariane 5 ECA",
            launch_site_id="kourou-ela3",
            destination_ids=["jwst"],
            timeline=[
                _event("2021-12-25", "Launch", "From Kourou, on an unusually precise Ariane 5 trajectory.", True),
                _event("2021-12-28", "Sunshield deployment begins", "Five layers, 21 by 14 metres."),
                _event("2022-01-08", "Primary mirror deployed", "All 18 segments latched.", True),
                _event("2022-01-24", "L2 insertion", "1.5 million km from Earth.", True),
                _event("2022-03-11", "Mirror alignment complete", "Diffraction-limited at 2 micrometres.", True),
                _event("2022-07-12", "First images released", "Including the Cosmic Cliffs and the deepest infrared image then taken.", True),
            ],
            discoveries=[
                "Galaxies at redshifts above 13, seen as they were within 350 million years of the Big Bang — earlier and more massive than models predicted.",
                "Direct detection of carbon dioxide in an exoplanet atmosphere.",
                "Resolved star formation inside dust clouds that are entirely opaque at visible wavelengths.",
            ],
            vehicle_facts=[
                prop("Primary mirror diameter", 6.5, "m", note="18 hexagonal beryllium segments"),
                prop("Collecting area", 25.4, "m²", note="Over six times Hubble's"),
                prop("Mass", 6200, "kg"),
                prop("Operating temperature", 40, "K"),
                prop("Sunshield", 21.2, "m", note="21.2 × 14.2 m, five layers"),
                prop("Deployment single-point failures", 344),
            ],
            failures=[
                "A micrometeoroid struck segment C3 in May 2022, producing an uncorrectable figure error larger than pre-launch models predicted for that mass range. The observatory now avoids pointing into its direction of travel where possible.",
                "Development ran roughly fourteen years late and ten times over the original budget — itself a case study in the cost of a design that cannot be tested end to end on the ground.",
            ],
            concept_slugs=["light", "scale-of-the-universe"],
            image=image_for("jwst"),
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
                "Hubble's first images were blurred. Its primary mirror had been ground to the "
                "wrong shape by 2.2 micrometres — a null corrector assembled with a lens spaced "
                "1.3 mm out of position, and a test that would have caught it dismissed as "
                "faulty.\n\n"
                "Because the telescope was designed to be serviced, astronauts installed "
                "corrective optics in 1993. It has since become the most scientifically "
                "productive instrument ever built."
            ),
            launch_date="1990-04-24",
            launch_vehicle="Space Shuttle Discovery (STS-31)",
            launch_site_id="ksc-lc39a",
            destination_ids=["hubble", "earth"],
            timeline=[
                _event("1990-04-24", "Launch", "Deployed from Discovery at 615 km.", True),
                _event("1990-06-27", "Spherical aberration confirmed", "The mirror is the wrong shape.", True),
                _event("1993-12-02", "Servicing Mission 1", "COSTAR corrective optics installed. Vision restored.", True),
                _event("1995-12-18", "Hubble Deep Field", "Ten days on an apparently empty patch of sky.", True),
                _event("2009-05-11", "Servicing Mission 4", "The final servicing visit before Shuttle retirement.", True),
            ],
            discoveries=[
                "Measured the Hubble constant to within a few percent, settling the age of the universe near 13.8 billion years.",
                "Provided the supernova observations that revealed the expansion of the universe is accelerating.",
                "The Deep Field images established that the observable universe contains hundreds of billions of galaxies.",
                "Confirmed that supermassive black holes are present at the centre of essentially every large galaxy.",
            ],
            vehicle_facts=[
                prop("Primary mirror diameter", 2.4, "m"),
                prop("Mass", 11_110, "kg"),
                prop("Length", 13.2, "m"),
                prop("Orbital altitude", 535, "km"),
                prop("Pointing accuracy", 0.007, "arcsec"),
                prop("Servicing missions", 5),
            ],
            failures=[
                "The primary mirror was ground to the wrong shape because the null corrector used to test it was assembled with a lens 1.3 mm out of position. Two independent tests showed the error and were dismissed as less trustworthy than the one that did not.",
                "Solar array oscillations caused by thermal cycling through day–night transitions disturbed pointing until the arrays were replaced.",
                "Gyroscope failures have repeatedly reduced the telescope to reduced-gyro modes; with no further servicing possible, this now limits its remaining life.",
            ],
            concept_slugs=["light", "orbital-decay", "failure-analysis"],
            image=image_for("hubble"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="perseverance",
            name="Mars 2020 — Perseverance",
            operator="NASA / JPL",
            status="active",
            mission_type="Mars rover and sample caching",
            objective="Look for signs of ancient microbial life in Jezero Crater and cache samples for return.",
            overview=(
                "Perseverance landed in Jezero Crater, an ancient river delta, using terrain "
                "relative navigation — comparing descent imagery against an onboard map in real "
                "time to steer away from hazards. It is drilling cores into sealed tubes for a "
                "future mission to collect.\n\n"
                "It also carried MOXIE, which produced breathable oxygen from Martian "
                "atmospheric carbon dioxide, and Ingenuity, which proved powered flight is "
                "possible in air one percent as dense as Earth's."
            ),
            launch_date="2020-07-30",
            launch_vehicle="Atlas V 541",
            launch_site_id="ccsfs-slc40",
            destination_ids=["mars", "perseverance"],
            timeline=[
                _event("2020-07-30", "Launch", "Into a Mars transfer window that opens every 26 months.", True),
                _event("2021-02-18", "Landing", "Jezero Crater, using terrain relative navigation and the sky crane.", True),
                _event("2021-04-19", "Ingenuity's first flight", "The first powered flight on another world.", True),
                _event("2021-04-20", "MOXIE produces oxygen", "5.4 g from atmospheric CO₂.", True),
                _event("2021-09-06", "First rock core sealed", "The sample-return campaign begins."),
                _event("2024-01-18", "Ingenuity's final flight", "Rotor damage after 72 flights, against a design life of five.", True),
            ],
            discoveries=[
                "Confirmed Jezero Crater held a long-lived lake and a river delta, with sediments suited to preserving biosignatures.",
                "Found igneous rocks on the crater floor, which can be radiometrically dated once returned.",
                "MOXIE demonstrated in-situ resource utilisation — the first manufacture of a consumable on another planet.",
                "Ingenuity showed that rotorcraft flight is viable on Mars, and flew 14 times its design life.",
            ],
            vehicle_facts=[
                prop("Rover mass", 1025, "kg", note="The heaviest rover landed on Mars"),
                prop("Entry velocity", 5.4, "km/s"),
                prop("Entry mass", 3440, "kg", note="Including heat shield and descent stage"),
                prop("Landing ellipse", 7.7, "km", note="Down from 20 km on earlier missions"),
                prop("Power", 110, "W", note="Radioisotope thermoelectric generator"),
                prop("Sample tubes", 43),
            ],
            failures=[
                "The first sampling attempt returned an empty tube: the rock crumbled to powder under the drill rather than producing a core. The response was to change target selection rather than the hardware.",
                "Ingenuity's final flight ended with rotor blade damage during landing over featureless terrain, where its vision-based navigation could not track surface motion reliably.",
            ],
            concept_slugs=["reentry-heating", "atmospheric-drag", "recovery"],
            image=image_for("perseverance"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="curiosity",
            name="Mars Science Laboratory — Curiosity",
            operator="NASA / JPL",
            status="active",
            mission_type="Mars rover",
            objective="Determine whether Gale Crater ever offered conditions capable of supporting microbial life.",
            overview=(
                "Curiosity was too heavy for airbags, so JPL built the sky crane: a descent stage "
                "that hovered on eight throttleable engines and winched the rover to the surface "
                "on cables before flying away to crash at a safe distance.\n\n"
                "It could not be tested end to end on Earth, and it worked on the first attempt."
            ),
            launch_date="2011-11-26",
            launch_vehicle="Atlas V 541",
            launch_site_id="ccsfs-slc40",
            destination_ids=["mars", "curiosity"],
            timeline=[
                _event("2011-11-26", "Launch"),
                _event("2012-08-06", "Sky crane landing", "Seven minutes of entry, descent and landing, fully autonomous.", True),
                _event("2013-03-12", "Habitable conditions confirmed", "Mudstone from an ancient freshwater lake.", True),
                _event("2014-09-11", "Reaches Mount Sharp", "The layered mound at the centre of Gale Crater.", True),
                _event("2018-06-07", "Organic molecules found", "Preserved in 3-billion-year-old mudstone.", True),
            ],
            discoveries=[
                "Gale Crater once held a freshwater lake with the chemistry required to support microbial life.",
                "Complex organic molecules preserved in 3-billion-year-old mudstone.",
                "Seasonal methane variation in the atmosphere that remains unexplained.",
                "Measured the radiation dose on the surface and in transit — a direct constraint on crewed mission design.",
            ],
            vehicle_facts=[
                prop("Rover mass", 899, "kg"),
                prop("Entry mass", 3893, "kg"),
                prop("Landing accuracy", 2.4, "km", note="From the centre of the target ellipse"),
                prop("Power", 110, "W"),
                prop("Distance driven", 34, "km", note="Cumulative, still increasing"),
            ],
            failures=[
                "Wheel damage appeared far earlier than expected: sharp embedded rocks punctured the thin aluminium skin. Driving software was rewritten to change how the wheels are loaded over rough ground.",
                "A memory fault in the primary computer in 2013 forced a switch to the backup, which then had to be repaired remotely to restore redundancy.",
            ],
            concept_slugs=["reentry-heating", "recovery"],
            image=image_for("curiosity"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="chandrayaan-3",
            name="Chandrayaan-3",
            operator="ISRO",
            status="completed",
            mission_type="Lunar lander and rover",
            objective="Demonstrate a soft landing near the lunar south pole and operate a rover there.",
            overview=(
                "Chandrayaan-3 followed a lander that had crashed four years earlier, and the "
                "redesign came directly from that failure report: a stronger structure, a wider "
                "landing footprint, more propellant margin, more redundancy in sensing, and "
                "software able to tolerate larger errors.\n\n"
                "It touched down at 69.37°S — closer to a pole than any previous lunar landing."
            ),
            launch_date="2023-07-14",
            end_date="2023-09-04",
            launch_vehicle="LVM3-M4",
            launch_site_id="sriharikota-slp",
            destination_ids=["luna"],
            timeline=[
                _event("2023-07-14", "Launch", "From the Second Launch Pad at Sriharikota.", True),
                _event("2023-08-05", "Lunar orbit insertion", "After a series of Earth-orbit raising burns."),
                _event("2023-08-17", "Lander separation", "Vikram separates from the propulsion module."),
                _event("2023-08-23", "Landing", "69.37°S, 32.35°E. The first landing near the south pole.", True),
                _event("2023-08-24", "Pragyan rover deployed", "Operated for one lunar day."),
                _event("2023-09-04", "Sleep mode", "Neither lander nor rover woke after the lunar night.", True),
            ],
            discoveries=[
                "Measured the lunar regolith's vertical temperature profile directly, finding a much steeper gradient than models assumed.",
                "Confirmed sulphur in the polar regolith, along with aluminium, calcium, iron, chromium and titanium.",
                "Recorded seismic activity with an onboard seismometer.",
            ],
            vehicle_facts=[
                prop("Total launch mass", 3900, "kg"),
                prop("Lander mass", 1752, "kg", note="Vikram, including the rover"),
                prop("Rover mass", 26, "kg", note="Pragyan"),
                prop("Landing site latitude", -69.37, "°"),
                prop("Mission cost", 75, "million USD"),
            ],
            failures=[
                "Its predecessor, Chandrayaan-2's Vikram lander, crashed in 2019 after a larger-than-expected velocity error during the braking phase saturated the control authority available. Chandrayaan-3's redesign widened every margin the failure report identified.",
                "Neither lander nor rover survived the lunar night, as expected — they carried no radioisotope heating and the surface reaches −180 °C.",
            ],
            concept_slugs=["delta-v-budget", "failure-analysis", "guidance-navigation-control"],
            image=image_for("moon-surface"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="artemis-1",
            name="Artemis I",
            operator="NASA",
            status="completed",
            mission_type="Uncrewed lunar test flight",
            objective="Prove the Space Launch System and Orion on a lunar trajectory before flying crew.",
            overview=(
                "Artemis I was an uncrewed shakedown: send Orion around the Moon and bring it "
                "back through a re-entry faster and hotter than any capsule had faced since "
                "Apollo. It took four launch attempts to leave the ground, defeated twice by "
                "hydrogen leaks and twice by hurricanes."
            ),
            launch_date="2022-11-16",
            end_date="2022-12-11",
            launch_vehicle="Space Launch System Block 1",
            launch_site_id="ksc-lc39a",
            destination_ids=["luna", "earth"],
            timeline=[
                _event("2022-08-29", "First attempt scrubbed", "Engine bleed sensor reading out of family."),
                _event("2022-09-03", "Second attempt scrubbed", "Hydrogen leak at the quick-disconnect."),
                _event("2022-11-16", "Launch", "01:47 EST, on the fourth attempt.", True),
                _event("2022-11-21", "Lunar flyby", "130 km above the surface."),
                _event("2022-11-25", "Distant retrograde orbit", "432,210 km from Earth — a record for a crew-rated capsule.", True),
                _event("2022-12-11", "Splashdown", "Pacific, after a skip re-entry at 11 km/s.", True),
            ],
            discoveries=[
                "Verified the Orion heat shield at lunar return velocity, though with unexpected char loss.",
                "Confirmed SLS performance to within 0.3% of predicted.",
                "Collected radiation data with mannequin-borne dosimeters for future crewed flights.",
            ],
            vehicle_facts=[
                prop("Launch mass", 2_608_000, "kg"),
                prop("Height", 98, "m"),
                prop("Liftoff thrust", 39_100, "kN", note="Four RS-25s and two five-segment boosters"),
                prop("Re-entry velocity", 11.0, "km/s"),
                prop("Heat shield peak temperature", 2760, "°C"),
                prop("Mission duration", 25.5, "days"),
            ],
            failures=[
                "Repeated liquid hydrogen leaks at the core stage quick-disconnect caused two scrubs. Hydrogen's small molecule size makes sealing it genuinely hard, and the fix involved a gentler chill-down procedure rather than new hardware.",
                "The Orion heat shield lost char material in an unexpected pattern during the skip re-entry. The investigation traced it to gases generated inside the ablator being unable to escape fast enough, and delayed Artemis II by more than a year.",
            ],
            concept_slugs=["staging", "reentry-heating", "thrust-to-weight"],
            image=image_for("artemis1"),
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
                "The station has been continuously crewed since November 2000 — the longest "
                "unbroken human presence off Earth. Its 51.6° inclination exists for a specific "
                "engineering reason: Baikonur sits at 45.96°N, and the station had to be "
                "reachable from there.\n\n"
                "At 408 km it is low enough that residual atmosphere still drags on it, so "
                "visiting vehicles periodically reboost it. Left alone it would re-enter within "
                "a couple of years."
            ),
            launch_date="1998-11-20",
            launch_vehicle="Proton-K, Space Shuttle, Soyuz, Falcon 9",
            launch_site_id="baikonur-site1",
            destination_ids=["iss", "earth"],
            timeline=[
                _event("1998-11-20", "Zarya launched", "The first module, from Baikonur.", True),
                _event("1998-12-04", "Unity attached", "First US module, joined on STS-88."),
                _event("2000-11-02", "Expedition 1 arrives", "Continuous human presence begins.", True),
                _event("2001-02-07", "Destiny laboratory", "The primary US research module."),
                _event("2011-05-16", "Assembly complete", "Final Shuttle assembly flight.", True),
                _event("2020-05-30", "Crew Dragon Demo-2", "Crewed launches return to US soil.", True),
            ],
            discoveries=[
                "Established that microgravity causes measurable bone density and muscle loss, and which countermeasures work.",
                "Protein crystals grown in microgravity have supported drug development not possible on the ground.",
                "The Alpha Magnetic Spectrometer has recorded a positron excess that remains unexplained.",
                "Demonstrated closed-loop life support recovering over 90% of water.",
            ],
            vehicle_facts=[
                prop("Mass", 419_725, "kg"),
                prop("Pressurised volume", 388, "m³"),
                prop("Orbital altitude", 408, "km"),
                prop("Orbital velocity", 7.66, "km/s"),
                prop("Orbital period", 92.9, "minutes"),
                prop("Inclination", 51.64, "°", note="Set by Baikonur's latitude"),
                prop("Power", 120, "kW"),
            ],
            failures=[
                "A coolant leak in 2013 forced an emergency spacewalk to replace an ammonia pump, with the crew working against a system that was venting.",
                "The Nauka module fired its thrusters unexpectedly after docking in 2021, rotating the entire station one and a half turns before control was recovered.",
                "Orbital debris avoidance manoeuvres are now routine, and the collision risk in this altitude band continues to rise.",
            ],
            concept_slugs=["orbital-mechanics", "orbital-decay", "orbit-geometry"],
            image=image_for("iss"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="parker-solar-probe",
            name="Parker Solar Probe",
            operator="NASA / APL",
            status="active",
            mission_type="Solar corona probe",
            objective="Fly through the Sun's corona to determine how it is heated and how the solar wind is accelerated.",
            overview=(
                "Getting close to the Sun is a problem of shedding energy, not gaining it: Earth "
                "carries 30 km/s of orbital velocity that has to go somewhere. Parker uses seven "
                "Venus gravity assists to walk its perihelion down step by step.\n\n"
                "Behind an 11.4 cm carbon-composite shield running at 1,370 °C, the instruments "
                "sit near room temperature."
            ),
            launch_date="2018-08-12",
            launch_vehicle="Delta IV Heavy with Star 48BV upper stage",
            launch_site_id="ccsfs-slc40",
            destination_ids=["sol", "venus", "parker-solar-probe"],
            timeline=[
                _event("2018-08-12", "Launch", "One of the highest-energy departures ever flown.", True),
                _event("2018-10-03", "First Venus gravity assist", "The first of seven."),
                _event("2018-11-05", "First perihelion", "24 million km — already a record."),
                _event("2021-04-28", "Enters the corona", "The first spacecraft to fly inside the solar atmosphere.", True),
                _event("2024-12-24", "Closest approach", "6.1 million km from the photosphere, at 192 km/s.", True),
            ],
            discoveries=[
                "Found magnetic 'switchbacks' — sharp reversals in the solar wind's magnetic field — that are far more common than predicted.",
                "Crossed the Alfvén surface, the boundary where the solar wind stops being magnetically connected to the Sun.",
                "Measured dust depletion close to the Sun, where solar radiation vaporises particles.",
            ],
            vehicle_facts=[
                prop("Launch mass", 685, "kg"),
                prop("Heat shield thickness", 11.4, "cm"),
                prop("Heat shield temperature", 1370, "°C"),
                prop("Peak velocity", 192, "km/s", note="The fastest object ever built"),
                prop("Closest approach", 6.1e6, "km"),
                prop("Venus gravity assists", 7),
            ],
            failures=[
                "Dust impacts at over 100 km/s have repeatedly damaged the solar array cooling system and thermal blankets. At these speeds a grain of dust vaporises into plasma on contact, and the effect on long-term survivability is still being characterised.",
            ],
            concept_slugs=["gravity-assist", "delta-v-budget"],
            image=image_for("parker"),
            sources=[BUNDLED],
        ),

        ReferenceMission(
            id="juno",
            name="Juno",
            operator="NASA / JPL",
            status="active",
            mission_type="Jupiter polar orbiter",
            objective="Determine Jupiter's internal structure, water content and magnetic field from a polar orbit.",
            overview=(
                "Juno flies a highly elliptical polar orbit that dives between Jupiter and its "
                "radiation belts, spending as little time as possible in an environment that "
                "would destroy the electronics. The avionics sit inside a titanium vault.\n\n"
                "It also runs on solar power at five astronomical units, where sunlight is 1/25th "
                "of its intensity at Earth — something no previous outer-planet mission had "
                "attempted."
            ),
            launch_date="2011-08-05",
            launch_vehicle="Atlas V 551",
            launch_site_id="ccsfs-slc40",
            destination_ids=["jupiter", "io", "europa", "ganymede"],
            timeline=[
                _event("2011-08-05", "Launch"),
                _event("2013-10-09", "Earth gravity assist", "Added 7.3 km/s.", True),
                _event("2016-07-04", "Jupiter orbit insertion", "A 35-minute burn, in the dark, out of contact.", True),
                _event("2016-10-18", "Period reduction burn cancelled", "Helium valve anomaly; the 53-day orbit is kept.", True),
                _event("2021-06-07", "Ganymede flyby", "The closest approach since Galileo."),
                _event("2022-09-29", "Europa flyby", "352 km above the surface.", True),
            ],
            discoveries=[
                "Jupiter's core is 'fuzzy' — diluted and partially dissolved rather than sharply bounded.",
                "The magnetic field is far more irregular than expected, with a concentrated feature near the equator.",
                "Cyclones arranged in stable polygons at both poles, an arrangement nobody predicted.",
                "The Great Red Spot extends at least 300 km deep.",
            ],
            vehicle_facts=[
                prop("Launch mass", 3625, "kg"),
                prop("Solar array area", 60, "m²", note="Three arrays, 9 m each"),
                prop("Power at Jupiter", 500, "W", note="From 14 kW at Earth's distance"),
                prop("Radiation vault mass", 200, "kg", note="Titanium, 1 cm walls"),
                prop("Perijove altitude", 4200, "km"),
            ],
            failures=[
                "Helium check valves opened too slowly during a pressurisation test, so the burn that would have shortened the orbit from 53 to 14 days was cancelled. The mission continued on the longer orbit, which reduced the science cadence but also cut the total radiation dose — a failure that turned out to extend the mission.",
                "The JunoCam imager has progressively degraded under radiation, as expected; it was never part of the primary science payload.",
            ],
            concept_slugs=["orbit-geometry", "gravity-assist"],
            image=image_for("juno-craft"),
            sources=[BUNDLED],
        ),
    ]


REFERENCE_MISSION_IDS = [
    "apollo-11", "apollo-13", "voyager-2", "cassini", "new-horizons", "jwst", "hubble",
    "perseverance", "curiosity", "chandrayaan-3", "artemis-1", "iss",
    "parker-solar-probe", "juno",
]


def reference_missions_by_id() -> Dict[str, ReferenceMission]:
    return {mission.id: mission for mission in build_reference_missions()}
