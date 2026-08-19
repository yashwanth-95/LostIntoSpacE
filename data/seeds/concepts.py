"""Curated engineering and physics concepts.

Editorial content, written for this project. It is tagged
`SourceType.EDITORIAL` so it can never be mistaken for archive data, and it
cites external references rather than asserting novel results.

These exist because the retrieval layer needs something to answer conceptual
questions with. "What causes Max-Q?" is a real user question with no answer in
any orbital database, and an AI layer with nothing to retrieve would have to
invent one — which is exactly what the project's grounding rule forbids.
"""

from datetime import datetime, timezone
from typing import List

from contracts.provenance import SourceReference, SourceType

from ..models.learning import ContentKind, DifficultyLevel, Equation, LearningContent

__all__ = ["EDITORIAL_SOURCE", "build_concepts", "CONCEPT_SLUGS"]

#: Provenance for everything in this module.
EDITORIAL_SOURCE = SourceReference(
    source_name="lostintospace_editorial",
    source_type=SourceType.EDITORIAL,
    retrieved_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    attribution="LostIntoSpacE educational content",
    license="Project content",
)


def _content(**kwargs) -> LearningContent:
    kwargs.setdefault("source_references", [EDITORIAL_SOURCE])
    kwargs.setdefault("retrieved_at", EDITORIAL_SOURCE.retrieved_at)
    kwargs.setdefault("valid_at", EDITORIAL_SOURCE.retrieved_at)
    slug = kwargs["slug"]
    kwargs.setdefault("canonical_id", "concept:{0}".format(slug))
    return LearningContent(**kwargs)


def build_concepts() -> List[LearningContent]:
    """The curated concept set."""
    return [
        _content(
            slug="max-q",
            name="Max-Q (maximum dynamic pressure)",
            aliases=["Max Q", "MaxQ", "maximum dynamic pressure"],
            keywords=["dynamic pressure", "aerodynamic load", "throttle down",
                      "ascent", "q", "buffeting"],
            kind=ContentKind.CONCEPT,
            category="aerodynamics",
            topics=["launch", "structures", "aerodynamics", "ascent"],
            difficulty=DifficultyLevel.INTRODUCTORY,
            summary=(
                "Max-Q is the point during ascent where the aerodynamic pressure on "
                "a launch vehicle peaks. It happens because speed rises while air "
                "density falls, and the product of the two has a maximum."
            ),
            body=(
                "Dynamic pressure is q = 0.5 * rho * v^2, where rho is the density "
                "of the surrounding air and v is the vehicle's speed through it.\n\n"
                "Early in flight the rocket is slow but the air is thick. Later it is "
                "fast but the air is thin. Because rho falls roughly exponentially "
                "with altitude while v^2 grows, their product rises, peaks, and then "
                "falls. That peak is Max-Q.\n\n"
                "It matters because dynamic pressure drives the aerodynamic loads the "
                "airframe must survive, and those loads combine with steering forces "
                "to produce the highest bending moments of the flight. Many vehicles "
                "throttle their engines down through this region to keep the loads "
                "within structural limits, then throttle back up once past it.\n\n"
                "For a typical orbital launch vehicle Max-Q occurs roughly a minute "
                "into flight, somewhere in the region of 10-15 km altitude, though "
                "the exact value depends on the vehicle's thrust-to-weight ratio and "
                "its trajectory."
            ),
            equations=[
                Equation(
                    name="Dynamic pressure",
                    expression="q = 0.5 * rho * v^2",
                    symbols={
                        "q": "dynamic pressure (Pa)",
                        "rho": "atmospheric density (kg/m^3)",
                        "v": "speed relative to the air (m/s)",
                    },
                    notes="Peaks when the rate of density loss balances the rate of "
                    "speed gain.",
                )
            ],
        ),
        _content(
            slug="staging",
            name="Rocket staging",
            aliases=["multistage rocket", "stage separation", "staging"],
            keywords=["mass ratio", "delta-v", "jettison", "serial staging",
                      "parallel staging", "dead weight", "tank"],
            kind=ContentKind.CONCEPT,
            category="propulsion",
            topics=["propulsion", "launch", "vehicle design"],
            difficulty=DifficultyLevel.INTRODUCTORY,
            summary=(
                "Staging improves rocket performance by throwing away structure that "
                "has stopped being useful, so the remaining engines no longer have to "
                "accelerate empty tanks."
            ),
            body=(
                "The rocket equation says delta-v = Isp * g0 * ln(m_initial / "
                "m_final). The gain comes from the *ratio* of masses, and it is "
                "logarithmic — so improving it gets progressively harder.\n\n"
                "A single-stage vehicle must carry its entire structure, including "
                "tanks that are empty by the end of the burn, all the way to orbit. "
                "Those empty tanks sit in m_final and cap the achievable mass ratio.\n\n"
                "Staging fixes this by discarding spent structure mid-flight. Each "
                "stage gets its own favourable mass ratio, and the total delta-v is "
                "the sum of the stages' contributions. A second benefit is engine "
                "matching: a first stage can use nozzles optimised for sea level "
                "while an upper stage uses large vacuum-optimised nozzles that would "
                "be unusable lower down.\n\n"
                "The costs are added complexity and new failure modes — every "
                "separation event is a mechanism that must work exactly once, and "
                "staging failures are a recurring cause of launch loss."
            ),
            equations=[
                Equation(
                    name="Tsiolkovsky rocket equation",
                    expression="delta_v = Isp * g0 * ln(m_initial / m_final)",
                    symbols={
                        "delta_v": "velocity change achievable (m/s)",
                        "Isp": "specific impulse (s)",
                        "g0": "standard gravity, 9.80665 m/s^2",
                        "m_initial": "mass before the burn (kg)",
                        "m_final": "mass after the burn (kg)",
                    },
                )
            ],
            prerequisites=["concept:specific-impulse"],
        ),
        _content(
            slug="specific-impulse",
            name="Specific impulse",
            aliases=["Isp", "specific impulse"],
            keywords=["efficiency", "exhaust velocity", "propellant", "thrust"],
            kind=ContentKind.DEFINITION,
            category="propulsion",
            topics=["propulsion", "engines"],
            difficulty=DifficultyLevel.INTRODUCTORY,
            summary=(
                "Specific impulse measures how much thrust an engine produces per "
                "unit of propellant consumed per second — effectively, propellant "
                "efficiency."
            ),
            body=(
                "Specific impulse in seconds is Isp = v_e / g0, where v_e is the "
                "effective exhaust velocity. A higher Isp means more velocity change "
                "for the same propellant mass.\n\n"
                "Typical values: solid boosters around 250 s at sea level, kerosene "
                "and liquid oxygen around 300-340 s, hydrogen and liquid oxygen "
                "around 450 s in vacuum, and ion thrusters several thousand seconds "
                "at very low thrust.\n\n"
                "Isp alone does not determine a good engine. An ion thruster's "
                "enormous Isp is useless for a launch, because it cannot produce "
                "enough thrust to lift its own weight."
            ),
            equations=[
                Equation(
                    name="Specific impulse",
                    expression="Isp = v_e / g0",
                    symbols={
                        "Isp": "specific impulse (s)",
                        "v_e": "effective exhaust velocity (m/s)",
                        "g0": "standard gravity, 9.80665 m/s^2",
                    },
                )
            ],
        ),
        _content(
            slug="liquid-propulsion",
            name="Liquid propulsion",
            aliases=["liquid rocket engine", "liquid propellant", "liquid engine"],
            keywords=["turbopump", "combustion chamber", "cryogenic", "hypergolic",
                      "regenerative cooling", "throttle", "restart", "LOX",
                      "kerosene", "methane", "hydrogen"],
            kind=ContentKind.CONCEPT,
            category="propulsion",
            topics=["propulsion", "engines", "vehicle design"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "Liquid rocket engines pump liquid fuel and oxidiser into a "
                "combustion chamber. Unlike solids, they can be throttled, shut "
                "down and often restarted."
            ),
            body=(
                "A liquid engine stores fuel and oxidiser separately as liquids, then "
                "feeds them into a combustion chamber where they burn and accelerate "
                "out through a nozzle.\n\n"
                "Common propellant combinations are liquid oxygen with kerosene (dense "
                "and well understood), liquid oxygen with liquid hydrogen (highest "
                "Isp, but hydrogen is bulky and cryogenic), liquid oxygen with "
                "methane (a compromise, and easier to reuse), and hypergolic pairs "
                "that ignite on contact and so need no ignition system.\n\n"
                "Feeding the chamber is the hard part. Pressure-fed designs are "
                "simple but need heavy tanks. Pump-fed designs use turbopumps driven "
                "by a gas generator, a staged-combustion cycle, or an expander cycle; "
                "these are more efficient and far more complex.\n\n"
                "Chamber walls are usually cooled regeneratively, by running "
                "propellant through channels in the wall before it is burned. The "
                "advantages over solid motors are control — throttling, shutdown, "
                "restart — at the cost of plumbing, turbomachinery and many more "
                "things that can fail."
            ),
        ),
        _content(
            slug="orbital-mechanics",
            name="Orbital mechanics",
            aliases=["astrodynamics", "orbital dynamics", "celestial mechanics"],
            keywords=["Kepler", "two-body problem", "orbital elements", "apoapsis",
                      "periapsis", "transfer orbit", "Hohmann", "inclination",
                      "eccentricity", "semi-major axis"],
            kind=ContentKind.LESSON,
            category="orbital mechanics",
            topics=["orbital mechanics", "trajectory", "mission design"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "Orbital mechanics describes how objects move under gravity. Most "
                "practical work starts from the two-body problem, whose solutions are "
                "conic sections described by six orbital elements."
            ),
            body=(
                "In the two-body problem a small object orbits a much larger one, and "
                "the path is a conic section: an ellipse when the orbit is bound, a "
                "parabola or hyperbola when it is not.\n\n"
                "Six elements pin down an orbit: semi-major axis (size), eccentricity "
                "(shape), inclination (tilt), longitude of the ascending node "
                "(rotation of the orbital plane), argument of periapsis (orientation "
                "within the plane), and a time reference such as mean anomaly at "
                "epoch (where the object is along the path).\n\n"
                "Two consequences drive mission design. First, orbital energy depends "
                "only on the semi-major axis, so raising an orbit costs energy "
                "regardless of how the manoeuvre is arranged. Second, a burn changes "
                "the orbit most efficiently where the vehicle is moving fastest — at "
                "periapsis — which is why transfer manoeuvres are placed where they "
                "are.\n\n"
                "Real trajectories add perturbations the two-body model omits: "
                "atmospheric drag, the non-spherical gravity field of the central "
                "body, third-body attraction, and radiation pressure."
            ),
            equations=[
                Equation(
                    name="Vis-viva equation",
                    expression="v^2 = mu * (2/r - 1/a)",
                    symbols={
                        "v": "orbital speed (m/s)",
                        "mu": "standard gravitational parameter of the central body "
                        "(m^3/s^2)",
                        "r": "current distance from the centre (m)",
                        "a": "semi-major axis (m)",
                    },
                    notes="Relates speed to position for any conic orbit.",
                )
            ],
        ),
        _content(
            slug="gravity-assist",
            name="Gravity assist",
            aliases=["slingshot", "swing-by", "gravitational slingshot", "flyby"],
            keywords=["planetary flyby", "trajectory", "heliocentric", "momentum "
                      "exchange", "Voyager", "interplanetary"],
            kind=ContentKind.CONCEPT,
            category="orbital mechanics",
            topics=["orbital mechanics", "trajectory", "mission design",
                    "interplanetary"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "A gravity assist changes a spacecraft's speed relative to the Sun by "
                "flying past a planet, trading a tiny amount of the planet's orbital "
                "momentum for a large change in the spacecraft's trajectory."
            ),
            body=(
                "Seen from the planet, a flyby is symmetric: the spacecraft arrives "
                "and departs with the same speed relative to the planet, and only its "
                "direction changes.\n\n"
                "Seen from the Sun, the picture is different. The planet is itself "
                "moving. Because the spacecraft's velocity relative to the planet has "
                "been rotated, adding the planet's orbital velocity back produces a "
                "different heliocentric speed. Pass behind the planet along its orbit "
                "and the spacecraft speeds up; pass in front and it slows down.\n\n"
                "Momentum is conserved: the planet loses exactly as much as the "
                "spacecraft gains. Because the planet is some 10^20 times more "
                "massive, its orbit changes immeasurably.\n\n"
                "The technique made the outer Solar System reachable. Voyager 2 used "
                "Jupiter, Saturn and Uranus in sequence; Cassini used Venus twice, "
                "Earth and Jupiter to reach Saturn. The cost is rigid timing — the "
                "planets must be in the right places, which is why interplanetary "
                "launch windows are so constrained."
            ),
        ),
        _content(
            slug="orbital-decay",
            name="Orbital decay",
            aliases=["orbit decay", "atmospheric drag decay", "deorbit"],
            keywords=["drag", "reboost", "thermosphere", "solar activity",
                      "ballistic coefficient", "re-entry", "LEO", "lifetime"],
            kind=ContentKind.CONCEPT,
            category="orbital mechanics",
            topics=["orbital mechanics", "satellites", "atmosphere"],
            difficulty=DifficultyLevel.INTRODUCTORY,
            summary=(
                "Orbital decay is the gradual shrinking of a low orbit caused mainly "
                "by atmospheric drag, which removes orbital energy until the object "
                "re-enters."
            ),
            body=(
                "The atmosphere does not stop at a boundary; it thins out gradually. "
                "Even at 400 km there is enough gas to exert a small drag force on a "
                "satellite.\n\n"
                "Drag removes energy, which lowers the semi-major axis. Counter-"
                "intuitively, the satellite then speeds up: a lower orbit is a faster "
                "orbit. The process accelerates, because lower altitude means denser "
                "air, which means more drag, which means faster descent — until the "
                "object re-enters.\n\n"
                "The rate depends on the ballistic coefficient (mass divided by drag "
                "area) and on solar activity. During solar maximum the thermosphere "
                "heats and expands, raising the density at a given altitude and "
                "shortening satellite lifetimes noticeably.\n\n"
                "The International Space Station loses altitude continuously and is "
                "periodically reboosted. Objects in orbits above roughly 1000 km "
                "experience negligible drag and will remain for many thousands of "
                "years, which is why that region is a debris concern."
            ),
        ),
        _content(
            slug="hohmann-transfer",
            name="Hohmann transfer",
            aliases=["Hohmann transfer orbit", "two-burn transfer"],
            keywords=["transfer orbit", "delta-v", "burn", "coplanar", "efficient",
                      "orbit raising"],
            kind=ContentKind.CONCEPT,
            category="orbital mechanics",
            topics=["orbital mechanics", "trajectory", "mission design"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "A Hohmann transfer moves between two circular coplanar orbits using "
                "two burns and an elliptical transfer arc. It is the lowest-delta-v "
                "two-impulse transfer for most such cases."
            ),
            body=(
                "The first burn raises apoapsis from the starting circular orbit to "
                "the target radius, putting the spacecraft on an ellipse. The "
                "spacecraft coasts half an orbit. The second burn, at apoapsis, "
                "raises periapsis to circularise at the new altitude.\n\n"
                "It is efficient because both burns happen where they do the most "
                "good, and there is no wasted plane change. The cost is time: the "
                "transfer takes half the period of the transfer ellipse, which for an "
                "Earth-to-Mars trajectory is around 8-9 months.\n\n"
                "When the radius ratio is very large — beyond about 11.94 — a "
                "bi-elliptic transfer using three burns can beat it, at the price of "
                "much longer flight time."
            ),
        ),
        _content(
            slug="delta-v-budget",
            name="Delta-v budget",
            aliases=["delta v budget", "dv budget"],
            keywords=["mission planning", "propellant", "margin", "manoeuvre",
                      "gravity loss", "drag loss"],
            kind=ContentKind.CONCEPT,
            category="mission design",
            topics=["mission design", "propulsion", "trajectory"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "A delta-v budget adds up every velocity change a mission needs, "
                "including the losses that do not appear in an idealised calculation."
            ),
            body=(
                "Reaching low Earth orbit needs about 9.4 km/s of delta-v, even "
                "though orbital velocity there is only about 7.8 km/s. The difference "
                "is losses: gravity losses while thrusting against gravity, "
                "atmospheric drag losses, and steering losses from thrusting off the "
                "velocity vector.\n\n"
                "A budget lists each phase — ascent, orbit insertion, plane changes, "
                "transfers, station-keeping, disposal — and sums them, then adds "
                "margin. Because the rocket equation is exponential in delta-v, a "
                "small underestimate translates into a large propellant shortfall."
            ),
        ),
        _content(
            slug="reentry-heating",
            name="Re-entry heating",
            aliases=["atmospheric entry heating", "aerothermal heating",
                     "entry heating"],
            keywords=["heat shield", "ablative", "shock layer", "thermal protection",
                      "TPS", "peak heating", "entry corridor"],
            kind=ContentKind.CONCEPT,
            category="aerodynamics",
            topics=["re-entry", "aerodynamics", "structures", "thermal"],
            difficulty=DifficultyLevel.INTERMEDIATE,
            summary=(
                "Re-entry heating comes overwhelmingly from compressing the air ahead "
                "of the vehicle, not from friction against its surface."
            ),
            body=(
                "A vehicle entering the atmosphere at orbital speed carries enormous "
                "kinetic energy that has to go somewhere. It goes into the air.\n\n"
                "A strong bow shock forms ahead of the vehicle and compresses the air "
                "violently, raising it to thousands of kelvin. Heat reaches the "
                "vehicle from that shock layer by convection and radiation. Surface "
                "friction is a minor contributor.\n\n"
                "This is why entry vehicles are blunt rather than pointed: a blunt "
                "shape pushes the shock further from the surface, so more of the "
                "energy stays in the air. Thermal protection is either ablative — "
                "material designed to char and carry heat away as it erodes — or "
                "reusable insulation such as ceramic tiles.\n\n"
                "The entry corridor is narrow. Too steep and the deceleration and "
                "heating exceed limits; too shallow and the vehicle skips back out."
            ),
        ),
    ]


#: Slugs of the curated set, for tests and for seeding checks.
CONCEPT_SLUGS = [
    "max-q", "staging", "specific-impulse", "liquid-propulsion",
    "orbital-mechanics", "gravity-assist", "orbital-decay",
    "hohmann-transfer", "delta-v-budget", "reentry-heating",
]
