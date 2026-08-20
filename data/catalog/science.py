"""The science library.

Twenty-two topics across five strands, written to be read at a workstation
rather than in a textbook: short, specific, and anchored on a number the reader
can go and change.

Two rules govern the content.

**No walls of text.** Every topic is a handful of short sections, and every
topic that can carry an interactive figure does. Reading about the rocket
equation is worth far less than watching delta-v refuse to rise as you add
propellant.

**No maths in this file.** An :class:`InteractiveSpec` names a visualisation and
the variables the reader manipulates; the formulas live in the physics package
that the builder and the flight simulation both use. That is what stops the
teaching figure and the simulation from drifting apart and quietly disagreeing
about, say, where max-Q is.
"""

from typing import Dict, List

from ._helpers import BUNDLED
from .imagery import image_for
from .models import (
    InteractiveParameter,
    InteractiveSpec,
    ScienceTopic,
    TopicSection,
)

__all__ = ["build_science_topics", "science_topics_by_slug", "STRANDS", "SCIENCE_SLUGS"]

#: The five strands, in the order a newcomer should meet them.
STRANDS = [
    "Space fundamentals",
    "Orbital mechanics",
    "Rocket science",
    "Atmospheric flight",
    "Mission engineering",
]


def _param(key, label, minimum, maximum, default, **kwargs) -> InteractiveParameter:
    return InteractiveParameter(
        key=key, label=label, min=minimum, max=maximum, default=default, **kwargs
    )


def build_science_topics() -> List[ScienceTopic]:
    """Every topic, in reading order within each strand."""
    return _fundamentals() + _orbital() + _propulsion() + _atmospheric() + _engineering()


# ──────────────────────────────────────────────────────────────
# Strand 1 — Space fundamentals
# ──────────────────────────────────────────────────────────────


def _fundamentals() -> List[ScienceTopic]:
    return [
        ScienceTopic(
            slug="scale-of-the-universe",
            title="The problem with scale",
            strand="Space fundamentals",
            level="foundation",
            summary=(
                "Every diagram of the solar system you have ever seen is a lie about "
                "distance, and it has to be. Here is the honest version."
            ),
            outcomes=[
                "Explain why solar-system diagrams cannot be drawn to scale",
                "Convert between kilometres, astronomical units and light-time",
                "Estimate how long a signal takes to reach a given spacecraft",
            ],
            sections=[
                TopicSection(
                    heading="Shrink the Sun to a football",
                    body=(
                        "Put a 22 cm football on the ground and call it the Sun. Earth is then "
                        "a 2 mm ball — a peppercorn — 23 metres away. Jupiter is a 2 cm marble "
                        "at 120 metres. Neptune is 700 metres off, and Voyager 1 is nearly four "
                        "kilometres away.\n\n"
                        "At that scale the nearest star is another football, six thousand "
                        "kilometres distant. This is why the diagram on the classroom wall has "
                        "the planets nearly touching: the alternative is a diagram that is "
                        "almost entirely empty."
                    ),
                ),
                TopicSection(
                    heading="Distance as time",
                    body=(
                        "Once distances get large, kilometres stop being useful and the natural "
                        "unit becomes how long light takes to cross them. Light is the speed "
                        "limit for information, so light-time is also *command latency* — the "
                        "delay between deciding something and the spacecraft learning about it."
                    ),
                    equation="t = d / c,  where c = 299,792,458 m/s",
                    worked_example=(
                        "Mars at opposition sits about 78 million km away. "
                        "t = 7.8×10¹⁰ / 3.0×10⁸ ≈ 260 s, so a command takes about four and a "
                        "half minutes to arrive and the acknowledgement another four and a half. "
                        "This is exactly why entry, descent and landing has to be fully "
                        "autonomous: by the time Earth hears that the parachute opened, the "
                        "rover has already landed or already crashed."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="light-travel-time",
                title="How far is that, really?",
                instruction=(
                    "Drag the distance and watch the signal delay. Note where it stops being "
                    "possible to fly a spacecraft by hand."
                ),
                parameters=[
                    _param("distance_km", "Distance", 1e3, 2.5e10, 3.844e5,
                           unit="km", logarithmic=True, precision=0,
                           hint="From the Moon at 384,400 km to Voyager 1 at 25 billion"),
                ],
                outputs=["light_time", "round_trip", "comparison"],
                equation="t = d / c",
                equation_note="c is 299,792,458 m/s exactly — the metre is defined from it.",
            ),
            glossary={
                "Astronomical unit (AU)": "The mean Earth–Sun distance, 149,597,870.7 km.",
                "Light-second": "The distance light travels in a second, 299,792.458 km.",
                "Round-trip light time": "How long a command plus its acknowledgement takes.",
            },
            object_ids=["earth", "mars", "voyager-1", "pluto"],
            estimated_minutes=6,
            image=image_for("pale-blue-dot"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="gravity",
            title="Gravity",
            strand="Space fundamentals",
            level="foundation",
            summary=(
                "One equation governs every trajectory in this simulator. It is also the "
                "reason orbit is about going sideways, not about going up."
            ),
            outcomes=[
                "Apply Newton's law of universal gravitation",
                "Explain why weight varies with altitude but mass does not",
                "Calculate surface gravity from a body's mass and radius",
            ],
            sections=[
                TopicSection(
                    heading="An inverse-square law",
                    body=(
                        "Two masses attract along the line joining them, with a force "
                        "proportional to each mass and inversely proportional to the square of "
                        "the distance between their centres. Double the separation and the "
                        "force falls to a quarter."
                    ),
                    equation="F = G·m₁·m₂ / r²,  G = 6.674×10⁻¹¹ N·m²/kg²",
                ),
                TopicSection(
                    heading="Orbit is falling and missing",
                    body=(
                        "Gravity does not stop at the edge of the atmosphere. At the "
                        "International Space Station's altitude it is still about 89% of its "
                        "surface value, and the crew are not weightless because gravity is "
                        "absent — they are in continuous free fall. They stay up because they "
                        "are moving sideways at 7.66 km/s, fast enough that the ground curves "
                        "away beneath them as fast as they fall toward it.\n\n"
                        "This is the single most useful idea in astronautics. Getting to space "
                        "is easy: a sounding rocket does it in minutes. Getting to *orbit* means "
                        "getting fast, and that is where almost all of the energy goes."
                    ),
                    worked_example=(
                        "At 408 km, r = 6,371 + 408 = 6,779 km. "
                        "g = GM/r² = 3.986×10¹⁴ / (6.779×10⁶)² = 8.68 m/s², "
                        "which is 88.5% of the 9.807 m/s² at the surface."
                    ),
                ),
                TopicSection(
                    heading="Mass, weight and μ",
                    body=(
                        "Mass is how much of you there is; weight is how hard gravity pulls on "
                        "it. Your mass on Mars is unchanged, but you weigh 38% as much.\n\n"
                        "In practice orbital mechanics rarely uses G and M separately. What is "
                        "measured — far more precisely than either — is their product, the "
                        "standard gravitational parameter μ = GM. For Earth, "
                        "μ = 3.986004418×10¹⁴ m³/s²."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="gravity-field",
                title="Feel the inverse square",
                instruction=(
                    "Change the mass and the separation. Watch how much faster distance "
                    "weakens the force than mass strengthens it."
                ),
                parameters=[
                    _param("mass_kg", "Body mass", 1e20, 2e27, 5.972e24,
                           unit="kg", logarithmic=True, precision=2,
                           hint="From Enceladus to Jupiter"),
                    _param("radius_km", "Distance from centre", 100, 400_000, 6371,
                           unit="km", logarithmic=True, precision=0),
                    _param("test_mass_kg", "Your spacecraft", 1, 500_000, 1000,
                           unit="kg", logarithmic=True, precision=0),
                ],
                outputs=["force", "acceleration", "escape_velocity", "orbital_velocity"],
                equation="F = G·M·m / r²   and   g = G·M / r²",
                equation_note="Surface gravity is just this evaluated at r = the body's radius.",
            ),
            glossary={
                "μ (standard gravitational parameter)": "G·M for a body. Measured far more precisely than G or M alone.",
                "Free fall": "Motion under gravity alone. Orbit is free fall that keeps missing the ground.",
                "Microgravity": "The correct term for orbit. Not zero gravity — gravity is nearly full strength there.",
            },
            object_ids=["earth", "luna", "mars", "jupiter", "iss"],
            experiment_ids=["gravity-well-comparison"],
            estimated_minutes=8,
            image=image_for("iss"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="light",
            title="Light, and what it tells us",
            strand="Space fundamentals",
            level="foundation",
            summary=(
                "Almost everything known about anything beyond the solar system arrived "
                "as light. Reading it is most of astronomy."
            ),
            outcomes=[
                "Explain why different telescopes observe at different wavelengths",
                "Describe what a spectrum reveals about a distant object",
                "Explain redshift and why it means looking back in time",
            ],
            sections=[
                TopicSection(
                    heading="Visible light is a sliver",
                    body=(
                        "The electromagnetic spectrum runs from radio waves metres long to "
                        "gamma rays smaller than an atomic nucleus. Human vision covers roughly "
                        "380 to 700 nanometres of it — a fraction of a percent. Everything "
                        "outside that window is invisible to us and perfectly visible to the "
                        "right instrument.\n\n"
                        "This is why observatories are built for specific bands. Hubble works "
                        "mainly in the visible and ultraviolet. Webb works in the infrared, "
                        "which is why it can see through dust clouds that block visible light, "
                        "and why it has to be kept at 40 K — a warm telescope glows in the "
                        "infrared and drowns out what it is trying to observe."
                    ),
                ),
                TopicSection(
                    heading="A spectrum is a chemical analysis",
                    body=(
                        "Split light into its wavelengths and dark lines appear where atoms in "
                        "the path absorbed specific energies. Each element leaves a fixed "
                        "pattern, so those lines identify what the light passed through — "
                        "across billions of light-years, without a sample.\n\n"
                        "The same lines, shifted, give velocity. An object moving away has its "
                        "lines stretched toward the red; approaching, compressed toward the "
                        "blue. This is how exoplanets are detected by radial velocity, and how "
                        "the expansion of the universe was discovered."
                    ),
                ),
                TopicSection(
                    heading="Looking out is looking back",
                    body=(
                        "Light takes time. The Sun you see is eight minutes old, Andromeda is "
                        "2.5 million years old, and the most distant galaxies Webb resolves are "
                        "seen as they were within a few hundred million years of the Big Bang. "
                        "A telescope with a bigger mirror is a time machine with better range."
                    ),
                ),
            ],
            glossary={
                "Redshift": "Stretching of light toward longer wavelengths, from recession or cosmic expansion.",
                "Spectral line": "A wavelength at which a specific atom absorbs or emits. An element's fingerprint.",
                "Angular resolution": "The smallest separation a telescope can distinguish. Improves with aperture.",
            },
            object_ids=["jwst", "hubble", "sol"],
            estimated_minutes=7,
            image=image_for("carina"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="celestial-bodies",
            title="What is out there",
            strand="Space fundamentals",
            level="foundation",
            summary=(
                "Stars, planets, moons, asteroids and comets — and why the boundaries "
                "between them turn out to be arguments about definitions."
            ),
            outcomes=[
                "Classify solar system objects by how they formed and what they orbit",
                "Explain why Pluto was reclassified",
                "Describe the difference between an asteroid and a comet",
            ],
            sections=[
                TopicSection(
                    heading="The hierarchy",
                    body=(
                        "A star fuses hydrogen in its core. A planet orbits a star, is massive "
                        "enough for gravity to have pulled it round, and has cleared its orbital "
                        "neighbourhood. A dwarf planet meets the first two conditions but not "
                        "the third. A moon orbits a planet. Asteroids and comets are what was "
                        "left over."
                    ),
                ),
                TopicSection(
                    heading="Why Pluto changed category",
                    body=(
                        "Pluto did not change; the catalogue did. Once surveys started finding "
                        "other Kuiper Belt objects of comparable size — Eris is very nearly as "
                        "large and more massive — the choice was to admit a growing list of "
                        "planets or to tighten the definition. The 2006 definition added "
                        "'clears its orbital neighbourhood', which Pluto does not: it shares its "
                        "region with a great many similar bodies.\n\n"
                        "This is worth noticing as a piece of scientific practice. Definitions "
                        "are tools, and a tool that stops being useful gets replaced."
                    ),
                ),
                TopicSection(
                    heading="Asteroids and comets",
                    body=(
                        "The historical distinction was behavioural: comets grow a tail, "
                        "asteroids do not. That reduces to composition and distance. Comets "
                        "formed far enough out to retain volatile ices, and when they approach "
                        "the Sun those ices sublimate into a coma streaming behind them.\n\n"
                        "The line is blurrier than it used to be. Some asteroids have been "
                        "caught outgassing, and some comets have exhausted their volatiles "
                        "entirely and are now indistinguishable from rock."
                    ),
                ),
            ],
            glossary={
                "Kuiper Belt": "A ring of icy bodies beyond Neptune, from about 30 to 50 AU.",
                "Coma": "The gas and dust envelope around an active comet's nucleus.",
                "Hydrostatic equilibrium": "Round because its own gravity made it so. One of the planet criteria.",
            },
            object_ids=["pluto", "ceres", "halley", "bennu", "sol"],
            estimated_minutes=6,
            image=image_for("pluto"),
            sources=[BUNDLED],
        ),
    ]


# ──────────────────────────────────────────────────────────────
# Strand 2 — Orbital mechanics
# ──────────────────────────────────────────────────────────────


def _orbital() -> List[ScienceTopic]:
    return [
        ScienceTopic(
            slug="orbital-mechanics",
            title="What an orbit actually is",
            strand="Orbital mechanics",
            level="foundation",
            summary=(
                "Orbit is a speed, not an altitude. Everything else in this strand "
                "follows from that one sentence."
            ),
            outcomes=[
                "Calculate circular orbital velocity at any altitude",
                "Explain why higher orbits are slower",
                "Distinguish a suborbital hop from an orbit",
            ],
            prerequisites=["gravity"],
            sections=[
                TopicSection(
                    heading="The condition for orbit",
                    body=(
                        "For a circular orbit, gravity has to supply exactly the centripetal "
                        "acceleration the circle requires — no more, no less. Set the two equal "
                        "and the mass of the spacecraft cancels out entirely. A bolt and a space "
                        "station at the same altitude orbit at the same speed."
                    ),
                    equation="v = √(μ / r)",
                    worked_example=(
                        "At the ISS altitude, r = 6,779 km. "
                        "v = √(3.986×10¹⁴ / 6.779×10⁶) = 7,670 m/s. "
                        "That is Mach 22 at sea level, and it is why reaching orbit is hard: "
                        "the 408 km of altitude is almost incidental next to the 7.67 km/s."
                    ),
                ),
                TopicSection(
                    heading="Higher is slower",
                    body=(
                        "Because v falls as 1/√r, a higher orbit is a slower one. Low Earth "
                        "orbit runs at 7.7 km/s and circles in 90 minutes; geostationary orbit, "
                        "35,786 km up, runs at 3.07 km/s and takes exactly one sidereal day — "
                        "which is why a dish pointed at it never has to move.\n\n"
                        "This produces the result that trips up every newcomer: to catch "
                        "something ahead of you in the same orbit, you slow down. Dropping into "
                        "a lower, faster orbit lets you overtake, then raise back up to meet it. "
                        "Thrusting straight at the target pushes you into a higher, slower orbit "
                        "and you fall behind."
                    ),
                ),
                TopicSection(
                    heading="Suborbital is a different thing",
                    body=(
                        "A suborbital flight crosses the Kármán line at 100 km and comes "
                        "straight back down, because it never acquired the horizontal speed to "
                        "miss the ground. Reaching 100 km vertically costs roughly 1.4 km/s of "
                        "ideal delta-v. Reaching orbit costs about 9.4 km/s once gravity and "
                        "drag losses are paid. The altitude is the cheap part."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="orbit-shape",
                title="Fire a cannonball",
                instruction=(
                    "Newton's own thought experiment. Raise the speed until the trajectory "
                    "stops meeting the ground, then keep going until it stops closing at all."
                ),
                parameters=[
                    _param("altitude_km", "Altitude", 100, 40_000, 408, unit="km",
                           logarithmic=True, precision=0),
                    _param("velocity_ms", "Horizontal velocity", 1000, 12_000, 7670,
                           unit="m/s", precision=0,
                           hint="Circular at this altitude is marked on the dial"),
                ],
                outputs=["orbit_type", "apoapsis", "periapsis", "eccentricity", "period", "escape_margin"],
                equation="v_circular = √(μ/r),   v_escape = √(2μ/r)",
                equation_note="Between the two you get an ellipse; at or above escape, you never come back.",
            ),
            glossary={
                "Kármán line": "100 km altitude, the conventional boundary of space.",
                "Geostationary orbit": "35,786 km, where the orbital period matches Earth's rotation.",
                "Centripetal acceleration": "The inward acceleration that holds an object on a curved path.",
            },
            object_ids=["earth", "iss", "hubble"],
            experiment_ids=["orbit-insertion-sweep"],
            explains_failures=["insufficient_delta_v", "failed_to_reach_orbit"],
            estimated_minutes=9,
            image=image_for("earth"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="orbit-geometry",
            title="Reading an orbit",
            strand="Orbital mechanics",
            level="intermediate",
            summary=(
                "Six numbers describe any orbit completely. Two of them do almost all "
                "the work in mission design."
            ),
            outcomes=[
                "Interpret eccentricity, inclination, apoapsis and periapsis",
                "Explain why launch latitude constrains reachable inclination",
                "Read a set of orbital elements and picture the orbit",
            ],
            prerequisites=["orbital-mechanics"],
            sections=[
                TopicSection(
                    heading="Size and shape",
                    body=(
                        "The semi-major axis sets the size of the orbit and, with it, the "
                        "period and the total energy. Eccentricity sets the shape: 0 is a "
                        "circle, values approaching 1 are increasingly elongated ellipses, "
                        "exactly 1 is a parabola and above 1 is a hyperbola — an escape "
                        "trajectory that never returns.\n\n"
                        "The lowest point is the periapsis and the highest the apoapsis. For "
                        "Earth these are called perigee and apogee; around the Sun, perihelion "
                        "and aphelion. The vehicle moves fastest at periapsis and slowest at "
                        "apoapsis, which is Kepler's second law restated."
                    ),
                    equation="T = 2π·√(a³/μ)",
                    worked_example=(
                        "A 400 km circular orbit has a = 6,771 km. "
                        "T = 2π·√((6.771×10⁶)³ / 3.986×10¹⁴) = 5,554 s ≈ 92.6 minutes."
                    ),
                ),
                TopicSection(
                    heading="Orientation, and the one that costs money",
                    body=(
                        "Inclination is the tilt of the orbital plane against the equator. It "
                        "is the expensive element, because changing it means turning your "
                        "velocity vector rather than lengthening it, and at 7.7 km/s even a "
                        "small turn is enormous.\n\n"
                        "The consequence for mission design is hard: the lowest inclination "
                        "reachable from a launch site equals its latitude. Kennedy at 28.6°N "
                        "cannot launch directly into an equatorial orbit. Kourou at 5.2°N very "
                        "nearly can, which is worth building a spaceport in a rainforest for. "
                        "It also runs the other way — the ISS is inclined 51.6° because Baikonur "
                        "sits at 45.96°N and had to be able to reach it."
                    ),
                    equation="Δv_plane_change = 2·v·sin(Δi/2)",
                    worked_example=(
                        "Changing inclination by 28.6° in a 7.7 km/s orbit costs "
                        "2 × 7,700 × sin(14.3°) = 3,800 m/s — comparable to the entire "
                        "delta-v of an upper stage, spent on turning rather than on going "
                        "anywhere."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="orbit-elements",
                title="Six numbers, one orbit",
                instruction="Change each element and watch which ones alter the shape and which only rotate it.",
                parameters=[
                    _param("semi_major_axis_km", "Semi-major axis", 6600, 60_000, 6771,
                           unit="km", precision=0),
                    _param("eccentricity", "Eccentricity", 0.0, 0.95, 0.0, precision=3),
                    _param("inclination_deg", "Inclination", 0, 180, 51.6, unit="°", precision=1),
                    _param("argument_of_periapsis_deg", "Argument of periapsis", 0, 360, 0,
                           unit="°", precision=0),
                ],
                outputs=["apoapsis", "periapsis", "period", "velocity_at_apoapsis",
                         "velocity_at_periapsis", "plane_change_cost"],
                equation="r_apoapsis = a(1+e),   r_periapsis = a(1−e)",
            ),
            glossary={
                "Semi-major axis (a)": "Half the long axis of the ellipse. Sets period and energy.",
                "Eccentricity (e)": "How elongated the orbit is. 0 is circular, 1 is parabolic.",
                "Inclination (i)": "Tilt of the orbital plane relative to the equator.",
                "RAAN": "Right ascension of the ascending node — where the orbit crosses the equator going north.",
                "True anomaly": "Where the vehicle currently is along its orbit.",
            },
            object_ids=["iss", "hubble", "halley", "pluto"],
            estimated_minutes=10,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="delta-v-budget",
            title="The delta-v budget",
            strand="Orbital mechanics",
            level="intermediate",
            summary=(
                "Mission design is accounting. Every manoeuvre has a price in velocity "
                "change, and the vehicle either has the budget or it does not."
            ),
            outcomes=[
                "Build a delta-v budget for a multi-stage mission",
                "Identify where gravity and drag losses come from",
                "Explain why the first 200 km costs more than the next 200,000",
            ],
            prerequisites=["orbital-mechanics", "tsiolkovsky"],
            sections=[
                TopicSection(
                    heading="Delta-v is the currency",
                    body=(
                        "Delta-v is the total velocity change a vehicle can produce with the "
                        "propellant it carries. It is independent of how quickly that change is "
                        "made, which makes it the natural unit for comparing missions. If a "
                        "trip needs 9.4 km/s and your vehicle has 8.1, the mission does not "
                        "happen — no amount of clever flying closes that gap."
                    ),
                ),
                TopicSection(
                    heading="A worked budget",
                    body=(
                        "Earth surface to low Earth orbit is about 9.4 km/s of *real* delta-v, "
                        "against an ideal orbital velocity of 7.8. The extra 1.6 goes to losses:\n\n"
                        "• **Gravity loss**, 1.2–1.5 km/s — every second spent fighting gravity "
                        "before the velocity vector is horizontal.\n"
                        "• **Drag loss**, 0.1–0.3 km/s — smaller than most people expect, "
                        "because the vehicle is through the dense air quickly.\n"
                        "• **Steering loss** — thrust that goes into turning rather than "
                        "accelerating.\n\n"
                        "Against that, an eastward launch collects up to 465 m/s free from "
                        "Earth's rotation, scaled by the cosine of latitude."
                    ),
                    worked_example=(
                        "LEO to the lunar surface, from low Earth orbit:\n"
                        "  Trans-lunar injection      3,150 m/s\n"
                        "  Lunar orbit insertion        850 m/s\n"
                        "  Descent and landing        1,870 m/s\n"
                        "  Total                      5,870 m/s\n"
                        "Getting to LEO in the first place cost more than that again."
                    ),
                ),
                TopicSection(
                    heading="Halfway to anywhere",
                    body=(
                        "Robert Heinlein's line — that low Earth orbit is halfway to anywhere "
                        "in the solar system, in energy terms — is very nearly true. From LEO, "
                        "Mars transfer costs about 3.6 km/s and Jupiter about 6.3. Both are less "
                        "than the 9.4 already spent getting off the ground."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="delta-v-budget",
                title="Can this vehicle get there?",
                instruction="Pick a destination and compare its cost against what your current design can produce.",
                parameters=[
                    _param("available_delta_v_ms", "Vehicle delta-v", 0, 20_000, 9400,
                           unit="m/s", precision=0,
                           hint="Your current design's figure is loaded here automatically"),
                    _param("launch_latitude_deg", "Launch latitude", 0, 70, 28.6, unit="°", precision=1),
                ],
                outputs=["reachable_destinations", "rotation_bonus", "margin"],
                equation="Δv_total = Σ Δv_manoeuvres + losses − rotation bonus",
            ),
            glossary={
                "Gravity loss": "Delta-v spent holding the vehicle up rather than accelerating it downrange.",
                "Steering loss": "Thrust wasted on turning the velocity vector rather than lengthening it.",
                "Trans-lunar injection": "The burn that raises apogee from LEO out to the Moon's distance.",
            },
            object_ids=["earth", "luna", "mars"],
            experiment_ids=["payload-mass-sweep"],
            explains_failures=["insufficient_delta_v"],
            estimated_minutes=9,
            image=image_for("saturn-v"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="hohmann-transfer",
            title="Transfer orbits",
            strand="Orbital mechanics",
            level="intermediate",
            summary=(
                "The cheapest way between two circular orbits is an ellipse that touches "
                "both — and you must leave at exactly the right moment."
            ),
            outcomes=[
                "Calculate both burns of a Hohmann transfer",
                "Explain what a launch window is and why it recurs",
                "Say when a bi-elliptic transfer beats a Hohmann",
            ],
            prerequisites=["orbit-geometry", "delta-v-budget"],
            sections=[
                TopicSection(
                    heading="Two burns",
                    body=(
                        "Burn prograde at the lower orbit to raise apoapsis until it touches "
                        "the target orbit. Coast half an ellipse. Burn again at apoapsis to "
                        "raise periapsis and circularise. Skip the second burn and you fall "
                        "straight back to where you started — a common and instructive mistake.\n\n"
                        "For most transfers this is provably the minimum-energy two-impulse "
                        "route."
                    ),
                    equation="Δv₁ = √(μ/r₁)·(√(2r₂/(r₁+r₂)) − 1)",
                    worked_example=(
                        "LEO at 6,678 km to geostationary at 42,164 km:\n"
                        "  Δv₁ = 2,426 m/s at perigee\n"
                        "  Δv₂ = 1,466 m/s at apogee\n"
                        "  Total 3,892 m/s, transfer time 5.3 hours."
                    ),
                ),
                TopicSection(
                    heading="Launch windows",
                    body=(
                        "The transfer only works if the target is where the ellipse's apoapsis "
                        "will be when the spacecraft arrives. For an interplanetary trip that "
                        "means the two planets must be correctly phased, which happens once per "
                        "synodic period.\n\n"
                        "For Mars that is every 25.6 months. Miss it and everything — the "
                        "vehicle, the team, the funding — waits two years. This is the single "
                        "hardest scheduling constraint in the business, and it is set by "
                        "celestial mechanics rather than by anyone's preferences."
                    ),
                ),
                TopicSection(
                    heading="When three burns beat two",
                    body=(
                        "For very large ratios between the two orbits — beyond about 11.94 — a "
                        "bi-elliptic transfer wins: burn out to an apoapsis far beyond the "
                        "target, do a cheap plane and periapsis change there where velocity is "
                        "low, then come back down. It costs less delta-v and vastly more time. "
                        "Rarely worth it, but it is a good demonstration that intuition about "
                        "'shortest is cheapest' does not survive contact with orbital mechanics."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="transfer-orbit",
                title="Plan a transfer",
                instruction="Set the two orbits and read off both burns and the flight time.",
                parameters=[
                    _param("departure_altitude_km", "Departure orbit", 200, 40_000, 400,
                           unit="km", logarithmic=True, precision=0),
                    _param("arrival_altitude_km", "Target orbit", 200, 400_000, 35_786,
                           unit="km", logarithmic=True, precision=0),
                ],
                outputs=["delta_v_1", "delta_v_2", "total_delta_v", "transfer_time",
                         "bi_elliptic_better"],
                equation="Δv_total = Δv₁ + Δv₂,   t = π·√(a_transfer³/μ)",
            ),
            glossary={
                "Synodic period": "How often two orbiting bodies return to the same relative geometry.",
                "Prograde": "In the direction of motion. Burning prograde raises the opposite side of the orbit.",
                "Bi-elliptic transfer": "A three-burn route via a very high apoapsis. Cheaper for extreme ratios.",
            },
            object_ids=["earth", "mars", "luna"],
            estimated_minutes=10,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="gravity-assist",
            title="Gravity assists",
            strand="Orbital mechanics",
            level="advanced",
            summary=(
                "Stealing momentum from a planet. It looks like free energy, and the "
                "reason it is not is the interesting part."
            ),
            outcomes=[
                "Explain a gravity assist in both the planet's and the Sun's frame",
                "Say where the energy actually comes from",
                "Recognise why Parker Solar Probe needs seven of them",
            ],
            prerequisites=["orbit-geometry", "delta-v-budget"],
            sections=[
                TopicSection(
                    heading="Two frames, two stories",
                    body=(
                        "In the planet's frame nothing is gained: the spacecraft arrives at some "
                        "speed, is bent through an angle, and leaves at exactly the same speed. "
                        "A hyperbolic pass is symmetric.\n\n"
                        "In the Sun's frame the planet is moving, so bending the spacecraft's "
                        "path changes its heliocentric velocity — by up to twice the planet's "
                        "own orbital speed. The energy comes from the planet's orbit, which is "
                        "slowed by an utterly unmeasurable amount, because the mass ratio is "
                        "around 10²⁰."
                    ),
                ),
                TopicSection(
                    heading="It works in reverse",
                    body=(
                        "Passing in front of the planet instead of behind it removes energy. "
                        "That is what Parker Solar Probe does: it needs to get close to the Sun, "
                        "which means shedding most of the 30 km/s of orbital velocity it "
                        "inherited from Earth. Seven Venus flybys walk its perihelion down step "
                        "by step. Getting close to the Sun is harder than leaving the solar "
                        "system entirely."
                    ),
                    worked_example=(
                        "Voyager 2's Jupiter encounter raised its heliocentric speed by about "
                        "10 km/s. No chemical stage of the era could have supplied that; "
                        "without it the Grand Tour was impossible."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="gravity-assist",
                title="Steal some momentum",
                instruction="Change the approach geometry and watch the outbound heliocentric velocity move.",
                parameters=[
                    _param("approach_velocity_kms", "Approach speed", 2, 30, 10,
                           unit="km/s", precision=1),
                    _param("periapsis_radii", "Flyby distance", 1.05, 20, 2.0,
                           unit="planet radii", precision=2),
                    _param("planet_velocity_kms", "Planet's orbital speed", 5, 48, 13.1,
                           unit="km/s", precision=1, hint="Jupiter 13.1, Venus 35.0, Earth 29.8"),
                ],
                outputs=["deflection_angle", "velocity_change", "outbound_speed"],
                equation="sin(δ/2) = 1 / (1 + r_p·v∞²/μ)",
                equation_note="A closer pass bends the path more, so it changes velocity more.",
            ),
            glossary={
                "v∞ (hyperbolic excess velocity)": "Speed relative to the planet far from it. Unchanged by the flyby.",
                "Deflection angle": "How far the trajectory is bent. Set by flyby distance and approach speed.",
                "Oberth effect": "Burning deep in a gravity well is more efficient, because kinetic energy goes as v².",
            },
            object_ids=["jupiter", "venus", "voyager-2", "parker-solar-probe", "new-horizons"],
            estimated_minutes=8,
            image=image_for("voyager"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="orbital-decay",
            title="Orbits are not permanent",
            strand="Orbital mechanics",
            level="intermediate",
            summary=(
                "Low Earth orbit is not a vacuum. Anything left there comes down, and "
                "the schedule depends on the Sun."
            ),
            outcomes=[
                "Explain why low orbits decay",
                "Describe how solar activity changes decay rates",
                "Explain why the ISS needs reboosting",
            ],
            prerequisites=["orbital-mechanics", "atmospheric-drag"],
            sections=[
                TopicSection(
                    heading="There is still air up there",
                    body=(
                        "At 400 km the density is around 10⁻¹² kg/m³ — a trillionth of sea "
                        "level. At 7.7 km/s that is still enough to matter, because drag goes "
                        "with the square of velocity. The ISS loses roughly 2 km of altitude a "
                        "month and is reboosted by visiting vehicles.\n\n"
                        "Drag removes energy, which lowers the orbit, which puts the vehicle "
                        "into denser air, which increases drag. The process accelerates, and "
                        "the final descent from a few hundred kilometres takes days rather than "
                        "the years the decay itself took."
                    ),
                ),
                TopicSection(
                    heading="The Sun sets the timetable",
                    body=(
                        "Solar activity heats and expands the upper atmosphere, so at solar "
                        "maximum the density at a given altitude can be an order of magnitude "
                        "higher than at minimum. Skylab came down in 1979 years earlier than "
                        "planned because solar activity was underestimated.\n\n"
                        "This makes debris lifetimes genuinely hard to predict. Below about "
                        "600 km objects clear within a few decades. Above 800 km they persist "
                        "for centuries, which is why that band is where collision risk "
                        "accumulates."
                    ),
                ),
            ],
            glossary={
                "Ballistic coefficient": "Mass divided by drag area. High means it decays slowly.",
                "Reboost": "A burn to raise an orbit against decay.",
                "Kessler syndrome": "Runaway collisional cascade in a crowded orbital band.",
            },
            object_ids=["iss", "hubble", "earth"],
            explains_failures=["orbital_decay"],
            estimated_minutes=6,
            image=image_for("iss"),
            sources=[BUNDLED],
        ),
    ]


# ──────────────────────────────────────────────────────────────
# Strand 3 — Rocket science
# ──────────────────────────────────────────────────────────────


def _propulsion() -> List[ScienceTopic]:
    return [
        ScienceTopic(
            slug="thrust",
            title="Thrust",
            strand="Rocket science",
            level="foundation",
            summary=(
                "A rocket does not push against anything. It throws mass backwards, and "
                "conservation of momentum does the rest."
            ),
            outcomes=[
                "Explain thrust in terms of momentum, not of pushing against air",
                "Calculate thrust from mass flow and exhaust velocity",
                "Explain why an engine gains thrust as it climbs",
            ],
            sections=[
                TopicSection(
                    heading="Momentum, not air",
                    body=(
                        "A rocket works better in vacuum than in atmosphere. There is nothing "
                        "to push against in either case — the engine throws propellant one way "
                        "and the vehicle moves the other, and the surrounding air only gets in "
                        "the way.\n\n"
                        "The New York Times editorialised in 1920 that Robert Goddard 'seems to "
                        "lack the knowledge ladled out daily in high schools' for suggesting "
                        "otherwise. It printed a correction in 1969, the day after Apollo 11 "
                        "launched."
                    ),
                    equation="F = ṁ·v_e + (p_e − p_ambient)·A_e",
                ),
                TopicSection(
                    heading="Two terms",
                    body=(
                        "The first term is momentum: mass flow rate times exhaust velocity. The "
                        "second is pressure: if the exhaust leaves at higher pressure than the "
                        "surrounding air, that difference acting over the nozzle exit area adds "
                        "thrust.\n\n"
                        "As ambient pressure falls with altitude, the pressure term grows. A "
                        "Merlin 1D produces 845 kN at sea level and 981 kN in vacuum — the same "
                        "engine, the same propellant flow, 16% more thrust simply because there "
                        "is less air outside. This simulator models that, which is why your "
                        "thrust readout climbs during ascent without you doing anything."
                    ),
                    worked_example=(
                        "An engine flowing 140 kg/s at an exhaust velocity of 2,650 m/s "
                        "produces 140 × 2,650 = 371 kN from the momentum term alone."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="thrust-curve",
                title="Thrust against altitude",
                instruction="Set the engine's sea-level and vacuum figures, then sweep altitude.",
                parameters=[
                    _param("thrust_sea_level_kN", "Sea-level thrust", 1, 8000, 845,
                           unit="kN", logarithmic=True, precision=0),
                    _param("thrust_vacuum_kN", "Vacuum thrust", 1, 9000, 981,
                           unit="kN", logarithmic=True, precision=0),
                    _param("altitude_km", "Altitude", 0, 100, 0, unit="km", precision=1),
                ],
                outputs=["thrust_at_altitude", "ambient_pressure", "gain_over_sea_level"],
                equation="F(h) = F_vac − (F_vac − F_SL)·p(h)/p₀",
            ),
            glossary={
                "Mass flow rate (ṁ)": "Kilograms of propellant leaving the nozzle each second.",
                "Exhaust velocity (vₑ)": "How fast the propellant leaves. Directly sets specific impulse.",
                "Nozzle expansion ratio": "Exit area over throat area. Sets which altitude the nozzle suits.",
            },
            object_ids=[],
            explains_failures=["insufficient_thrust", "engine_failure"],
            estimated_minutes=7,
            image=image_for("artemis1"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="specific-impulse",
            title="Specific impulse",
            strand="Rocket science",
            level="foundation",
            summary=(
                "The efficiency figure that decides what a vehicle can do. Measured, "
                "confusingly, in seconds."
            ),
            outcomes=[
                "Explain what specific impulse measures",
                "Convert between Isp and exhaust velocity",
                "Compare chemical, nuclear and electric propulsion honestly",
            ],
            prerequisites=["thrust"],
            sections=[
                TopicSection(
                    heading="Why seconds?",
                    body=(
                        "Specific impulse is impulse per unit weight of propellant, and the "
                        "units cancel to seconds. Physically: how many seconds one kilogram of "
                        "propellant can produce one kilogram-weight of thrust.\n\n"
                        "The unit is a historical accident that survives because it is the same "
                        "number in metric and imperial. Exhaust velocity is the cleaner quantity "
                        "and they differ only by g₀."
                    ),
                    equation="I_sp = v_e / g₀,   g₀ = 9.80665 m/s²",
                ),
                TopicSection(
                    heading="What good looks like",
                    body=(
                        "Solid motors reach 250–280 s. Kerosene and liquid oxygen give 300–350. "
                        "Hydrogen and oxygen reach 450, the practical ceiling for chemistry, "
                        "because hydrogen's low molecular mass means a high exhaust velocity for "
                        "a given combustion temperature.\n\n"
                        "Ion thrusters reach 3,000 s and more — but produce millinewtons. That "
                        "trade is the whole story of propulsion: specific impulse and thrust "
                        "pull against each other, and which one you need depends on whether you "
                        "are fighting gravity or already coasting."
                    ),
                    worked_example=(
                        "An RS-25 has a vacuum Isp of 452.3 s, so "
                        "vₑ = 452.3 × 9.80665 = 4,436 m/s. That exhaust leaves the nozzle at "
                        "about Mach 13."
                    ),
                ),
                TopicSection(
                    heading="Why hydrogen is not simply better",
                    body=(
                        "Liquid hydrogen has the best Isp available to chemistry and a density "
                        "of 71 kg/m³ — a fourteenth of kerosene's. The tanks are enormous, they "
                        "need heavy insulation, and it boils off. A first stage often does "
                        "better on dense kerosene despite the lower Isp, because tank mass and "
                        "aerodynamic size cost more down low than efficiency buys."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="isp-comparison",
                title="Efficiency against thrust",
                instruction="Compare propulsion types on the two axes that actually conflict.",
                parameters=[
                    _param("isp_s", "Specific impulse", 150, 5000, 350, unit="s",
                           logarithmic=True, precision=0),
                    _param("propellant_mass_kg", "Propellant", 100, 500_000, 20_000,
                           unit="kg", logarithmic=True, precision=0),
                    _param("dry_mass_kg", "Dry mass", 50, 100_000, 3000,
                           unit="kg", logarithmic=True, precision=0),
                ],
                outputs=["exhaust_velocity", "delta_v", "mass_ratio", "propulsion_class"],
                equation="v_e = I_sp·g₀",
            ),
            glossary={
                "g₀": "Standard gravity, 9.80665 m/s². A defined constant, not a local measurement.",
                "Total impulse": "Thrust integrated over burn time. The total 'push' a motor contains.",
                "Bulk density": "Propellant mass per unit tank volume. Where hydrogen loses.",
            },
            explains_failures=["insufficient_delta_v"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="tsiolkovsky",
            title="The rocket equation",
            strand="Rocket science",
            level="intermediate",
            summary=(
                "The most important equation in astronautics, and the most discouraging. "
                "It is why rockets are enormous and payloads are small."
            ),
            outcomes=[
                "Apply the Tsiolkovsky rocket equation",
                "Explain why delta-v depends logarithmically on mass ratio",
                "Calculate the propellant fraction a mission demands",
            ],
            prerequisites=["specific-impulse"],
            sections=[
                TopicSection(
                    heading="The equation",
                    body=(
                        "Derived by Konstantin Tsiolkovsky in 1903, before anyone had flown a "
                        "liquid rocket. It says the velocity change available is the exhaust "
                        "velocity times the natural logarithm of the mass ratio — start mass "
                        "over end mass."
                    ),
                    equation="Δv = I_sp·g₀·ln(m₀/m_f)",
                ),
                TopicSection(
                    heading="The logarithm is the problem",
                    body=(
                        "Because delta-v depends on the *logarithm* of the mass ratio, gains "
                        "come brutally slowly. Doubling the propellant does not double the "
                        "delta-v; it adds one more ln(2) × vₑ, and each doubling after that adds "
                        "the same fixed amount for twice the propellant.\n\n"
                        "Run it the other way and it becomes a design constraint. Reaching orbit "
                        "needs about 9.4 km/s. With a kerolox Isp of 340 s (vₑ = 3,335 m/s), the "
                        "required mass ratio is e^(9400/3335) = 16.7. The vehicle on the pad must "
                        "be nearly seventeen times its final mass — meaning **94% propellant**, "
                        "leaving 6% for tanks, engines, structure, avionics and payload.\n\n"
                        "That is why rockets look the way they do. They are thin-walled tanks "
                        "with an engine bolted on, and there is no version of the design where "
                        "they are not."
                    ),
                    worked_example=(
                        "m₀/m_f = e^(Δv/vₑ) = e^(9400/3335) = 16.7\n"
                        "Propellant fraction = 1 − 1/16.7 = 94.0%"
                    ),
                ),
                TopicSection(
                    heading="Payload is what is left",
                    body=(
                        "Everything that is not propellant competes for the same 6%: the tanks "
                        "holding the propellant, the engines burning it, the structure carrying "
                        "the loads, and only then the payload. A kilogram added anywhere is a "
                        "kilogram taken from the payload, which is why aerospace structural "
                        "engineering is so aggressive about mass — and why the Falcon 9's "
                        "recovery hardware costs it roughly 30–40% of its expendable payload."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="rocket-equation",
                title="Watch the logarithm defeat you",
                instruction=(
                    "Add propellant and watch delta-v flatten out. Then raise Isp instead and "
                    "see which lever actually works."
                ),
                parameters=[
                    _param("dry_mass_kg", "Dry mass", 100, 100_000, 3000, unit="kg",
                           logarithmic=True, precision=0),
                    _param("propellant_mass_kg", "Propellant", 100, 2_000_000, 40_000,
                           unit="kg", logarithmic=True, precision=0),
                    _param("isp_s", "Specific impulse", 150, 480, 340, unit="s", precision=0),
                    _param("payload_mass_kg", "Payload", 0, 50_000, 500, unit="kg",
                           logarithmic=True, precision=0),
                ],
                outputs=["delta_v", "mass_ratio", "propellant_fraction", "reachable_orbit"],
                equation="Δv = I_sp·g₀·ln((m_dry + m_prop + m_payload)/(m_dry + m_payload))",
            ),
            glossary={
                "Mass ratio": "Wet mass over dry mass. The only thing besides Isp that sets delta-v.",
                "Propellant mass fraction": "Propellant as a share of total mass. Around 0.9 for a launch vehicle.",
                "Structural coefficient": "Dry structural mass over total stage mass. Lower is better and harder.",
            },
            experiment_ids=["payload-mass-sweep", "isp-sensitivity"],
            explains_failures=["insufficient_delta_v"],
            estimated_minutes=11,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="staging",
            title="Staging",
            strand="Rocket science",
            level="intermediate",
            summary=(
                "Throwing away empty tanks mid-flight, because carrying them costs more "
                "than the complexity of dropping them."
            ),
            outcomes=[
                "Explain why staging beats a single stage to orbit",
                "Calculate the total delta-v of a multi-stage vehicle",
                "Compare serial and parallel staging",
            ],
            prerequisites=["tsiolkovsky"],
            sections=[
                TopicSection(
                    heading="Empty tanks are dead weight",
                    body=(
                        "Once a tank is empty it contributes nothing but mass, and that mass "
                        "sits in the denominator of the rocket equation for the rest of the "
                        "flight. Dropping it resets the mass ratio for whatever is left.\n\n"
                        "Delta-v adds across stages, so a two-stage vehicle can produce far more "
                        "than a single stage of the same total mass. This is why every orbital "
                        "launch vehicle in history has staged."
                    ),
                    equation="Δv_total = Σᵢ I_sp,i·g₀·ln(m₀,i / m_f,i)",
                ),
                TopicSection(
                    heading="Single stage to orbit",
                    body=(
                        "SSTO is not impossible, it is merely uneconomic. The mass ratio needed "
                        "leaves so little for structure that the payload approaches zero. "
                        "Attempts — the X-33 and VentureStar among them — have foundered on "
                        "exactly this margin.\n\n"
                        "Reusability changed the argument's shape rather than its answer. The "
                        "Falcon 9 still stages; it simply flies the first stage back."
                    ),
                    worked_example=(
                        "Two stages, each Isp 300 s, each with a mass ratio of 4:\n"
                        "  Δv per stage = 300 × 9.807 × ln(4) = 4,079 m/s\n"
                        "  Total = 8,158 m/s\n"
                        "A single stage with the same total mass ratio of 4 gives only 4,079."
                    ),
                ),
                TopicSection(
                    heading="Serial and parallel",
                    body=(
                        "Serial staging stacks stages nose to tail and fires them in turn. "
                        "Parallel staging fires boosters alongside a core from liftoff, so the "
                        "core's engines are lit at sea level where they are least efficient — "
                        "the arrangement used by the Space Shuttle, Ariane 5 and Falcon Heavy.\n\n"
                        "Each separation is a hard-to-test event that must work exactly once. "
                        "Staging failures are a recurring cause of launch loss, which is the "
                        "real price of the performance."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="staging-comparison",
                title="One stage or two?",
                instruction="Split the same total mass between one and two stages and compare the delta-v.",
                parameters=[
                    _param("total_mass_kg", "Total launch mass", 1000, 1_000_000, 50_000,
                           unit="kg", logarithmic=True, precision=0),
                    _param("stage_count", "Number of stages", 1, 3, 2, precision=0, step=1),
                    _param("structural_fraction", "Structural fraction", 0.04, 0.25, 0.09,
                           precision=3, hint="Dry mass as a share of each stage. 0.09 is typical."),
                    _param("isp_s", "Specific impulse", 200, 460, 320, unit="s", precision=0),
                ],
                outputs=["delta_v_per_stage", "total_delta_v", "single_stage_comparison"],
                equation="Δv_total = Σ I_sp·g₀·ln(m₀,i/m_f,i)",
            ),
            glossary={
                "Staging event": "Separation of a spent stage. A single-shot mechanism that cannot be rehearsed in flight.",
                "Interstage": "The structure joining two stages, carrying loads until separation.",
                "Hot staging": "Igniting the upper stage before separation, to settle propellant and guarantee ignition.",
            },
            experiment_ids=["staging-comparison"],
            explains_failures=["stage_separation_failure", "insufficient_delta_v"],
            estimated_minutes=9,
            image=image_for("saturn-v"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="thrust-to-weight",
            title="Thrust-to-weight ratio",
            strand="Rocket science",
            level="foundation",
            summary=(
                "Below 1.0 the vehicle does not move. The first number to check on any "
                "design, and the most common reason one fails on the pad."
            ),
            outcomes=[
                "Calculate thrust-to-weight ratio at liftoff",
                "Explain why TWR below 1 means no flight at all",
                "Say why very high TWR is also wrong",
            ],
            prerequisites=["thrust"],
            sections=[
                TopicSection(
                    heading="The pad test",
                    body=(
                        "Thrust-to-weight is thrust divided by weight — both forces, so the "
                        "ratio is dimensionless. Below 1.0 the engine cannot lift the vehicle "
                        "and it sits on the pad burning propellant until it either shuts down "
                        "or fails.\n\n"
                        "This is the single most common failure in a first design, and the "
                        "simulator reports it explicitly rather than letting the vehicle "
                        "mysteriously fail to move."
                    ),
                    equation="TWR = F_thrust / (m·g)",
                    worked_example=(
                        "A 24,500 kg vehicle with 380 kN of sea-level thrust:\n"
                        "  weight = 24,500 × 9.807 = 240.3 kN\n"
                        "  TWR = 380 / 240.3 = 1.58 — comfortably flyable."
                    ),
                ),
                TopicSection(
                    heading="Too much is also wrong",
                    body=(
                        "Real launchers lift off at 1.2–1.5. Higher is not better for two "
                        "reasons: the vehicle reaches high dynamic pressure while still deep in "
                        "the atmosphere, driving up drag losses and structural loads, and the "
                        "acceleration keeps climbing as propellant burns off, so a vehicle "
                        "starting at 2.0 can be pulling 6 g by cutoff.\n\n"
                        "That is why real vehicles throttle down through max-Q and again near "
                        "the end of the burn. Crewed vehicles are limited to about 3 g; "
                        "uncrewed ones are limited by structure and by whatever the payload will "
                        "tolerate."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="twr-profile",
                title="Acceleration through the burn",
                instruction="Watch TWR climb as propellant burns off — the ratio you start at is not the one you end at.",
                parameters=[
                    _param("thrust_kN", "Sea-level thrust", 10, 10_000, 380, unit="kN",
                           logarithmic=True, precision=0),
                    _param("launch_mass_kg", "Launch mass", 500, 3_000_000, 24_500,
                           unit="kg", logarithmic=True, precision=0),
                    _param("propellant_fraction", "Propellant fraction", 0.3, 0.95, 0.85,
                           precision=2),
                ],
                outputs=["twr_liftoff", "twr_burnout", "peak_g", "verdict"],
                equation="TWR(t) = F / (m(t)·g)",
            ),
            glossary={
                "Liftoff TWR": "Thrust-to-weight at ignition. Must exceed 1.0, and should be about 1.2–1.5.",
                "Burnout TWR": "The ratio at engine cutoff, when the vehicle is lightest. Sets peak acceleration.",
                "Throttling": "Reducing thrust deliberately, to manage loads through max-Q or limit peak g.",
            },
            experiment_ids=["twr-threshold"],
            explains_failures=["insufficient_thrust", "excessive_g_load"],
            estimated_minutes=6,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="propellants",
            title="Propellants",
            strand="Rocket science",
            level="intermediate",
            summary=(
                "What is actually in the tanks, and why each choice buys something at "
                "the cost of something else."
            ),
            outcomes=[
                "Compare solid, liquid and hybrid propulsion",
                "Explain why hypergolics are used despite being poisonous",
                "Say why methane is displacing kerosene in new designs",
            ],
            prerequisites=["specific-impulse"],
            sections=[
                TopicSection(
                    heading="Solids",
                    body=(
                        "Fuel and oxidiser cast together into a single grain. Simple, dense, "
                        "storable for years, and capable of enormous thrust — a Shuttle SRB "
                        "produced 12.5 MN.\n\n"
                        "The catch is absolute: once lit, a solid cannot be throttled or shut "
                        "down. It burns until the grain is gone. That is acceptable for a "
                        "booster and unacceptable for anything needing control, and it is why "
                        "crewed vehicles that use solids need an escape system that can outrun "
                        "one."
                    ),
                ),
                TopicSection(
                    heading="Liquids",
                    body=(
                        "Separate fuel and oxidiser, pumped into a combustion chamber. "
                        "Throttleable, restartable, shutdownable, and far more efficient — at "
                        "the cost of turbopumps, plumbing, valves and cryogenic handling.\n\n"
                        "• **Kerolox** (RP-1 + LOX): dense, well understood, 300–340 s. Soot "
                        "makes reuse harder.\n"
                        "• **Hydrolox** (LH₂ + LOX): the best chemical Isp at 450 s, but "
                        "hydrogen's very low density means huge insulated tanks.\n"
                        "• **Methalox** (CH₄ + LOX): about 380 s, denser than hydrogen, burns "
                        "clean enough for rapid reuse, and could in principle be manufactured on "
                        "Mars from atmospheric CO₂ and subsurface water. This is why Raptor, "
                        "BE-4 and most new engines are methalox."
                    ),
                ),
                TopicSection(
                    heading="Hypergolics",
                    body=(
                        "Hydrazine and nitrogen tetroxide ignite on contact — no ignition system "
                        "at all, and therefore nothing that can fail to ignite. They are also "
                        "storable at room temperature for years.\n\n"
                        "They are also acutely toxic and carcinogenic, requiring full protective "
                        "suits to handle. That trade is accepted where reliability is worth more "
                        "than safety on the ground: the Apollo Lunar Module ascent engine was "
                        "hypergolic precisely because it had exactly one chance to light, with "
                        "two people depending on it."
                    ),
                ),
            ],
            glossary={
                "Hypergolic": "Ignites spontaneously on contact. No igniter, and nothing to fail to ignite.",
                "Cryogenic": "Stored as a liquid far below ambient temperature. Boils off continuously.",
                "Mixture ratio": "Oxidiser mass over fuel mass. Optimised for exhaust velocity, not for complete combustion.",
            },
            estimated_minutes=8,
            image=image_for("sls"),
            sources=[BUNDLED],
        ),
    ]


# ──────────────────────────────────────────────────────────────
# Strand 4 — Atmospheric flight
# ──────────────────────────────────────────────────────────────


def _atmospheric() -> List[ScienceTopic]:
    return [
        ScienceTopic(
            slug="atmospheric-drag",
            title="Drag",
            strand="Atmospheric flight",
            level="foundation",
            summary=(
                "The force that makes the first minute of flight the most expensive one, "
                "and the only force here that goes with the square of speed."
            ),
            outcomes=[
                "Apply the drag equation",
                "Explain why drag rises then falls during ascent",
                "Say what the drag coefficient does and does not capture",
            ],
            sections=[
                TopicSection(
                    heading="The drag equation",
                    body=(
                        "Drag depends on air density, on the square of speed, on the frontal "
                        "area, and on a coefficient that wraps up everything about the shape. "
                        "The square is what matters: doubling speed quadruples drag."
                    ),
                    equation="D = ½·ρ·v²·C_d·A",
                    worked_example=(
                        "A 1.5 m diameter vehicle (A = 1.767 m²) at 300 m/s, at 5 km where "
                        "ρ = 0.736 kg/m³, with C_d = 0.42:\n"
                        "  D = 0.5 × 0.736 × 300² × 0.42 × 1.767 = 24.6 kN"
                    ),
                ),
                TopicSection(
                    heading="Two quantities pulling opposite ways",
                    body=(
                        "During ascent, speed climbs and density falls. Drag is the product, so "
                        "it rises to a peak and then collapses. The peak is max-Q, and it "
                        "typically arrives 60–90 seconds in, around 11–14 km. Above roughly "
                        "100 km drag stops mattering altogether.\n\n"
                        "This is why launch vehicles are slender: frontal area is a direct "
                        "multiplier on drag, and the fairing is usually the widest thing on the "
                        "stack."
                    ),
                ),
                TopicSection(
                    heading="Cd is not a constant",
                    body=(
                        "The drag coefficient is a summary of shape, surface finish and flow "
                        "regime, and it changes sharply with Mach number — rising steeply "
                        "through the transonic region as shock waves form. A vehicle with a "
                        "subsonic C_d of 0.4 can peak near 0.8 around Mach 1.\n\n"
                        "This simulator models that rise, which is why your drag readout jumps "
                        "as you go supersonic even though nothing about the vehicle changed."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="drag-curve",
                title="Where does the drag go?",
                instruction="Change altitude and speed independently and watch which one dominates.",
                parameters=[
                    _param("altitude_km", "Altitude", 0, 80, 10, unit="km", precision=1),
                    _param("velocity_ms", "Velocity", 0, 3000, 400, unit="m/s", precision=0),
                    _param("diameter_m", "Vehicle diameter", 0.1, 10, 1.5, unit="m", precision=2),
                    _param("drag_coefficient", "Subsonic C_d", 0.1, 1.2, 0.42, precision=2),
                ],
                outputs=["air_density", "dynamic_pressure", "mach", "effective_cd", "drag_force"],
                equation="D = ½·ρ(h)·v²·C_d(M)·A",
            ),
            glossary={
                "Reference area": "The area the drag coefficient is defined against. Usually the maximum cross-section.",
                "Transonic": "Roughly Mach 0.8 to 1.2, where flow is mixed subsonic and supersonic and drag rises sharply.",
                "Ballistic coefficient": "Mass over drag area. High means drag matters less relative to inertia.",
            },
            object_ids=["earth", "mars", "titan"],
            experiment_ids=["drag-area-sweep"],
            explains_failures=["excessive_dynamic_pressure", "aerodynamic_breakup"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="dynamic-pressure",
            title="Dynamic pressure and max-Q",
            strand="Atmospheric flight",
            level="intermediate",
            summary=(
                "The moment of peak aerodynamic load. It is why launch commentary always "
                "calls it out, and why engines throttle down there."
            ),
            outcomes=[
                "Calculate dynamic pressure",
                "Explain where max-Q occurs and why",
                "Explain why vehicles throttle through it",
            ],
            prerequisites=["atmospheric-drag"],
            sections=[
                TopicSection(
                    heading="q",
                    body=(
                        "Dynamic pressure is the kinetic energy per unit volume of the oncoming "
                        "air. It is the number that determines aerodynamic force on the "
                        "airframe, and structural design is sized against its maximum."
                    ),
                    equation="q = ½·ρ·v²",
                    worked_example=(
                        "At 11 km, ρ = 0.365 kg/m³. At 400 m/s:\n"
                        "  q = 0.5 × 0.365 × 400² = 29.2 kPa — about a third of sea-level "
                        "atmospheric pressure, pressing on the vehicle's frontal area."
                    ),
                ),
                TopicSection(
                    heading="Why the throttle comes back",
                    body=(
                        "Because q is a product of a falling density and a rising velocity, it "
                        "has a single peak. Real vehicles deliberately reduce thrust through it: "
                        "the Shuttle's 'go at throttle up' call marked the *end* of a throttle "
                        "bucket taken to keep max-Q within structural limits.\n\n"
                        "Typical launch vehicles peak at 30–40 kPa. Pushing higher means either "
                        "a heavier airframe or a smaller margin, and neither is free."
                    ),
                ),
                TopicSection(
                    heading="q times alpha",
                    body=(
                        "Dynamic pressure alone is a symmetric load the vehicle is built for. "
                        "Multiply it by the angle of attack and you get the *lateral* load — a "
                        "bending moment on a long thin tube, which is far more dangerous.\n\n"
                        "This is why a launch can be scrubbed for upper-level wind shear on a "
                        "cloudless day. Wind at altitude drives angle of attack, and q·α is what "
                        "the airframe actually cares about. This simulator computes it from the "
                        "real wind profile at your selected launch site."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="max-q-profile",
                title="Find max-Q",
                instruction="Fly a profile and watch dynamic pressure peak and collapse.",
                parameters=[
                    _param("liftoff_twr", "Liftoff TWR", 1.0, 3.0, 1.4, precision=2),
                    _param("burn_time_s", "Burn time", 30, 300, 150, unit="s", precision=0),
                    _param("drag_coefficient", "C_d", 0.1, 1.0, 0.42, precision=2),
                ],
                outputs=["max_q", "max_q_altitude", "max_q_time", "structural_margin"],
                equation="q(t) = ½·ρ(h(t))·v(t)²",
            ),
            glossary={
                "Max-Q": "The point of maximum dynamic pressure. Usually 60–90 s in, around 11–14 km.",
                "q·α": "Dynamic pressure times angle of attack. The lateral bending load.",
                "Throttle bucket": "A deliberate thrust reduction through max-Q to keep loads in limits.",
            },
            explains_failures=["excessive_dynamic_pressure", "aerodynamic_breakup", "excessive_q_alpha"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="atmosphere-structure",
            title="The atmosphere by the numbers",
            strand="Atmospheric flight",
            level="intermediate",
            summary=(
                "Half the air is below 5.6 km. Almost all of the drag problem lives in "
                "the first two minutes."
            ),
            outcomes=[
                "Read a standard atmosphere profile",
                "Explain what scale height means",
                "Explain why launch-day weather changes the trajectory",
            ],
            sections=[
                TopicSection(
                    heading="Exponential, near enough",
                    body=(
                        "Density falls roughly exponentially with altitude, with a scale height "
                        "of about 8.5 km — the distance over which it drops by a factor of e. "
                        "Half the atmosphere's mass sits below 5.6 km, and 99.99997% below "
                        "100 km.\n\n"
                        "This simulator uses the US Standard Atmosphere 1976, a seven-layer "
                        "piecewise model from sea level to 86 km with exponential decay above."
                    ),
                    equation="ρ(h) ≈ ρ₀·e^(−h/H),   H ≈ 8,500 m",
                ),
                TopicSection(
                    heading="Layers, and where temperature turns around",
                    body=(
                        "Temperature does not fall monotonically. It drops through the "
                        "troposphere at 6.5 K/km to −56.5 °C at 11 km, holds constant through "
                        "the lower stratosphere, then *rises* again as ozone absorbs "
                        "ultraviolet, peaking near 0 °C at 50 km before falling once more.\n\n"
                        "That matters for a launch because the speed of sound depends only on "
                        "temperature. Mach 1 is 340 m/s at sea level and 295 m/s at 11 km, so a "
                        "vehicle can go transonic at a lower true airspeed than expected."
                    ),
                ),
                TopicSection(
                    heading="The standard day is not today",
                    body=(
                        "The standard atmosphere describes an average, and a launch never "
                        "happens on one. A hot, humid, low-pressure morning has measurably "
                        "thinner air than the model says — and humid air is *less* dense than "
                        "dry, because a water molecule is lighter than the nitrogen it "
                        "displaces.\n\n"
                        "This platform fetches real conditions at your launch site and applies "
                        "them as offsets to the standard profile. Between a hot humid day and a "
                        "cold dry one the surface density differs by nearly 19%, and drag "
                        "differs by the same fraction."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="atmosphere-profile",
                title="Fly up through the air",
                instruction="Sweep altitude and watch pressure, density and the speed of sound diverge.",
                parameters=[
                    _param("altitude_km", "Altitude", 0, 100, 0, unit="km", precision=1),
                    _param("surface_temperature_C", "Surface temperature", -30, 45, 15,
                           unit="°C", precision=1),
                    _param("surface_pressure_hPa", "Surface pressure", 950, 1050, 1013.25,
                           unit="hPa", precision=1),
                    _param("relative_humidity", "Relative humidity", 0, 1, 0.0, precision=2),
                ],
                outputs=["temperature", "pressure", "density", "speed_of_sound",
                         "density_vs_standard"],
                equation="US Standard Atmosphere 1976, with surface anomalies decaying to zero by 20 km",
            ),
            glossary={
                "Scale height": "The altitude interval over which density falls by a factor of e. About 8.5 km on Earth.",
                "Lapse rate": "How fast temperature falls with altitude. 6.5 K/km in the troposphere.",
                "Tropopause": "The top of the troposphere, about 11 km, where the temperature fall stops.",
            },
            object_ids=["earth", "mars", "venus", "titan"],
            experiment_ids=["weather-sensitivity"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="wind-and-shear",
            title="Wind, shear and angle of attack",
            strand="Atmospheric flight",
            level="advanced",
            summary=(
                "Weather at the pad is only half the problem. The wind that breaks "
                "vehicles is the one at 11 km."
            ),
            outcomes=[
                "Explain how a wind profile varies with altitude",
                "Relate wind to angle of attack and lateral load",
                "Explain why launches are scrubbed on clear days",
            ],
            prerequisites=["dynamic-pressure", "atmosphere-structure"],
            sections=[
                TopicSection(
                    heading="Wind is not one number",
                    body=(
                        "The surface report gives wind at 10 m. Above that, speed climbs with a "
                        "power law through the surface layer, keeps rising toward a jet-stream "
                        "maximum near the tropopause, and dies away above 25 km. Direction veers "
                        "with height as well — clockwise in the northern hemisphere, by up to "
                        "about 30°.\n\n"
                        "A calm morning at the pad can sit under a 60 m/s jet at 11 km. That is "
                        "exactly the altitude band where max-Q occurs."
                    ),
                    equation="v(h) = v₁₀·(h/10)^α,   α ≈ 0.143 over open terrain",
                ),
                TopicSection(
                    heading="Wind becomes angle of attack",
                    body=(
                        "Aerodynamics act on the velocity relative to the *air*, not to the "
                        "ground. Crosswind tilts that relative velocity away from the vehicle's "
                        "axis, and that angle is the angle of attack.\n\n"
                        "A rocket is a long thin tube with almost no lift and very little "
                        "tolerance for side loading. Multiply angle of attack by dynamic "
                        "pressure and you get the bending moment. This is what a launch weather "
                        "officer is really evaluating, and it is why a balloon sounding is flown "
                        "and the trajectory reflown against the measured profile before commit."
                    ),
                    worked_example=(
                        "At 5 km with 34.7 m/s of wind and 300 m/s of vertical velocity, the "
                        "relative wind tilts about 6.6° off axis. At q = 33.6 kPa that gives "
                        "q·α ≈ 222,000 Pa·deg — approaching the limit a medium vehicle is "
                        "designed to."
                    ),
                ),
                TopicSection(
                    heading="Where it shows up in your flight",
                    body=(
                        "This simulator builds a full wind profile from the live surface "
                        "observation at your selected launch site and resolves it into airspeed "
                        "and angle of attack at every step. You will see it as lateral "
                        "deviation from the intended ground track, as an elevated q·α reading, "
                        "and — if it is bad enough — as an environmental failure with the "
                        "measured value against the limit."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="wind-profile",
                title="Wind against altitude",
                instruction="Set the surface wind and watch what it becomes at max-Q altitude.",
                parameters=[
                    _param("surface_wind_ms", "Surface wind at 10 m", 0, 30, 8,
                           unit="m/s", precision=1),
                    _param("surface_direction_deg", "Direction from", 0, 360, 270,
                           unit="°", precision=0),
                    _param("latitude_deg", "Launch latitude", -60, 60, 28.6, unit="°", precision=1),
                    _param("vehicle_velocity_ms", "Vehicle velocity", 50, 1000, 300,
                           unit="m/s", precision=0),
                ],
                outputs=["wind_at_altitude", "veer", "angle_of_attack", "q_alpha", "verdict"],
                equation="α = angle between the relative wind and the vehicle axis",
            ),
            glossary={
                "Wind shear": "Change of wind speed or direction with height. The dangerous kind is sharp.",
                "Veer": "Clockwise rotation of wind direction with height, from the Ekman spiral.",
                "Angle of attack (α)": "The angle between where the vehicle points and where the air comes from.",
            },
            experiment_ids=["crosswind-sweep"],
            explains_failures=["excessive_q_alpha", "trajectory_deviation"],
            estimated_minutes=9,
            sources=[BUNDLED],
        ),
    ]


# ──────────────────────────────────────────────────────────────
# Strand 5 — Mission engineering
# ──────────────────────────────────────────────────────────────


def _engineering() -> List[ScienceTopic]:
    return [
        ScienceTopic(
            slug="stability-margin",
            title="Stability",
            strand="Mission engineering",
            level="foundation",
            summary=(
                "Two points on the vehicle decide whether it flies straight or tumbles. "
                "Their order matters more than their positions."
            ),
            outcomes=[
                "Explain the relationship between centre of gravity and centre of pressure",
                "Calculate static margin in calibers",
                "Say why fins go at the back",
            ],
            sections=[
                TopicSection(
                    heading="Two centres",
                    body=(
                        "The centre of gravity is where the vehicle's mass balances. The centre "
                        "of pressure is where the aerodynamic forces effectively act. A vehicle "
                        "rotates about its CG, so if the CP is *behind* the CG, any disturbance "
                        "produces a restoring moment that pushes the nose back into the wind.\n\n"
                        "If the CP is ahead of the CG the same disturbance is amplified. The "
                        "vehicle tumbles, and it does so within a second or two."
                    ),
                    equation="static margin = (x_CP − x_CG) / d,  measured in calibers",
                ),
                TopicSection(
                    heading="Why an arrow works and a dart thrown backwards does not",
                    body=(
                        "An arrow has its mass concentrated at the front, in the head, and its "
                        "aerodynamic surface at the back, in the fletching. CG forward, CP aft, "
                        "and it flies straight.\n\n"
                        "That is the whole reason fins exist. They add area at the tail, moving "
                        "the CP backwards without adding much mass there. Bigger fins mean more "
                        "stability — and more drag, and more mass at exactly the end where you "
                        "least want it."
                    ),
                    worked_example=(
                        "A 1.5 m diameter vehicle with CG at 8.2 m from the nose and CP at "
                        "10.1 m:\n"
                        "  margin = (10.1 − 8.2) / 1.5 = 1.27 calibers — inside the usual "
                        "1–2 target."
                    ),
                ),
                TopicSection(
                    heading="More is not better",
                    body=(
                        "Below about 1 caliber a vehicle is marginally stable and is easily "
                        "upset by a gust. Above about 2 it becomes *over*-stable: it weathercocks "
                        "hard into the wind, which on a windy day means it turns into the wind "
                        "and flies there instead of where it was aimed.\n\n"
                        "It also changes in flight. Propellant burns off, usually from tanks "
                        "ahead of the engine, so the CG moves aft as the flight goes on and the "
                        "margin shrinks. A design stable when full can be unstable when nearly "
                        "empty, which is why this platform reports both wet and dry margins."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="stability-margin",
                title="Move the two centres",
                instruction="Drag the CG and CP and watch the vehicle become stable, marginal, or a tumbling wreck.",
                parameters=[
                    _param("cg_position_m", "Centre of gravity", 0.5, 20, 8.2,
                           unit="m from nose", precision=2),
                    _param("cp_position_m", "Centre of pressure", 0.5, 20, 10.1,
                           unit="m from nose", precision=2),
                    _param("diameter_m", "Body diameter", 0.05, 6, 1.5, unit="m", precision=2),
                ],
                outputs=["static_margin", "verdict", "restoring_moment", "recommendation"],
                equation="margin = (x_CP − x_CG)/d",
                equation_note="One caliber is one body diameter. The unit makes margins comparable across vehicle sizes.",
            ),
            glossary={
                "Caliber": "One body diameter. The unit static margin is measured in.",
                "Weathercocking": "Turning into the wind. Desirable in small amounts, a trajectory error in large ones.",
                "Barrowman equations": "The standard method for estimating CP from component geometry.",
            },
            experiment_ids=["fin-size-sweep"],
            explains_failures=["unstable_flight", "loss_of_control"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="guidance-navigation-control",
            title="Guidance, navigation and control",
            strand="Mission engineering",
            level="intermediate",
            summary=(
                "Three different questions that are constantly confused: where am I, "
                "where should I go, and how do I make the vehicle do it."
            ),
            outcomes=[
                "Distinguish guidance, navigation and control",
                "Explain a gravity turn and why it is used",
                "Describe how thrust vectoring steers a rocket",
            ],
            prerequisites=["orbital-mechanics"],
            sections=[
                TopicSection(
                    heading="Three jobs",
                    body=(
                        "**Navigation** answers where the vehicle is and how fast — from "
                        "inertial measurement units, GPS, star trackers, ground radar.\n\n"
                        "**Guidance** decides where it should go next, and computes the "
                        "trajectory to get there.\n\n"
                        "**Control** actuates: gimbal the engine, deflect a fin, fire a "
                        "thruster, and hold the commanded attitude against everything trying to "
                        "disturb it.\n\n"
                        "Confusing them is the most common conceptual error in the field. A "
                        "vehicle can know exactly where it is and still have no idea where to go."
                    ),
                ),
                TopicSection(
                    heading="The gravity turn",
                    body=(
                        "Rather than steering continuously — which wastes thrust on turning "
                        "rather than accelerating — a launch vehicle pitches over slightly early "
                        "in flight and then lets gravity do the rest. Once the vehicle is at a "
                        "small angle, gravity pulls the velocity vector down toward horizontal "
                        "on its own, and the vehicle simply flies along it at zero angle of "
                        "attack.\n\n"
                        "That is the elegance: minimum steering loss and minimum aerodynamic "
                        "load, from one small initial input. It is also unforgiving — pitch over "
                        "too early and the vehicle never gets high enough, too late and it "
                        "wastes delta-v climbing."
                    ),
                ),
                TopicSection(
                    heading="Steering by vectoring",
                    body=(
                        "Fins only work in atmosphere, and only while the vehicle is moving fast "
                        "enough for them to bite. Above that, steering means moving the thrust "
                        "line: gimballing the engine a few degrees puts the thrust vector off "
                        "the centre of gravity and produces a torque.\n\n"
                        "A few degrees is enough. The Saturn V's F-1 engines gimballed ±5.15°, "
                        "and that was sufficient to steer three thousand tonnes."
                    ),
                ),
            ],
            glossary={
                "IMU": "Inertial measurement unit. Accelerometers and gyroscopes; drifts over time and needs correcting.",
                "Thrust vector control": "Steering by gimballing the engine or deflecting the exhaust.",
                "Gravity turn": "A trajectory where gravity does the pitching, so the vehicle flies at zero angle of attack.",
            },
            explains_failures=["guidance_failure", "loss_of_control", "trajectory_deviation"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="recovery",
            title="Recovery",
            strand="Mission engineering",
            level="intermediate",
            summary=(
                "Getting down is a separate problem from getting up, and it has its own "
                "ways of going wrong."
            ),
            outcomes=[
                "Explain two-stage parachute recovery",
                "Calculate terminal velocity under a parachute",
                "Say why a main chute deploys late rather than early",
            ],
            prerequisites=["atmospheric-drag"],
            sections=[
                TopicSection(
                    heading="Two chutes, two jobs",
                    body=(
                        "A small drogue deploys at or shortly after apogee. Its job is not to "
                        "slow the vehicle much — it is to stabilise the descent and keep the "
                        "vehicle from tumbling, while letting it fall fast through thin air "
                        "where wind drift would otherwise carry it a long way.\n\n"
                        "The main deploys low, typically 300–500 m. Deploying it at apogee would "
                        "mean a long, slow descent and kilometres of drift, and in denser air "
                        "at higher speed the opening shock can destroy both the canopy and the "
                        "vehicle."
                    ),
                    equation="v_terminal = √(2·m·g / (ρ·C_d·A))",
                    worked_example=(
                        "A 25 kg vehicle under a 3 m² canopy with C_d = 1.5, at sea level:\n"
                        "  v = √(2 × 25 × 9.807 / (1.225 × 1.5 × 3)) = 10.4 m/s\n"
                        "Survivable for most hardware; roughly a two-metre drop."
                    ),
                ),
                TopicSection(
                    heading="Opening shock",
                    body=(
                        "The load when a canopy inflates can be several times the vehicle's "
                        "weight, and it arrives in a fraction of a second. Reefing — opening the "
                        "canopy partially first, then fully — spreads it out. Apollo's mains "
                        "were reefed in two stages for exactly this reason.\n\n"
                        "A parachute that opens at the wrong speed does not save the vehicle; it "
                        "tears off, or tears the vehicle apart. This simulator checks deployment "
                        "speed against the canopy's rated limit and reports it as a recovery "
                        "failure when it is exceeded."
                    ),
                ),
                TopicSection(
                    heading="Propulsive landing",
                    body=(
                        "Landing on the engine avoids parachutes entirely and gives precision "
                        "measured in metres, at the cost of reserving propellant that could have "
                        "been payload — and of requiring the engine to relight, deep-throttle "
                        "and hold the vehicle in a hover-slam it cannot abort from.\n\n"
                        "The Falcon 9 booster does this routinely now. It took a long sequence "
                        "of public failures to get there, each of which produced a fix."
                    ),
                ),
            ],
            interactive=InteractiveSpec(
                kind="parachute-descent",
                title="Size a parachute",
                instruction="Find the canopy area that brings the vehicle down at a survivable speed.",
                parameters=[
                    _param("mass_kg", "Descent mass", 0.5, 5000, 25, unit="kg",
                           logarithmic=True, precision=1),
                    _param("canopy_area_m2", "Canopy area", 0.1, 200, 3.0, unit="m²",
                           logarithmic=True, precision=2),
                    _param("drag_coefficient", "Canopy C_d", 0.7, 2.2, 1.5, precision=2),
                    _param("deploy_altitude_m", "Deployment altitude", 50, 5000, 400,
                           unit="m", precision=0),
                ],
                outputs=["terminal_velocity", "descent_time", "opening_shock", "verdict"],
                equation="v_t = √(2mg / (ρ·C_d·A))",
            ),
            glossary={
                "Drogue": "A small stabilising chute deployed high. Controls descent, does not slow it much.",
                "Reefing": "Opening a canopy in stages, to limit the shock load.",
                "Terminal velocity": "The speed at which drag equals weight, so descent stops accelerating.",
            },
            experiment_ids=["parachute-sizing"],
            explains_failures=["recovery_failure", "parachute_deployment_failure", "hard_landing"],
            estimated_minutes=8,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="failure-analysis",
            title="Reading a failure",
            strand="Mission engineering",
            level="intermediate",
            summary=(
                "The most valuable output of a flight is usually the reason it did not "
                "work. Here is how to read one."
            ),
            outcomes=[
                "Trace a failure from symptom to root cause",
                "Distinguish proximate from root causes",
                "Use telemetry to test a hypothesis rather than to confirm one",
            ],
            sections=[
                TopicSection(
                    heading="Proximate is not root",
                    body=(
                        "'The vehicle broke up' is a symptom. 'Dynamic pressure exceeded the "
                        "structural limit' is a proximate cause. 'The trajectory was too shallow "
                        "because thrust-to-weight was higher than the profile assumed' is closer "
                        "to a root cause — and only the last one tells you what to change.\n\n"
                        "Every failure this simulator reports carries the measured value, the "
                        "threshold it crossed, the moment it happened, and what contributed. "
                        "That is deliberate: a verdict without evidence teaches nothing."
                    ),
                ),
                TopicSection(
                    heading="Look before the alarm",
                    body=(
                        "Failures announce themselves late. The interesting part of the "
                        "telemetry is the twenty seconds *before* the event, where the drift "
                        "that led to it is visible.\n\n"
                        "Challenger is the canonical case. The proximate cause was an O-ring "
                        "seal failing in cold weather. The root cause, as the Rogers Commission "
                        "found, was an organisation that had been observing seal erosion for "
                        "years and had come to treat it as normal because it had not yet caused "
                        "a loss."
                    ),
                ),
                TopicSection(
                    heading="Change one thing",
                    body=(
                        "Once you have a hypothesis, test it by changing exactly one variable "
                        "and re-flying. If the failure moves as predicted, you understood it. If "
                        "it does not, you did not — and that is more useful than a fix that "
                        "happened to work.\n\n"
                        "The comparison view exists for this. Two runs, side by side, with every "
                        "difference listed."
                    ),
                ),
            ],
            glossary={
                "Proximate cause": "The immediate physical event that ended the mission.",
                "Root cause": "The design or process decision that made the proximate cause possible.",
                "Normalisation of deviance": "Treating a recurring anomaly as acceptable because it has not yet caused a loss.",
            },
            object_ids=[],
            experiment_ids=["failure-diagnosis"],
            estimated_minutes=7,
            image=image_for("apollo13"),
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="payload",
            title="Payload",
            strand="Mission engineering",
            level="foundation",
            summary=(
                "The only part of the vehicle that is the point. Everything else exists "
                "to deliver it."
            ),
            outcomes=[
                "Explain how payload mass trades against performance",
                "Describe what a payload fairing does",
                "Explain why payload mass depends on the target orbit",
            ],
            prerequisites=["tsiolkovsky"],
            sections=[
                TopicSection(
                    heading="Payload is the residual",
                    body=(
                        "Payload capacity is not designed in; it is what remains after the "
                        "rocket equation has taken its share. Add a kilogram of payload and it "
                        "sits in the denominator for the entire flight, so it costs "
                        "proportionally more delta-v than a kilogram of propellant returns.\n\n"
                        "This is why quoted payload figures always name an orbit. A Falcon 9 "
                        "lifts 22.8 t to low Earth orbit but only 8.3 t to geostationary "
                        "transfer — the same vehicle, a different destination, a third of the "
                        "capacity."
                    ),
                ),
                TopicSection(
                    heading="The fairing",
                    body=(
                        "The nose cone protecting the payload through the atmosphere is "
                        "typically the widest part of the vehicle, so it drives the drag "
                        "coefficient and the reference area. It is jettisoned as soon as "
                        "aerodynamic heating drops enough to allow it, usually around 3 minutes "
                        "and 110 km, because after that it is pure dead mass.\n\n"
                        "A fairing that fails to separate is a mission loss. It has happened "
                        "repeatedly, and it is a single-shot mechanism that cannot be tested in "
                        "flight conditions before the flight."
                    ),
                ),
                TopicSection(
                    heading="Where the mass sits",
                    body=(
                        "Payload is at the top, far from the centre of gravity, so it has "
                        "leverage over the CG position out of proportion to its mass. A heavy "
                        "payload pulls the CG forward, which usually *increases* stability "
                        "margin — occasionally past the point of being over-stable.\n\n"
                        "The builder recalculates this as you change payload mass, which is the "
                        "quickest way to see the effect."
                    ),
                ),
            ],
            glossary={
                "Payload fairing": "The aerodynamic shroud protecting the payload during ascent.",
                "Payload adapter": "The structure mating payload to upper stage. Its mass counts against payload.",
                "GTO": "Geostationary transfer orbit. A common quoted target, and much more expensive than LEO.",
            },
            experiment_ids=["payload-mass-sweep"],
            explains_failures=["fairing_separation_failure", "insufficient_delta_v"],
            estimated_minutes=6,
            sources=[BUNDLED],
        ),

        ScienceTopic(
            slug="telemetry",
            title="Telemetry",
            strand="Mission engineering",
            level="foundation",
            summary=(
                "A vehicle you cannot measure is a vehicle you cannot learn from. What "
                "gets sent down, and why."
            ),
            outcomes=[
                "Identify the core telemetry channels of a launch",
                "Explain why sample rate matters near events",
                "Explain what makes a run reproducible",
            ],
            sections=[
                TopicSection(
                    heading="What comes down",
                    body=(
                        "Position, velocity, acceleration, attitude, mass, thrust, chamber "
                        "pressure, tank pressures, temperatures, and the state of every valve "
                        "and pyrotechnic. Hundreds of channels on a real vehicle, sampled from a "
                        "few hertz to a few kilohertz.\n\n"
                        "This simulator records the channels that matter for understanding the "
                        "flight: altitude, downrange, speed, airspeed, acceleration, g-load, "
                        "mass, propellant, thrust, drag, dynamic pressure, Mach, air density, "
                        "attitude, angle of attack, q·α, lateral deviation, wind, and the full "
                        "orbital element set once above the atmosphere."
                    ),
                ),
                TopicSection(
                    heading="Sample where it matters",
                    body=(
                        "A uniform sample rate wastes bandwidth on the boring parts and misses "
                        "the interesting ones. Events — staging, ignition, max-Q, failures — "
                        "happen fast, and a 1 Hz record can step straight over one.\n\n"
                        "This engine samples on a fixed interval *and* forces a sample at every "
                        "event and every state change, so nothing significant falls between two "
                        "samples."
                    ),
                ),
                TopicSection(
                    heading="Reproducibility",
                    body=(
                        "A result you cannot reproduce is an anecdote. Every run here records "
                        "the engine version, the integrator and timestep, the full vehicle "
                        "definition, the launch site, and the exact weather used — so the same "
                        "project file re-flown gives the same numbers, and a comparison between "
                        "two runs is a comparison of the thing you changed rather than of "
                        "conditions that drifted."
                    ),
                ),
            ],
            glossary={
                "Channel": "One measured quantity over time.",
                "Sample rate": "How often a channel is recorded. Too low and events are missed entirely.",
                "Decimation": "Thinning a record for transmission or display, keeping the shape.",
            },
            estimated_minutes=5,
            sources=[BUNDLED],
        ),
    ]


#: Every slug, for cross-reference validation.
SCIENCE_SLUGS = [
    "scale-of-the-universe", "gravity", "light", "celestial-bodies",
    "orbital-mechanics", "orbit-geometry", "delta-v-budget", "hohmann-transfer",
    "gravity-assist", "orbital-decay",
    "thrust", "specific-impulse", "tsiolkovsky", "staging", "thrust-to-weight",
    "propellants",
    "atmospheric-drag", "dynamic-pressure", "atmosphere-structure", "wind-and-shear",
    "stability-margin", "guidance-navigation-control", "recovery", "failure-analysis",
    "payload", "telemetry",
]


def science_topics_by_slug() -> Dict[str, ScienceTopic]:
    return {topic.slug: topic for topic in build_science_topics()}
