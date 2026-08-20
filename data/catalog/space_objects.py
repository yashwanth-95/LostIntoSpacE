"""The space-object catalog.

Every number here is a published bulk parameter — NASA's planetary fact sheets
and JPL Solar System Dynamics for the solar system, mission pages for the
spacecraft. Values are given to the precision the reference gives them and no
further; a mean radius quoted to a tenth of a kilometre is a real measurement,
a gravitational acceleration quoted to five decimals would not be.

`appearance` is data too. The colours are the body's actual appearance in
visible light, which is what lets the object field draw Mars as iron oxide and
Titan as orange haze without loading a single texture, and what makes a colour
in the legend mean something.
"""

from typing import Dict, List

from ._helpers import BUNDLED, JPL_SSD, NASA_FACTSHEET, prop, text_prop
from .imagery import image_for
from .models import Appearance, CatalogObject, ObjectKind, RingSystem, SurfaceTexture

__all__ = ["build_space_objects", "space_objects_by_id", "SPACE_OBJECT_IDS"]

#: Catalog id to imagery key, where the two differ. Objects not listed here look
#: up their own id.
_IMAGE_KEYS = {
    "churyumov-gerasimenko": "churyumov",
    "voyager-1": "voyager",
    "voyager-2": "voyager",
    "new-horizons": "new-horizons-craft",
    "parker-solar-probe": "parker",
    "chandrayaan-3": "moon-surface",
}

#: Extra photographs worth showing on an object's detail page.
_GALLERY_KEYS = {
    "mars": ["mars-surface", "perseverance", "curiosity"],
    "luna": ["moon-surface", "apollo11", "earthrise"],
    "earth": ["earthrise", "pale-blue-dot", "aurora", "iss"],
    "saturn": ["saturn-rings", "titan", "enceladus"],
    "jupiter": ["io", "europa", "ganymede", "callisto"],
    "sol": ["parker"],
    "pluto": ["new-horizons-craft"],
    "iss": ["aurora", "earth"],
    "jwst": ["carina", "star-field"],
    "hubble": ["star-field", "galaxy", "nebula"],
    "perseverance": ["mars-surface", "ingenuity"],
    "neptune": ["triton"],
    "uranus": ["voyager"],
}

_FACTS = [NASA_FACTSHEET, JPL_SSD]
_T = SurfaceTexture


def build_space_objects() -> List[CatalogObject]:
    """The full catalog, in the order the explorer presents it."""
    return _with_imagery(_catalog())


def _catalog() -> List[CatalogObject]:
    return [
        # ── The star ────────────────────────────────────────────────
        CatalogObject(
            id="sol",
            name="The Sun",
            designation="Sol",
            kind=ObjectKind.STAR,
            classification="G2V main-sequence star",
            tagline="99.86% of the mass of the solar system, fusing 600 million tonnes of hydrogen a second.",
            overview=(
                "Every orbit in this catalog is an orbit around the Sun, or around something "
                "that orbits the Sun. Its gravity sets the shape of every trajectory a mission "
                "flies, and the energy it radiates sets the thermal environment every spacecraft "
                "has to survive. The visible surface is not a surface at all but the photosphere, "
                "the depth at which the plasma finally becomes transparent to its own light."
            ),
            physical=[
                prop("Mean radius", 695_700, "km", note="109 times Earth's", earth_ratio=109.2),
                prop("Mass", 1.989e30, "kg", note="333,000 Earths", earth_ratio=333_000),
                prop("Surface gravity", 274.0, "m/s²", earth_ratio=27.94),
                prop("Photosphere temperature", 5772, "K"),
                prop("Core temperature", 1.571e7, "K"),
                prop("Luminosity", 3.828e26, "W"),
                prop("Escape velocity", 617.6, "km/s", earth_ratio=55.2),
                prop("Mean density", 1408, "kg/m³"),
                prop("Age", 4.6e9, "years"),
                text_prop("Composition", "Hydrogen 73.5%, helium 24.9%, heavier elements 1.6%", "By mass"),
            ],
            orbital=[
                prop("Rotation period (equator)", 25.4, "days", note="Differential: 34 days at the poles"),
                prop("Galactic orbital period", 2.3e8, "years"),
            ],
            facts=[
                "Light leaving the core takes tens of thousands of years to random-walk out to the photosphere, then eight minutes to reach Earth.",
                "The corona is over a million kelvin — hundreds of times hotter than the surface beneath it, and why that is remains an open problem.",
                "Parker Solar Probe has flown inside the corona, closer than any object built by humans.",
            ],
            mission_ids=["parker-solar-probe"],
            related_ids=["mercury", "earth", "parker-solar-probe"],
            concept_slugs=["gravity", "scale-of-the-universe"],
            appearance=Appearance(
                base_color="#FFCF87",
                accent_color="#FF9A3C",
                radius_km=695_700,
                texture=_T.STELLAR,
                albedo=1.0,
                atmosphere_color="#FFB454",
                atmosphere_strength=0.9,
                emissive=True,
                axial_tilt_deg=7.25,
            ),
            field_x=0.06,
            field_y=0.30,
            field_depth=0.15,
            sources=_FACTS,
        ),

        # ── Terrestrial planets ─────────────────────────────────────
        CatalogObject(
            id="mercury",
            name="Mercury",
            designation="Sol I",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Terrestrial planet",
            tagline="The smallest planet, with an iron core filling 85% of its radius.",
            overview=(
                "Mercury is the hardest inner planet to reach, which is counter-intuitive until "
                "you look at the delta-v: falling toward the Sun means arriving far too fast, so "
                "a mission has to shed enormous orbital energy. MESSENGER took six and a half "
                "years and six planetary flybys to slow down enough to be captured."
            ),
            physical=[
                prop("Mean radius", 2439.7, "km", earth_ratio=0.383),
                prop("Mass", 3.301e23, "kg", earth_ratio=0.0553),
                prop("Surface gravity", 3.70, "m/s²", earth_ratio=0.378),
                prop("Escape velocity", 4.25, "km/s", earth_ratio=0.38),
                prop("Mean density", 5429, "kg/m³", note="Second densest planet, after Earth"),
                text_prop("Surface temperature", "−173 °C to 427 °C", "The largest swing of any planet"),
                prop("Geometric albedo", 0.142),
            ],
            orbital=[
                prop("Mean distance from Sun", 5.79e7, "km", note="0.387 AU"),
                prop("Orbital period", 87.97, "days"),
                prop("Orbital velocity", 47.36, "km/s", note="The fastest planet"),
                prop("Eccentricity", 0.2056, note="The most elliptical planetary orbit"),
                prop("Inclination to ecliptic", 7.005, "°"),
                prop("Sidereal rotation", 58.646, "days"),
                prop("Solar day", 176, "days", note="Two Mercury years to one Mercury day"),
                prop("Axial tilt", 0.034, "°"),
            ],
            atmosphere=[
                text_prop("Atmosphere", "Exosphere only — oxygen, sodium, hydrogen, helium, potassium"),
                prop("Surface pressure", 5e-10, "Pa", note="Effectively vacuum"),
            ],
            facts=[
                "Its 3:2 spin–orbit resonance means it rotates exactly three times for every two orbits.",
                "Radar found water ice in permanently shadowed polar craters, on the planet closest to the Sun.",
            ],
            mission_ids=[],
            related_ids=["sol", "venus", "luna"],
            concept_slugs=["orbital-mechanics", "delta-v-budget"],
            appearance=Appearance(
                base_color="#8C8177",
                accent_color="#B5A99C",
                radius_km=2439.7,
                texture=_T.CRATERED,
                albedo=0.142,
                axial_tilt_deg=0.034,
            ),
            field_x=0.17,
            field_y=0.62,
            field_depth=0.35,
            sources=_FACTS,
        ),

        CatalogObject(
            id="venus",
            name="Venus",
            designation="Sol II",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Terrestrial planet",
            tagline="Ninety-two atmospheres of carbon dioxide at 464 °C — hot enough to melt lead.",
            overview=(
                "Venus is almost exactly Earth's size and mass, and nothing like it. A runaway "
                "greenhouse pushed the surface to 464 °C, uniformly, day and night, pole to "
                "equator. It is the clearest evidence available that planetary habitability is "
                "not a matter of distance from a star alone."
            ),
            physical=[
                prop("Mean radius", 6051.8, "km", earth_ratio=0.949),
                prop("Mass", 4.867e24, "kg", earth_ratio=0.815),
                prop("Surface gravity", 8.87, "m/s²", earth_ratio=0.905),
                prop("Escape velocity", 10.36, "km/s", earth_ratio=0.926),
                prop("Mean density", 5243, "kg/m³"),
                prop("Surface temperature", 464, "°C", note="Hotter than Mercury, despite being further out"),
                prop("Geometric albedo", 0.689, note="The brightest planet in our sky"),
            ],
            orbital=[
                prop("Mean distance from Sun", 1.082e8, "km", note="0.723 AU"),
                prop("Orbital period", 224.70, "days"),
                prop("Orbital velocity", 35.02, "km/s"),
                prop("Eccentricity", 0.0068, note="The most nearly circular planetary orbit"),
                prop("Inclination to ecliptic", 3.395, "°"),
                prop("Sidereal rotation", 243.02, "days", note="Retrograde — the Sun rises in the west"),
                prop("Axial tilt", 177.36, "°"),
            ],
            atmosphere=[
                text_prop("Composition", "CO₂ 96.5%, N₂ 3.5%, traces of SO₂"),
                prop("Surface pressure", 9.2e6, "Pa", note="92 bar — equivalent to 900 m of ocean on Earth", earth_ratio=92),
                text_prop("Cloud deck", "Sulfuric acid, 45–70 km altitude"),
            ],
            facts=[
                "A day on Venus is longer than its year.",
                "Its rotation is retrograde: it spins backwards relative to almost everything else in the solar system.",
                "At around 55 km altitude the pressure and temperature are close to Earth's surface conditions.",
            ],
            related_ids=["earth", "mercury", "mars"],
            concept_slugs=["atmospheric-drag", "reentry-heating"],
            appearance=Appearance(
                base_color="#D8B26B",
                accent_color="#F0DCA8",
                band_colors=["#C99F58", "#DCBB77", "#EBD49A", "#DCBB77", "#C99F58"],
                radius_km=6051.8,
                texture=_T.GASEOUS,
                albedo=0.689,
                atmosphere_color="#F5D89B",
                atmosphere_strength=0.85,
                axial_tilt_deg=177.36,
            ),
            field_x=0.30,
            field_y=0.22,
            field_depth=0.45,
            sources=_FACTS,
        ),

        CatalogObject(
            id="earth",
            name="Earth",
            designation="Sol III",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Terrestrial planet",
            tagline="The reference body: every launch in this simulator starts here.",
            overview=(
                "Earth is where the mission begins, so its numbers are the ones the simulation "
                "uses constantly. Its gravitational parameter sets orbital velocity, its "
                "atmosphere produces the drag and dynamic pressure a launch vehicle has to "
                "survive, and its rotation gives an eastward launch a free 465 m/s at the "
                "equator — a bonus that shrinks with the cosine of latitude."
            ),
            physical=[
                prop("Mean radius", 6371.0, "km", note="Equatorial 6378.1, polar 6356.8"),
                prop("Mass", 5.972e24, "kg"),
                prop("Surface gravity", 9.807, "m/s²"),
                prop("Escape velocity", 11.186, "km/s"),
                prop("Mean density", 5514, "kg/m³", note="The densest planet"),
                prop("Mean surface temperature", 15, "°C"),
                prop("Geometric albedo", 0.434),
                prop("Gravitational parameter μ", 3.986e14, "m³/s²", note="GM — the number orbital mechanics actually uses"),
            ],
            orbital=[
                prop("Mean distance from Sun", 1.496e8, "km", note="1 AU, by definition"),
                prop("Orbital period", 365.256, "days"),
                prop("Orbital velocity", 29.78, "km/s"),
                prop("Eccentricity", 0.0167),
                prop("Sidereal rotation", 23.934, "hours", note="23h 56m 4s"),
                prop("Axial tilt", 23.44, "°", note="The reason there are seasons"),
                prop("Equatorial rotation speed", 465.1, "m/s", note="Free delta-v for an eastward launch"),
            ],
            atmosphere=[
                text_prop("Composition", "N₂ 78.08%, O₂ 20.95%, Ar 0.93%, CO₂ 0.04%"),
                prop("Sea-level pressure", 101_325, "Pa"),
                prop("Sea-level density", 1.225, "kg/m³", note="The value in every drag calculation"),
                prop("Scale height", 8.5, "km", note="Density falls by 1/e over this distance"),
                prop("Kármán line", 100, "km", note="The conventional boundary of space"),
            ],
            facts=[
                "Half the atmosphere's mass sits below 5.6 km — most of the drag a rocket fights is in the first minute of flight.",
                "The Moon is receding by about 3.8 cm a year, measured by laser ranging off retroreflectors left by Apollo.",
            ],
            mission_ids=["iss"],
            related_ids=["luna", "mars", "venus", "iss"],
            concept_slugs=["atmospheric-drag", "orbital-mechanics", "dynamic-pressure"],
            appearance=Appearance(
                base_color="#4E7C8E",
                accent_color="#7B9E6A",
                radius_km=6371.0,
                texture=_T.OCEANIC,
                albedo=0.434,
                atmosphere_color="#7FA8B8",
                atmosphere_strength=0.55,
                axial_tilt_deg=23.44,
            ),
            field_x=0.47,
            field_y=0.68,
            field_depth=0.7,
            sources=_FACTS,
        ),

        CatalogObject(
            id="mars",
            name="Mars",
            designation="Sol IV",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Terrestrial planet",
            tagline="Iron-oxide dust, 0.6% of Earth's surface pressure, and the hardest landings in the solar system.",
            overview=(
                "Mars has just enough atmosphere to matter and not enough to help. It is thick "
                "enough to require a heat shield and to make parachutes worth carrying, and thin "
                "enough that parachutes alone cannot land anything heavy — which is why every "
                "successful large lander has ended its descent under rocket power."
            ),
            physical=[
                prop("Mean radius", 3389.5, "km", earth_ratio=0.532),
                prop("Mass", 6.417e23, "kg", earth_ratio=0.107),
                prop("Surface gravity", 3.721, "m/s²", earth_ratio=0.379),
                prop("Escape velocity", 5.03, "km/s", earth_ratio=0.45),
                prop("Mean density", 3934, "kg/m³"),
                prop("Mean surface temperature", -63, "°C", note="Range −143 °C to 35 °C"),
                prop("Geometric albedo", 0.170),
            ],
            orbital=[
                prop("Mean distance from Sun", 2.279e8, "km", note="1.524 AU"),
                prop("Orbital period", 686.98, "days", note="1.88 Earth years"),
                prop("Orbital velocity", 24.07, "km/s"),
                prop("Eccentricity", 0.0934, note="Large enough that opposition distance varies by a factor of two"),
                prop("Inclination to ecliptic", 1.850, "°"),
                prop("Sidereal rotation", 24.623, "hours", note="A sol is 24h 39m 35s"),
                prop("Axial tilt", 25.19, "°", note="Close to Earth's — Mars has seasons"),
                prop("Synodic period", 779.9, "days", note="The launch window repeats every 26 months"),
            ],
            atmosphere=[
                text_prop("Composition", "CO₂ 95.3%, N₂ 2.7%, Ar 1.6%, O₂ 0.13%"),
                prop("Surface pressure", 610, "Pa", note="0.6% of Earth's", earth_ratio=0.006),
                prop("Surface density", 0.020, "kg/m³", earth_ratio=0.016),
                prop("Scale height", 11.1, "km"),
            ],
            facts=[
                "Olympus Mons rises 21.9 km — about two and a half times the height of Everest above sea level.",
                "Valles Marineris runs over 4,000 km, roughly the width of the continental United States.",
                "Transfer windows open about every 26 months; miss one and the next attempt is over two years away.",
            ],
            mission_ids=["perseverance", "curiosity"],
            related_ids=["phobos", "deimos", "earth", "perseverance"],
            concept_slugs=["hohmann-transfer", "reentry-heating", "delta-v-budget"],
            appearance=Appearance(
                base_color="#B4552F",
                accent_color="#D98A5F",
                band_colors=["#C9BBA8", "#B4552F", "#9E4526", "#B4552F", "#C9BBA8"],
                radius_km=3389.5,
                texture=_T.ROCKY,
                albedo=0.170,
                atmosphere_color="#C88A63",
                atmosphere_strength=0.18,
                axial_tilt_deg=25.19,
            ),
            field_x=0.72,
            field_y=0.34,
            field_depth=0.85,
            sources=_FACTS,
        ),

        # ── Gas and ice giants ──────────────────────────────────────
        CatalogObject(
            id="jupiter",
            name="Jupiter",
            designation="Sol V",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Gas giant",
            tagline="More massive than every other planet combined, twice over.",
            overview=(
                "Jupiter's mass dominates the outer solar system: it shepherds the asteroid belt, "
                "it deflects or captures incoming comets, and its gravity well is the standard "
                "tool for accelerating a spacecraft outward. Voyager, Galileo, Cassini, New "
                "Horizons and Juno all used it, and several could not have reached their targets "
                "without it."
            ),
            physical=[
                prop("Mean radius", 69_911, "km", earth_ratio=10.97),
                prop("Mass", 1.898e27, "kg", earth_ratio=317.8),
                prop("Surface gravity", 24.79, "m/s²", note="At the 1-bar level", earth_ratio=2.53),
                prop("Escape velocity", 59.5, "km/s", earth_ratio=5.32),
                prop("Mean density", 1326, "kg/m³"),
                prop("Cloud-top temperature", -108, "°C"),
                prop("Known moons", 95, note="Confirmed as of 2023"),
            ],
            orbital=[
                prop("Mean distance from Sun", 7.785e8, "km", note="5.204 AU"),
                prop("Orbital period", 11.862, "years"),
                prop("Orbital velocity", 13.06, "km/s"),
                prop("Eccentricity", 0.0489),
                prop("Sidereal rotation", 9.925, "hours", note="The fastest rotation of any planet"),
                prop("Axial tilt", 3.13, "°"),
            ],
            atmosphere=[
                text_prop("Composition", "H₂ 89.8%, He 10.2%, traces of CH₄, NH₃, H₂O"),
                text_prop("Great Red Spot", "A storm wider than Earth, observed for over 190 years"),
            ],
            facts=[
                "Its rapid rotation flattens it visibly: the equatorial radius exceeds the polar radius by about 4,600 km.",
                "The magnetosphere is the largest structure in the solar system after the heliosphere itself.",
            ],
            mission_ids=["juno", "voyager-1", "voyager-2"],
            related_ids=["io", "europa", "ganymede", "callisto"],
            concept_slugs=["gravity-assist", "gravity"],
            appearance=Appearance(
                base_color="#C8956B",
                accent_color="#E8C9A0",
                band_colors=["#A67C52", "#E3C49C", "#B98A5E", "#F0DCC0", "#C8956B", "#9E6F49", "#DBB98E", "#A67C52"],
                radius_km=69_911,
                texture=_T.BANDED,
                albedo=0.538,
                atmosphere_color="#E0B98D",
                atmosphere_strength=0.7,
                axial_tilt_deg=3.13,
            ),
            field_x=0.88,
            field_y=0.72,
            field_depth=0.55,
            sources=_FACTS,
        ),

        CatalogObject(
            id="saturn",
            name="Saturn",
            designation="Sol VI",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Gas giant",
            tagline="Less dense than water, wearing a ring system 280,000 km across and 10 metres thick.",
            overview=(
                "The rings are the headline, and they are stranger than they look: essentially "
                "pure water ice, spanning a quarter of a million kilometres, and in most places "
                "only about ten metres deep. Cassini spent thirteen years there and ended by "
                "flying between the rings and the planet, a gap no spacecraft had entered."
            ),
            physical=[
                prop("Mean radius", 58_232, "km", earth_ratio=9.14),
                prop("Mass", 5.683e26, "kg", earth_ratio=95.16),
                prop("Surface gravity", 10.44, "m/s²", note="At the 1-bar level", earth_ratio=1.065),
                prop("Escape velocity", 35.5, "km/s", earth_ratio=3.17),
                prop("Mean density", 687, "kg/m³", note="Less dense than liquid water"),
                prop("Cloud-top temperature", -139, "°C"),
                prop("Known moons", 146, note="The most of any planet"),
            ],
            orbital=[
                prop("Mean distance from Sun", 1.434e9, "km", note="9.583 AU"),
                prop("Orbital period", 29.457, "years"),
                prop("Orbital velocity", 9.68, "km/s"),
                prop("Eccentricity", 0.0565),
                prop("Sidereal rotation", 10.56, "hours"),
                prop("Axial tilt", 26.73, "°"),
            ],
            atmosphere=[
                text_prop("Composition", "H₂ 96.3%, He 3.25%, traces of CH₄, NH₃"),
                text_prop("Polar hexagon", "A six-sided jet stream around the north pole, ~30,000 km across"),
            ],
            facts=[
                "The rings are over 99% water ice and would fit between Earth and the Moon.",
                "Its magnetic field is almost perfectly aligned with its rotation axis, which theory says should be impossible.",
            ],
            mission_ids=["cassini"],
            related_ids=["titan", "enceladus", "jupiter", "uranus"],
            concept_slugs=["orbital-mechanics", "gravity"],
            appearance=Appearance(
                base_color="#D5BD8B",
                accent_color="#F0E0BC",
                band_colors=["#B9A176", "#E5D2A6", "#D5BD8B", "#F2E4C4", "#C9B183", "#B9A176"],
                radius_km=58_232,
                texture=_T.BANDED,
                albedo=0.499,
                atmosphere_color="#E8D5A8",
                atmosphere_strength=0.6,
                axial_tilt_deg=26.73,
                ring=RingSystem(
                    inner_radius_ratio=1.24,
                    outer_radius_ratio=2.27,
                    color="#CFC1A0",
                    opacity=0.6,
                    tilt_deg=26.73,
                    gaps=[1.95],
                ),
            ),
            field_x=0.62,
            field_y=0.86,
            field_depth=0.4,
            sources=_FACTS,
        ),

        CatalogObject(
            id="uranus",
            name="Uranus",
            designation="Sol VII",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Ice giant",
            tagline="Tipped on its side by 98 degrees, so its poles face the Sun in turn.",
            overview=(
                "Uranus rotates almost in the plane of its orbit, which gives each pole a "
                "forty-two-year day followed by a forty-two-year night. The most likely "
                "explanation is a collision with an Earth-sized body early in its history. "
                "Only one spacecraft has ever visited: Voyager 2, for a few hours in 1986."
            ),
            physical=[
                prop("Mean radius", 25_362, "km", earth_ratio=3.98),
                prop("Mass", 8.681e25, "kg", earth_ratio=14.54),
                prop("Surface gravity", 8.87, "m/s²", earth_ratio=0.905),
                prop("Escape velocity", 21.3, "km/s", earth_ratio=1.90),
                prop("Mean density", 1270, "kg/m³"),
                prop("Cloud-top temperature", -197, "°C", note="The coldest planetary atmosphere measured"),
                prop("Known moons", 28),
            ],
            orbital=[
                prop("Mean distance from Sun", 2.871e9, "km", note="19.19 AU"),
                prop("Orbital period", 84.01, "years"),
                prop("Orbital velocity", 6.80, "km/s"),
                prop("Eccentricity", 0.0457),
                prop("Sidereal rotation", 17.24, "hours", note="Retrograde"),
                prop("Axial tilt", 97.77, "°"),
            ],
            atmosphere=[
                text_prop("Composition", "H₂ 82.5%, He 15.2%, CH₄ 2.3%"),
                text_prop("Colour", "Methane absorbs red light, leaving the pale blue-green"),
            ],
            facts=[
                "It was the first planet discovered with a telescope, by William Herschel in 1781.",
                "Its magnetic field is tilted 59° from its rotation axis and offset from the centre of the planet.",
            ],
            mission_ids=["voyager-2"],
            related_ids=["neptune", "voyager-2"],
            concept_slugs=["orbital-mechanics"],
            appearance=Appearance(
                base_color="#7FA8A6",
                accent_color="#B4D6D2",
                band_colors=["#6F9A98", "#8FB6B4", "#7FA8A6"],
                radius_km=25_362,
                texture=_T.GASEOUS,
                albedo=0.488,
                atmosphere_color="#A8CFCC",
                atmosphere_strength=0.5,
                axial_tilt_deg=97.77,
                ring=RingSystem(
                    inner_radius_ratio=1.60,
                    outer_radius_ratio=2.00,
                    color="#7E8C8C",
                    opacity=0.22,
                    tilt_deg=97.77,
                ),
            ),
            field_x=0.35,
            field_y=0.92,
            field_depth=0.25,
            sources=_FACTS,
        ),

        CatalogObject(
            id="neptune",
            name="Neptune",
            designation="Sol VIII",
            kind=ObjectKind.PLANET,
            parent_id="sol",
            classification="Ice giant",
            tagline="Supersonic winds at 2,100 km/h, on a world receiving 1/900th of Earth's sunlight.",
            overview=(
                "Neptune was found by prediction rather than survey: irregularities in Uranus's "
                "orbit implied an unseen mass, and the planet was located within a degree of "
                "where the calculation said it would be. It radiates more than twice the energy "
                "it receives from the Sun, and nobody is certain where that heat comes from."
            ),
            physical=[
                prop("Mean radius", 24_622, "km", earth_ratio=3.86),
                prop("Mass", 1.024e26, "kg", earth_ratio=17.15),
                prop("Surface gravity", 11.15, "m/s²", earth_ratio=1.14),
                prop("Escape velocity", 23.5, "km/s", earth_ratio=2.10),
                prop("Mean density", 1638, "kg/m³"),
                prop("Cloud-top temperature", -201, "°C"),
                prop("Peak wind speed", 2100, "km/h", note="The fastest winds in the solar system"),
                prop("Known moons", 16),
            ],
            orbital=[
                prop("Mean distance from Sun", 4.495e9, "km", note="30.07 AU"),
                prop("Orbital period", 164.79, "years", note="One Neptune year since its discovery, completed in 2011"),
                prop("Orbital velocity", 5.43, "km/s"),
                prop("Eccentricity", 0.0113),
                prop("Sidereal rotation", 16.11, "hours"),
                prop("Axial tilt", 28.32, "°"),
            ],
            atmosphere=[text_prop("Composition", "H₂ 80%, He 19%, CH₄ 1.5%")],
            facts=[
                "Voyager 2 remains the only spacecraft to have visited, in August 1989.",
                "Its largest moon Triton orbits backwards, which means it was captured rather than formed in place.",
            ],
            mission_ids=["voyager-2"],
            related_ids=["triton", "uranus", "voyager-2"],
            concept_slugs=["orbital-mechanics"],
            appearance=Appearance(
                base_color="#5A7495",
                accent_color="#8FA9C4",
                band_colors=["#4C6584", "#6B85A6", "#5A7495"],
                radius_km=24_622,
                texture=_T.GASEOUS,
                albedo=0.442,
                atmosphere_color="#7E9BBC",
                atmosphere_strength=0.55,
                axial_tilt_deg=28.32,
            ),
            field_x=0.14,
            field_y=0.88,
            field_depth=0.2,
            sources=_FACTS,
        ),
    ] + _dwarf_planets() + _moons() + _small_bodies() + _spacecraft()


def _with_imagery(objects: List[CatalogObject]) -> List[CatalogObject]:
    """Attach verified photography to each object.

    Done here rather than inline in every entry so that adding an image is a
    one-line change to the imagery table, and so an object with no verified
    photograph simply carries `None` and falls through to the procedural
    renderer instead of pointing at a URL that does not exist.
    """
    resolved = []
    for obj in objects:
        primary = image_for(_IMAGE_KEYS.get(obj.id, obj.id))
        gallery = [
            image
            for key in _GALLERY_KEYS.get(obj.id, [])
            for image in [image_for(key)]
            if image is not None and image is not primary
        ]
        resolved.append(obj.model_copy(update={"image": primary, "gallery": gallery}))
    return resolved


def _dwarf_planets() -> List[CatalogObject]:
    return [
        CatalogObject(
            id="pluto",
            name="Pluto",
            designation="134340 Pluto",
            kind=ObjectKind.DWARF_PLANET,
            parent_id="sol",
            classification="Dwarf planet, Kuiper Belt object",
            tagline="Nitrogen glaciers flowing across a heart-shaped basin, 5.9 billion km out.",
            overview=(
                "Before 2015 the best image of Pluto was a handful of pixels. New Horizons "
                "arrived expecting a dead ball of ice and found nitrogen glaciers, water-ice "
                "mountains three kilometres high, and a surface young enough to still be "
                "resurfacing — on a body that should have frozen solid long ago."
            ),
            physical=[
                prop("Mean radius", 1188.3, "km", earth_ratio=0.186),
                prop("Mass", 1.303e22, "kg", earth_ratio=0.0022),
                prop("Surface gravity", 0.62, "m/s²", earth_ratio=0.063),
                prop("Escape velocity", 1.21, "km/s"),
                prop("Mean density", 1854, "kg/m³"),
                prop("Surface temperature", -229, "°C"),
                prop("Known moons", 5, note="Charon, Nix, Hydra, Kerberos, Styx"),
            ],
            orbital=[
                prop("Mean distance from Sun", 5.906e9, "km", note="39.48 AU"),
                prop("Orbital period", 247.94, "years"),
                prop("Orbital velocity", 4.67, "km/s"),
                prop("Eccentricity", 0.2488, note="Crosses inside Neptune's orbit"),
                prop("Inclination to ecliptic", 17.16, "°"),
                prop("Sidereal rotation", 6.387, "days", note="Retrograde"),
                prop("Axial tilt", 122.53, "°"),
            ],
            atmosphere=[
                text_prop("Composition", "N₂ with CH₄ and CO, collapsing as it moves away from the Sun"),
                prop("Surface pressure", 1.0, "Pa", note="About one hundred-thousandth of Earth's"),
            ],
            facts=[
                "Pluto and Charon are tidally locked to each other and orbit a barycentre outside Pluto's surface.",
                "It is in a 3:2 resonance with Neptune, which is why the two never collide despite crossing orbits.",
            ],
            mission_ids=["new-horizons"],
            related_ids=["neptune", "new-horizons", "ceres"],
            concept_slugs=["orbital-mechanics", "scale-of-the-universe"],
            appearance=Appearance(
                base_color="#A08D7C",
                accent_color="#DCCBB4",
                radius_km=1188.3,
                texture=_T.ICY,
                albedo=0.52,
                atmosphere_color="#B8C7CF",
                atmosphere_strength=0.12,
                axial_tilt_deg=122.53,
            ),
            field_depth=0.18,
            sources=_FACTS,
        ),

        CatalogObject(
            id="ceres",
            name="Ceres",
            designation="1 Ceres",
            kind=ObjectKind.DWARF_PLANET,
            parent_id="sol",
            classification="Dwarf planet, asteroid belt",
            tagline="A quarter water ice, and the only dwarf planet in the inner solar system.",
            overview=(
                "Ceres holds about a third of the asteroid belt's total mass and is round enough "
                "for its own gravity to have shaped it. Dawn found bright deposits of sodium "
                "carbonate in Occator Crater — evidence of briny water reaching the surface from "
                "below, recently enough to still be visible."
            ),
            physical=[
                prop("Mean radius", 469.7, "km"),
                prop("Mass", 9.384e20, "kg"),
                prop("Surface gravity", 0.28, "m/s²", earth_ratio=0.029),
                prop("Escape velocity", 0.51, "km/s"),
                prop("Mean density", 2162, "kg/m³"),
                prop("Surface temperature", -105, "°C", note="Maximum"),
            ],
            orbital=[
                prop("Mean distance from Sun", 4.14e8, "km", note="2.77 AU"),
                prop("Orbital period", 4.60, "years"),
                prop("Orbital velocity", 17.9, "km/s"),
                prop("Eccentricity", 0.0785),
                prop("Inclination to ecliptic", 10.59, "°"),
                prop("Sidereal rotation", 9.074, "hours"),
            ],
            facts=[
                "Discovered in 1801 and classified in turn as a planet, an asteroid, and a dwarf planet.",
                "Dawn is the only spacecraft to have orbited two extraterrestrial bodies: Vesta, then Ceres.",
            ],
            related_ids=["psyche", "pluto", "mars"],
            concept_slugs=["orbital-mechanics"],
            appearance=Appearance(
                base_color="#77706A",
                accent_color="#C6BFB4",
                radius_km=469.7,
                texture=_T.CRATERED,
                albedo=0.09,
            ),
            field_depth=0.3,
            sources=_FACTS,
        ),
    ]


def _moons() -> List[CatalogObject]:
    return [
        CatalogObject(
            id="luna",
            name="The Moon",
            designation="Luna",
            kind=ObjectKind.MOON,
            parent_id="earth",
            classification="Natural satellite",
            tagline="Two point four kilometres a second of escape velocity, and no atmosphere to slow you down.",
            overview=(
                "The Moon is the natural first destination in this simulator: reaching it needs "
                "roughly 3.2 km/s beyond low Earth orbit, and landing on it needs another 1.9, "
                "with no atmosphere to help. That absence cuts both ways — nothing to brake "
                "against, but also no drag, no weather, and no heat shield required."
            ),
            physical=[
                prop("Mean radius", 1737.4, "km", earth_ratio=0.273),
                prop("Mass", 7.346e22, "kg", earth_ratio=0.0123),
                prop("Surface gravity", 1.62, "m/s²", earth_ratio=0.165),
                prop("Escape velocity", 2.38, "km/s", earth_ratio=0.21),
                prop("Mean density", 3344, "kg/m³"),
                text_prop("Surface temperature", "−173 °C to 127 °C"),
                prop("Geometric albedo", 0.136, note="About as reflective as worn asphalt"),
            ],
            orbital=[
                prop("Mean distance from Earth", 384_400, "km"),
                prop("Perigee", 363_300, "km"),
                prop("Apogee", 405_500, "km"),
                prop("Orbital period", 27.322, "days", note="Sidereal; 29.53 days synodic"),
                prop("Orbital velocity", 1.022, "km/s"),
                prop("Eccentricity", 0.0549),
                prop("Inclination to ecliptic", 5.145, "°"),
                prop("Recession rate", 3.8, "cm/year"),
            ],
            facts=[
                "It is tidally locked, so the same hemisphere always faces Earth.",
                "Apollo left retroreflectors that are still used to measure the Earth–Moon distance to millimetre precision.",
                "Permanently shadowed polar craters hold water ice, which is why Artemis targets the south pole.",
            ],
            mission_ids=["apollo-11", "apollo-13", "artemis-1", "chandrayaan-3"],
            related_ids=["earth", "chandrayaan-3", "mars"],
            concept_slugs=["delta-v-budget", "gravity", "hohmann-transfer"],
            appearance=Appearance(
                base_color="#B5AFA3",
                accent_color="#DAD4C8",
                radius_km=1737.4,
                texture=_T.CRATERED,
                albedo=0.136,
                axial_tilt_deg=6.68,
            ),
            field_x=0.56,
            field_y=0.55,
            field_depth=0.75,
            sources=_FACTS,
        ),

        CatalogObject(
            id="io",
            name="Io",
            designation="Jupiter I",
            kind=ObjectKind.MOON,
            parent_id="jupiter",
            classification="Natural satellite",
            tagline="The most volcanically active body known — over 400 active volcanoes.",
            overview=(
                "Io is squeezed by Jupiter's tides and by resonances with Europa and Ganymede, "
                "and that flexing melts its interior. The surface is resurfaced fast enough that "
                "impact craters essentially do not survive, which makes it the youngest surface "
                "in the solar system."
            ),
            physical=[
                prop("Mean radius", 1821.6, "km"),
                prop("Mass", 8.932e22, "kg"),
                prop("Surface gravity", 1.796, "m/s²"),
                prop("Escape velocity", 2.558, "km/s"),
                prop("Mean density", 3528, "kg/m³"),
            ],
            orbital=[
                prop("Distance from Jupiter", 421_700, "km"),
                prop("Orbital period", 1.769, "days"),
                prop("Orbital velocity", 17.33, "km/s"),
                prop("Eccentricity", 0.0041),
            ],
            facts=[
                "Volcanic plumes reach 500 km above the surface — far higher than Io's own radius would suggest is possible.",
                "It sits inside Jupiter's radiation belts, where a human would receive a lethal dose within minutes.",
            ],
            mission_ids=["juno", "voyager-1"],
            related_ids=["jupiter", "europa", "ganymede"],
            appearance=Appearance(
                base_color="#D9C066",
                accent_color="#E8543A",
                radius_km=1821.6,
                texture=_T.VOLCANIC,
                albedo=0.63,
            ),
            field_depth=0.35,
            sources=_FACTS,
        ),

        CatalogObject(
            id="europa",
            name="Europa",
            designation="Jupiter II",
            kind=ObjectKind.MOON,
            parent_id="jupiter",
            classification="Natural satellite",
            tagline="A salt-water ocean under 15–25 km of ice, holding more water than all of Earth's.",
            overview=(
                "Europa's surface is the smoothest solid surface in the solar system, cracked by "
                "long reddish linea where the ice shell has shifted. Beneath it, induced magnetic "
                "field measurements from Galileo point to a global conducting layer — a salty "
                "ocean, in contact with a rocky floor."
            ),
            physical=[
                prop("Mean radius", 1560.8, "km"),
                prop("Mass", 4.800e22, "kg"),
                prop("Surface gravity", 1.314, "m/s²"),
                prop("Escape velocity", 2.025, "km/s"),
                prop("Mean density", 3013, "kg/m³"),
                prop("Surface temperature", -160, "°C", note="Equatorial mean"),
                prop("Geometric albedo", 0.67),
            ],
            orbital=[
                prop("Distance from Jupiter", 671_100, "km"),
                prop("Orbital period", 3.551, "days"),
                prop("Orbital velocity", 13.74, "km/s"),
                prop("Eccentricity", 0.009),
            ],
            facts=[
                "Its ocean may hold two to three times the volume of all Earth's oceans combined.",
                "Io, Europa and Ganymede are locked in a 4:2:1 resonance that keeps all three tidally heated.",
            ],
            related_ids=["jupiter", "io", "ganymede", "enceladus"],
            appearance=Appearance(
                base_color="#C9BDA8",
                accent_color="#8A6A52",
                radius_km=1560.8,
                texture=_T.ICY,
                albedo=0.67,
            ),
            field_depth=0.35,
            sources=_FACTS,
        ),

        CatalogObject(
            id="ganymede",
            name="Ganymede",
            designation="Jupiter III",
            kind=ObjectKind.MOON,
            parent_id="jupiter",
            classification="Natural satellite",
            tagline="Bigger than Mercury, and the only moon with a magnetic field of its own.",
            overview=(
                "Ganymede is the largest moon in the solar system and larger than the planet "
                "Mercury, though only about half its mass. A liquid iron core generates an "
                "intrinsic magnetic field — unique among moons — which carves a small "
                "magnetosphere inside Jupiter's vastly larger one."
            ),
            physical=[
                prop("Mean radius", 2634.1, "km", note="Larger than Mercury"),
                prop("Mass", 1.4819e23, "kg"),
                prop("Surface gravity", 1.428, "m/s²"),
                prop("Escape velocity", 2.741, "km/s"),
                prop("Mean density", 1936, "kg/m³"),
            ],
            orbital=[
                prop("Distance from Jupiter", 1_070_400, "km"),
                prop("Orbital period", 7.155, "days"),
                prop("Orbital velocity", 10.88, "km/s"),
            ],
            facts=["It probably holds a subsurface ocean beneath about 150 km of ice."],
            related_ids=["jupiter", "europa", "callisto"],
            appearance=Appearance(
                base_color="#9C9084",
                accent_color="#C4BAAE",
                radius_km=2634.1,
                texture=_T.CRATERED,
                albedo=0.43,
            ),
            field_depth=0.35,
            sources=_FACTS,
        ),

        CatalogObject(
            id="callisto",
            name="Callisto",
            designation="Jupiter IV",
            kind=ObjectKind.MOON,
            parent_id="jupiter",
            classification="Natural satellite",
            tagline="The most heavily cratered object known — a surface saturated with impacts.",
            overview=(
                "Callisto has been geologically quiet for so long that its surface has reached "
                "impact saturation: every new crater destroys an old one. It also orbits outside "
                "the worst of Jupiter's radiation belts, which has repeatedly made it the "
                "candidate of choice in crewed Jupiter mission studies."
            ),
            physical=[
                prop("Mean radius", 2410.3, "km"),
                prop("Mass", 1.0759e23, "kg"),
                prop("Surface gravity", 1.235, "m/s²"),
                prop("Escape velocity", 2.440, "km/s"),
                prop("Mean density", 1834, "kg/m³"),
            ],
            orbital=[
                prop("Distance from Jupiter", 1_882_700, "km"),
                prop("Orbital period", 16.689, "days"),
                prop("Orbital velocity", 8.20, "km/s"),
            ],
            facts=["It is the only Galilean moon not locked in the Laplace resonance, and the only one not tidally heated."],
            related_ids=["jupiter", "ganymede"],
            appearance=Appearance(
                base_color="#6E655C",
                accent_color="#A69C90",
                radius_km=2410.3,
                texture=_T.CRATERED,
                albedo=0.22,
            ),
            field_depth=0.3,
            sources=_FACTS,
        ),

        CatalogObject(
            id="titan",
            name="Titan",
            designation="Saturn VI",
            kind=ObjectKind.MOON,
            parent_id="saturn",
            classification="Natural satellite",
            tagline="The only moon with a thick atmosphere, and rain, rivers and seas of liquid methane.",
            overview=(
                "Titan's surface pressure is half again Earth's, under a nitrogen atmosphere "
                "thick with orange organic haze. At −179 °C methane plays the role water plays "
                "here: it rains, cuts channels, and pools into seas. Low gravity plus dense air "
                "means a person there could fly by strapping on wings."
            ),
            physical=[
                prop("Mean radius", 2574.7, "km", note="Larger than Mercury"),
                prop("Mass", 1.3452e23, "kg"),
                prop("Surface gravity", 1.352, "m/s²"),
                prop("Escape velocity", 2.639, "km/s"),
                prop("Mean density", 1880, "kg/m³"),
                prop("Surface temperature", -179, "°C"),
            ],
            orbital=[
                prop("Distance from Saturn", 1_221_870, "km"),
                prop("Orbital period", 15.945, "days"),
                prop("Orbital velocity", 5.57, "km/s"),
            ],
            atmosphere=[
                text_prop("Composition", "N₂ 94.2%, CH₄ 5.65%, H₂ 0.1%"),
                prop("Surface pressure", 146_700, "Pa", note="1.45 times Earth's", earth_ratio=1.45),
                prop("Surface density", 5.4, "kg/m³", note="4.4 times Earth's sea-level air", earth_ratio=4.4),
            ],
            facts=[
                "Huygens landed there in 2005 — the most distant landing ever achieved.",
                "Dragonfly, a nuclear-powered rotorcraft, is being built to fly between sites on its surface.",
            ],
            mission_ids=["cassini"],
            related_ids=["saturn", "enceladus", "europa"],
            concept_slugs=["atmospheric-drag"],
            appearance=Appearance(
                base_color="#C98A3E",
                accent_color="#E8B96B",
                radius_km=2574.7,
                texture=_T.GASEOUS,
                albedo=0.22,
                atmosphere_color="#E5A85C",
                atmosphere_strength=0.95,
            ),
            field_depth=0.35,
            sources=_FACTS,
        ),

        CatalogObject(
            id="enceladus",
            name="Enceladus",
            designation="Saturn II",
            kind=ObjectKind.MOON,
            parent_id="saturn",
            classification="Natural satellite",
            tagline="Firing ocean water into space from fractures at its south pole.",
            overview=(
                "Enceladus is 504 km across and geologically alive. Plumes erupt from four "
                "fractures near the south pole, feeding Saturn's E ring. Cassini flew through "
                "them and found water, salts, silica and organic molecules — a sample of a "
                "subsurface ocean, collected without landing."
            ),
            physical=[
                prop("Mean radius", 252.1, "km"),
                prop("Mass", 1.08e20, "kg"),
                prop("Surface gravity", 0.113, "m/s²", earth_ratio=0.0115),
                prop("Escape velocity", 0.239, "km/s"),
                prop("Mean density", 1609, "kg/m³"),
                prop("Geometric albedo", 1.375, note="The most reflective body in the solar system"),
            ],
            orbital=[
                prop("Distance from Saturn", 237_948, "km"),
                prop("Orbital period", 1.370, "days"),
                prop("Orbital velocity", 12.63, "km/s"),
            ],
            facts=[
                "Its escape velocity is so low that plume material leaves the moon entirely and forms a ring around Saturn.",
                "Silica grains in the plume imply hydrothermal activity on the ocean floor at 90 °C or more.",
            ],
            mission_ids=["cassini"],
            related_ids=["saturn", "titan", "europa"],
            appearance=Appearance(
                base_color="#E8EAEC",
                accent_color="#B8CDD6",
                radius_km=252.1,
                texture=_T.ICY,
                albedo=0.99,
            ),
            field_depth=0.3,
            sources=_FACTS,
        ),

        CatalogObject(
            id="triton",
            name="Triton",
            designation="Neptune I",
            kind=ObjectKind.MOON,
            parent_id="neptune",
            classification="Natural satellite, captured",
            tagline="Orbiting backwards, with nitrogen geysers on a surface at −235 °C.",
            overview=(
                "Triton goes round Neptune the wrong way, which no moon formed in place can do. "
                "It was almost certainly captured from the Kuiper Belt, making it a close cousin "
                "of Pluto that happens to be in orbit. That retrograde path is decaying: in a few "
                "billion years tides will pull it apart into a ring."
            ),
            physical=[
                prop("Mean radius", 1353.4, "km"),
                prop("Mass", 2.139e22, "kg"),
                prop("Surface gravity", 0.779, "m/s²"),
                prop("Escape velocity", 1.455, "km/s"),
                prop("Surface temperature", -235, "°C", note="One of the coldest surfaces measured"),
                prop("Geometric albedo", 0.76),
            ],
            orbital=[
                prop("Distance from Neptune", 354_759, "km"),
                prop("Orbital period", 5.877, "days", note="Retrograde"),
                prop("Inclination to Neptune's equator", 157.3, "°"),
            ],
            facts=["Voyager 2 photographed active nitrogen geysers throwing plumes 8 km high."],
            mission_ids=["voyager-2"],
            related_ids=["neptune", "pluto"],
            appearance=Appearance(
                base_color="#D6C8BC",
                accent_color="#E8A882",
                radius_km=1353.4,
                texture=_T.ICY,
                albedo=0.76,
            ),
            field_depth=0.25,
            sources=_FACTS,
        ),

        CatalogObject(
            id="phobos",
            name="Phobos",
            designation="Mars I",
            kind=ObjectKind.MOON,
            parent_id="mars",
            classification="Natural satellite",
            tagline="Spiralling in, and doomed to break apart into a ring around Mars.",
            overview=(
                "Phobos orbits below the areostationary altitude, so tides drag it inward rather "
                "than pushing it out. It loses about 1.8 centimetres a year and will be torn "
                "apart inside the Roche limit within roughly 50 million years."
            ),
            physical=[
                prop("Mean radius", 11.267, "km", note="Irregular: 27 × 22 × 18 km"),
                prop("Mass", 1.0659e16, "kg"),
                prop("Surface gravity", 0.0057, "m/s²", note="A brisk jump would reach orbit"),
                prop("Escape velocity", 11.4, "m/s"),
            ],
            orbital=[
                prop("Distance from Mars", 9376, "km", note="Closer than any other moon to its planet"),
                prop("Orbital period", 7.653, "hours", note="Faster than Mars rotates"),
                prop("Orbital decay", -1.8, "cm/year"),
            ],
            facts=["It rises in the west and sets in the east, twice a day, because it laps the planet."],
            related_ids=["mars", "deimos"],
            appearance=Appearance(
                base_color="#6B6259",
                radius_km=11.267,
                texture=_T.IRREGULAR,
                albedo=0.071,
            ),
            field_depth=0.4,
            sources=_FACTS,
        ),

        CatalogObject(
            id="deimos",
            name="Deimos",
            designation="Mars II",
            kind=ObjectKind.MOON,
            parent_id="mars",
            classification="Natural satellite",
            tagline="Mars's smaller, outer moon — a captured asteroid barely 12 km across.",
            overview=(
                "Deimos is smooth compared with Phobos, its craters partly filled by regolith. "
                "From the Martian surface it would look like a bright star, crossing the sky over "
                "two and a half days."
            ),
            physical=[
                prop("Mean radius", 6.2, "km", note="Irregular: 15 × 12 × 11 km"),
                prop("Mass", 1.4762e15, "kg"),
                prop("Surface gravity", 0.003, "m/s²"),
                prop("Escape velocity", 5.6, "m/s"),
            ],
            orbital=[
                prop("Distance from Mars", 23_463, "km"),
                prop("Orbital period", 30.31, "hours"),
            ],
            facts=["It is slowly receding from Mars, unlike Phobos."],
            related_ids=["mars", "phobos"],
            appearance=Appearance(
                base_color="#7A7065",
                radius_km=6.2,
                texture=_T.IRREGULAR,
                albedo=0.068,
            ),
            field_depth=0.4,
            sources=_FACTS,
        ),
    ]


def _small_bodies() -> List[CatalogObject]:
    return [
        CatalogObject(
            id="bennu",
            name="Bennu",
            designation="(101955) Bennu",
            kind=ObjectKind.ASTEROID,
            parent_id="sol",
            classification="Near-Earth asteroid, Apollo group",
            tagline="A rubble pile so loosely bound that the sampling arm sank into it.",
            overview=(
                "OSIRIS-REx went to Bennu expecting a sandy beach and found a boulder field. "
                "When the sampling head touched down it met almost no resistance — the surface "
                "behaved like a ball pit. That single measurement changed how the field models "
                "the strength of rubble-pile asteroids, which matters for any future deflection."
            ),
            physical=[
                prop("Mean radius", 0.2625, "km", note="490 m across"),
                prop("Mass", 7.329e10, "kg"),
                prop("Surface gravity", 6e-5, "m/s²"),
                prop("Escape velocity", 0.20, "m/s", note="Slower than a walk"),
                prop("Mean density", 1190, "kg/m³", note="Roughly 50% empty space"),
                prop("Geometric albedo", 0.044, note="Darker than charcoal"),
            ],
            orbital=[
                prop("Semi-major axis", 1.126, "AU"),
                prop("Orbital period", 1.195, "years"),
                prop("Eccentricity", 0.2037),
                prop("Inclination", 6.035, "°"),
                prop("Rotation period", 4.296, "hours"),
            ],
            facts=[
                "OSIRIS-REx returned 121.6 g of Bennu to Earth on 24 September 2023.",
                "It has roughly a 1-in-2,700 chance of striking Earth in the late 2100s — tracked, not imminent.",
            ],
            related_ids=["ryugu", "eros", "apophis"],
            concept_slugs=["orbital-mechanics"],
            appearance=Appearance(
                base_color="#4A443E",
                accent_color="#6E665C",
                radius_km=0.2625,
                texture=_T.IRREGULAR,
                albedo=0.044,
            ),
            field_depth=0.5,
            sources=_FACTS,
        ),

        CatalogObject(
            id="ryugu",
            name="Ryugu",
            designation="(162173) Ryugu",
            kind=ObjectKind.ASTEROID,
            parent_id="sol",
            classification="Near-Earth asteroid, Apollo group",
            tagline="Hayabusa2 shot it with a copper impactor to sample material never exposed to space.",
            overview=(
                "Ryugu is a spinning-top-shaped carbonaceous asteroid. Hayabusa2 collected a "
                "surface sample, then fired a 2 kg copper projectile to excavate a crater and "
                "sampled the subsurface material as well — the first time anyone had retrieved "
                "material shielded from billions of years of space weathering."
            ),
            physical=[
                prop("Mean radius", 0.448, "km"),
                prop("Mass", 4.5e11, "kg"),
                prop("Escape velocity", 0.37, "m/s"),
                prop("Mean density", 1190, "kg/m³"),
                prop("Geometric albedo", 0.045),
            ],
            orbital=[
                prop("Semi-major axis", 1.19, "AU"),
                prop("Orbital period", 1.30, "years"),
                prop("Eccentricity", 0.1902),
                prop("Rotation period", 7.63, "hours"),
            ],
            facts=[
                "Hayabusa2 returned 5.4 g of Ryugu in December 2020.",
                "The samples contain amino acids, including some never before found in an extraterrestrial sample.",
            ],
            related_ids=["bennu", "eros"],
            appearance=Appearance(
                base_color="#413C37",
                radius_km=0.448,
                texture=_T.IRREGULAR,
                albedo=0.045,
            ),
            field_depth=0.5,
            sources=_FACTS,
        ),

        CatalogObject(
            id="eros",
            name="Eros",
            designation="(433) Eros",
            kind=ObjectKind.ASTEROID,
            parent_id="sol",
            classification="Near-Earth asteroid, Amor group",
            tagline="The first asteroid orbited, and the first landed on.",
            overview=(
                "NEAR Shoemaker orbited Eros for a year and then, with the mission over and "
                "nothing to lose, was flown into the surface. It survived, transmitting from the "
                "ground — the first landing on an asteroid, achieved by a spacecraft never "
                "designed to land."
            ),
            physical=[
                prop("Mean radius", 8.42, "km", note="Elongated: 34 × 11 × 11 km"),
                prop("Mass", 6.687e15, "kg"),
                prop("Escape velocity", 10.3, "m/s"),
                prop("Mean density", 2670, "kg/m³"),
            ],
            orbital=[
                prop("Semi-major axis", 1.458, "AU"),
                prop("Orbital period", 1.76, "years"),
                prop("Eccentricity", 0.2226),
                prop("Rotation period", 5.27, "hours"),
            ],
            facts=["Gravity varies so much across its length that 'down' points in noticeably different directions."],
            related_ids=["bennu", "ryugu", "psyche"],
            appearance=Appearance(
                base_color="#8A7A63",
                radius_km=8.42,
                texture=_T.IRREGULAR,
                albedo=0.25,
            ),
            field_depth=0.45,
            sources=_FACTS,
        ),

        CatalogObject(
            id="psyche",
            name="Psyche",
            designation="(16) Psyche",
            kind=ObjectKind.ASTEROID,
            parent_id="sol",
            classification="Main-belt asteroid, M-type",
            tagline="Metal-rich, and possibly the exposed core of a shattered protoplanet.",
            overview=(
                "Psyche is unusually dense and radar-bright, consistent with a large fraction of "
                "iron and nickel. If it is the stripped core of an early planetesimal, it is the "
                "only chance anyone has to look directly at the kind of material that makes up "
                "Earth's own core. The Psyche spacecraft launched in October 2023 and arrives in 2029."
            ),
            physical=[
                prop("Mean radius", 111, "km", note="278 × 232 × 164 km"),
                prop("Mass", 2.29e19, "kg"),
                prop("Mean density", 3780, "kg/m³"),
                prop("Geometric albedo", 0.16),
            ],
            orbital=[
                prop("Semi-major axis", 2.923, "AU"),
                prop("Orbital period", 4.99, "years"),
                prop("Eccentricity", 0.134),
                prop("Rotation period", 4.196, "hours"),
            ],
            facts=["The Psyche mission carries a laser optical communications experiment, tested at over 30 million km."],
            related_ids=["ceres", "eros"],
            appearance=Appearance(
                base_color="#8E8A85",
                accent_color="#B9B3A8",
                radius_km=111,
                texture=_T.METALLIC,
                albedo=0.16,
            ),
            field_depth=0.4,
            sources=_FACTS,
        ),

        CatalogObject(
            id="apophis",
            name="Apophis",
            designation="(99942) Apophis",
            kind=ObjectKind.ASTEROID,
            parent_id="sol",
            classification="Near-Earth asteroid, Aten group",
            tagline="Passing inside geostationary orbit on 13 April 2029, visible to the naked eye.",
            overview=(
                "For a few years after its discovery Apophis carried the highest impact rating "
                "ever assigned. Better observations removed that risk entirely. What remains is "
                "an exceptionally close approach: on 13 April 2029 it passes about 31,600 km "
                "from Earth's surface — nearer than the satellites in geostationary orbit."
            ),
            physical=[
                prop("Mean radius", 0.17, "km", note="About 340 m across"),
                prop("Mass", 6.1e10, "kg"),
                prop("Geometric albedo", 0.23),
            ],
            orbital=[
                prop("Semi-major axis", 0.9224, "AU"),
                prop("Orbital period", 0.886, "years"),
                prop("Eccentricity", 0.1914),
                prop("Inclination", 3.34, "°"),
                prop("2029 close approach", 31_600, "km", note="Altitude above Earth's surface"),
            ],
            facts=[
                "Earth's tides are expected to measurably change its spin during the 2029 flyby.",
                "It has been ruled out as an impact risk for at least the next hundred years.",
            ],
            related_ids=["bennu", "earth"],
            appearance=Appearance(
                base_color="#7E7566",
                radius_km=0.17,
                texture=_T.IRREGULAR,
                albedo=0.23,
            ),
            field_depth=0.5,
            sources=_FACTS,
        ),

        CatalogObject(
            id="halley",
            name="Halley's Comet",
            designation="1P/Halley",
            kind=ObjectKind.COMET,
            parent_id="sol",
            classification="Periodic comet, Halley-type",
            tagline="Returns every 75 years; next perihelion in 2061.",
            overview=(
                "Halley was the comet that proved comets are periodic: Edmond Halley noticed "
                "that three recorded apparitions shared an orbit and predicted the return. In "
                "1986 the Giotto probe flew within 600 km of the nucleus and photographed it — "
                "a dark, peanut-shaped body venting jets from its sunward side."
            ),
            physical=[
                prop("Nucleus dimensions", 15, "km", note="Roughly 15 × 8 × 8 km"),
                prop("Mass", 2.2e14, "kg"),
                prop("Geometric albedo", 0.04, note="One of the darkest objects known"),
            ],
            orbital=[
                prop("Semi-major axis", 17.834, "AU"),
                prop("Orbital period", 75.3, "years"),
                prop("Eccentricity", 0.967, note="Highly elliptical"),
                prop("Inclination", 162.3, "°", note="Retrograde"),
                prop("Perihelion", 0.586, "AU"),
                prop("Aphelion", 35.08, "AU", note="Beyond Neptune"),
            ],
            facts=[
                "It is the source of both the Orionid and Eta Aquariid meteor showers.",
                "Its 1066 apparition is embroidered into the Bayeux Tapestry.",
            ],
            related_ids=["churyumov-gerasimenko"],
            appearance=Appearance(
                base_color="#5A5A56",
                accent_color="#9FC4CC",
                radius_km=5.5,
                texture=_T.IRREGULAR,
                albedo=0.04,
                atmosphere_color="#A8D4DC",
                atmosphere_strength=0.4,
            ),
            field_depth=0.45,
            sources=_FACTS,
        ),

        CatalogObject(
            id="churyumov-gerasimenko",
            name="Comet 67P",
            designation="67P/Churyumov–Gerasimenko",
            kind=ObjectKind.COMET,
            parent_id="sol",
            classification="Jupiter-family comet",
            tagline="Rosetta orbited it for two years and dropped a lander onto its surface.",
            overview=(
                "67P is a contact binary — two lobes joined by a neck — and Rosetta watched it "
                "wake up as it approached the Sun, mapping where the jets came from and how the "
                "surface changed. Philae's landing did not go to plan: the harpoons failed, it "
                "bounced twice, and came to rest in shadow with too little sunlight to recharge."
            ),
            physical=[
                prop("Dimensions", 4.3, "km", note="Two lobes, 4.1 × 3.3 km and 2.6 × 2.3 km"),
                prop("Mass", 9.982e12, "kg"),
                prop("Mean density", 533, "kg/m³", note="Less than half the density of water ice"),
                prop("Escape velocity", 1.0, "m/s"),
            ],
            orbital=[
                prop("Semi-major axis", 3.462, "AU"),
                prop("Orbital period", 6.44, "years"),
                prop("Eccentricity", 0.641),
                prop("Rotation period", 12.4, "hours"),
            ],
            facts=[
                "The deuterium-to-hydrogen ratio in its water differs from Earth's, arguing against Jupiter-family comets as the source of Earth's oceans.",
                "Rosetta ended its mission by descending onto the comet and transmitting until impact.",
            ],
            related_ids=["halley"],
            appearance=Appearance(
                base_color="#4C4741",
                accent_color="#8FA5A8",
                radius_km=2.0,
                texture=_T.IRREGULAR,
                albedo=0.06,
                atmosphere_color="#9FBFC6",
                atmosphere_strength=0.3,
            ),
            field_depth=0.45,
            sources=_FACTS,
        ),
    ]


def _spacecraft() -> List[CatalogObject]:
    return [
        CatalogObject(
            id="voyager-1",
            name="Voyager 1",
            kind=ObjectKind.SPACECRAFT,
            classification="Interstellar probe",
            tagline="The most distant human-made object, still returning data after nearly fifty years.",
            overview=(
                "Voyager 1 crossed the heliopause in August 2012 and has been in interstellar "
                "space ever since. Its radioisotope generators lose about four watts a year, so "
                "instruments have been switched off one at a time to keep the rest alive. A "
                "signal from it takes over twenty-two hours to reach Earth."
            ),
            physical=[
                prop("Launch mass", 825.5, "kg"),
                prop("High-gain antenna diameter", 3.7, "m"),
                prop("Power at launch", 470, "W", note="Three radioisotope thermoelectric generators"),
            ],
            orbital=[
                prop("Heliocentric velocity", 17.0, "km/s"),
                prop("Distance from Sun", 165, "AU", note="Increasing by about 3.6 AU per year"),
            ],
            facts=[
                "It carries the Golden Record: 115 images and greetings in 55 languages.",
                "In 1990 it turned around and photographed Earth from 6 billion km — the Pale Blue Dot.",
                "In 2023 a failing computer garbled its telemetry for months; engineers patched it from 24 billion km away.",
            ],
            mission_ids=["voyager-1"],
            related_ids=["voyager-2", "jupiter", "saturn"],
            concept_slugs=["scale-of-the-universe", "gravity-assist"],
            appearance=Appearance(
                base_color="#B9BDC2",
                accent_color="#E4682E",
                radius_km=0.004,
                texture=_T.ENGINEERED,
                albedo=0.5,
            ),
            field_depth=0.9,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="voyager-2",
            name="Voyager 2",
            kind=ObjectKind.SPACECRAFT,
            classification="Interstellar probe",
            tagline="The only spacecraft to have visited Uranus and Neptune.",
            overview=(
                "Voyager 2 flew the Grand Tour: Jupiter, Saturn, Uranus, Neptune, using each "
                "encounter to bend its path toward the next. The alignment that made it possible "
                "recurs about every 175 years. Almost everything known first-hand about the ice "
                "giants comes from a few hours of these flybys."
            ),
            physical=[
                prop("Launch mass", 825.5, "kg"),
                prop("Power at launch", 470, "W"),
            ],
            orbital=[
                prop("Heliocentric velocity", 15.4, "km/s"),
                prop("Distance from Sun", 138, "AU"),
            ],
            facts=[
                "Launched 20 August 1977, sixteen days before Voyager 1.",
                "It entered interstellar space in November 2018, six years after its twin.",
            ],
            mission_ids=["voyager-2"],
            related_ids=["voyager-1", "uranus", "neptune"],
            concept_slugs=["gravity-assist"],
            appearance=Appearance(
                base_color="#B9BDC2",
                accent_color="#E4682E",
                radius_km=0.004,
                texture=_T.ENGINEERED,
                albedo=0.5,
            ),
            field_depth=0.9,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="new-horizons",
            name="New Horizons",
            kind=ObjectKind.SPACECRAFT,
            classification="Kuiper Belt flyby probe",
            tagline="Left Earth faster than anything before it, and still took nine and a half years to reach Pluto.",
            overview=(
                "New Horizons had one shot. There was no fuel to enter orbit, so the entire "
                "Pluto encounter — every image, every spectrum — had to happen in a few hours "
                "during a flyby at 13.8 km/s, executed from a stored sequence with Earth four "
                "and a half light-hours away."
            ),
            physical=[
                prop("Launch mass", 478, "kg"),
                prop("Launch velocity", 16.26, "km/s", note="The fastest Earth departure ever flown"),
                prop("Power", 245, "W", note="At Pluto encounter"),
            ],
            orbital=[
                prop("Distance from Sun", 60, "AU"),
                prop("Velocity", 13.6, "km/s"),
            ],
            facts=[
                "A Jupiter gravity assist in 2007 cut three years off the journey.",
                "It flew past Arrokoth on 1 January 2019, the most distant object ever visited closely.",
            ],
            mission_ids=["new-horizons"],
            related_ids=["pluto", "jupiter"],
            concept_slugs=["gravity-assist", "delta-v-budget"],
            appearance=Appearance(
                base_color="#C9BFA8",
                accent_color="#E4682E",
                radius_km=0.0013,
                texture=_T.ENGINEERED,
                albedo=0.5,
            ),
            field_depth=0.85,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="parker-solar-probe",
            name="Parker Solar Probe",
            kind=ObjectKind.SPACECRAFT,
            classification="Solar probe",
            tagline="The fastest object ever built, flying through the Sun's corona behind a carbon shield.",
            overview=(
                "Getting close to the Sun is a problem of shedding energy, not gaining it: Earth "
                "carries 30 km/s of orbital velocity that has to go somewhere. Parker uses seven "
                "Venus gravity assists to drop its perihelion step by step, hiding behind a "
                "11.4 cm carbon-composite shield that runs at 1,370 °C while the instruments "
                "behind it stay near room temperature."
            ),
            physical=[
                prop("Launch mass", 685, "kg"),
                prop("Heat shield temperature", 1370, "°C"),
                prop("Heat shield thickness", 11.4, "cm"),
            ],
            orbital=[
                prop("Peak velocity", 192, "km/s", note="About 692,000 km/h — the fastest ever achieved"),
                prop("Closest approach", 6.1e6, "km", note="3.8 million miles from the photosphere"),
                prop("Orbital period", 88, "days", note="At final perihelion"),
            ],
            facts=[
                "It is the first spacecraft named after a living person, Eugene Parker, who predicted the solar wind in 1958.",
                "At closest approach it covers the distance from London to New York in under thirty seconds.",
            ],
            mission_ids=["parker-solar-probe"],
            related_ids=["sol", "venus"],
            concept_slugs=["gravity-assist", "delta-v-budget"],
            appearance=Appearance(
                base_color="#D8D4CC",
                accent_color="#FFCF87",
                radius_km=0.002,
                texture=_T.ENGINEERED,
                albedo=0.7,
            ),
            field_depth=0.8,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="perseverance",
            name="Perseverance",
            kind=ObjectKind.SPACECRAFT,
            classification="Mars rover",
            tagline="Caching samples in Jezero Crater for a return mission that has not launched yet.",
            overview=(
                "Perseverance landed in Jezero Crater, an ancient river delta, and is drilling "
                "cores into sealed tubes for a future mission to collect. It also carried "
                "MOXIE, which made breathable oxygen out of the Martian atmosphere, and "
                "Ingenuity, which proved powered flight is possible in air 1% as dense as Earth's."
            ),
            physical=[
                prop("Mass", 1025, "kg", note="The heaviest rover landed on Mars"),
                prop("Length", 3.0, "m"),
                prop("Power", 110, "W", note="Radioisotope thermoelectric generator"),
                prop("Entry velocity", 5.4, "km/s"),
            ],
            orbital=[prop("Landing site latitude", 18.44, "°N", note="Jezero Crater")],
            facts=[
                "MOXIE produced oxygen from atmospheric CO₂ — the first use of a resource made on another planet.",
                "Ingenuity flew 72 times before a rotor was damaged, having been designed for five flights.",
            ],
            mission_ids=["perseverance"],
            related_ids=["mars", "curiosity"],
            concept_slugs=["reentry-heating", "atmospheric-drag"],
            appearance=Appearance(
                base_color="#C4C0B6",
                accent_color="#B4552F",
                radius_km=0.0015,
                texture=_T.ENGINEERED,
                albedo=0.4,
            ),
            field_depth=0.8,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="curiosity",
            name="Curiosity",
            kind=ObjectKind.SPACECRAFT,
            classification="Mars rover",
            tagline="Lowered onto Mars by a rocket-powered sky crane in 2012, still driving.",
            overview=(
                "Curiosity was too heavy for airbags, so JPL built the sky crane: a descent "
                "stage that hovered on eight throttleable engines and winched the rover to the "
                "surface on cables before flying away to crash at a safe distance. It worked on "
                "the first attempt, with no way to test it end to end on Earth."
            ),
            physical=[
                prop("Mass", 899, "kg"),
                prop("Power", 110, "W"),
                prop("Distance driven", 34, "km", note="Cumulative, and still increasing"),
            ],
            orbital=[prop("Landing site latitude", -4.59, "°", note="Gale Crater")],
            facts=[
                "It found the mudstone evidence that Gale Crater once held a long-lived freshwater lake.",
                "It detects seasonal swings in atmospheric methane that remain unexplained.",
            ],
            mission_ids=["curiosity"],
            related_ids=["mars", "perseverance"],
            appearance=Appearance(
                base_color="#B8B4AA",
                accent_color="#B4552F",
                radius_km=0.0015,
                texture=_T.ENGINEERED,
                albedo=0.4,
            ),
            field_depth=0.75,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="chandrayaan-3",
            name="Chandrayaan-3",
            kind=ObjectKind.SPACECRAFT,
            classification="Lunar lander and rover",
            tagline="The first landing near the Moon's south pole, in August 2023.",
            overview=(
                "Chandrayaan-3 followed a lander that had crashed four years earlier, and the "
                "redesign was driven directly by that failure: a stronger structure, wider "
                "landing footprint, more propellant margin, and software that could tolerate "
                "larger errors. It touched down at 69.37°S — closer to a pole than any previous "
                "lunar landing."
            ),
            physical=[
                prop("Total launch mass", 3900, "kg"),
                prop("Lander mass", 1752, "kg", note="Vikram, including the Pragyan rover"),
                prop("Rover mass", 26, "kg", note="Pragyan"),
            ],
            orbital=[prop("Landing site latitude", -69.37, "°", note="Near the lunar south pole")],
            facts=[
                "It measured the lunar regolith temperature profile and confirmed sulphur in the polar soil.",
                "The mission cost roughly $75 million — less than many feature films.",
            ],
            mission_ids=["chandrayaan-3"],
            related_ids=["luna", "perseverance"],
            concept_slugs=["delta-v-budget"],
            appearance=Appearance(
                base_color="#C9B896",
                accent_color="#E4682E",
                radius_km=0.002,
                texture=_T.ENGINEERED,
                albedo=0.45,
            ),
            field_depth=0.75,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="jwst",
            name="James Webb Space Telescope",
            kind=ObjectKind.TELESCOPE,
            classification="Infrared space observatory",
            tagline="A 6.5-metre mirror at −233 °C, 1.5 million km from Earth, with no way to repair it.",
            overview=(
                "Webb had 344 single-point failure modes during deployment, every one of which "
                "had to work with no possibility of a service mission. The five-layer sunshield "
                "unfolded to the size of a tennis court, the eighteen mirror segments aligned to "
                "within nanometres, and the observatory reached its operating temperature of "
                "around 40 K entirely by radiating heat away."
            ),
            physical=[
                prop("Primary mirror diameter", 6.5, "m", note="18 beryllium segments, gold-coated"),
                prop("Collecting area", 25.4, "m²", note="Over six times Hubble's"),
                prop("Mass", 6200, "kg"),
                prop("Operating temperature", 40, "K", note="−233 °C"),
                prop("Sunshield dimensions", 21.2, "m", note="21.2 × 14.2 m, five layers"),
            ],
            orbital=[
                prop("Distance from Earth", 1.5e6, "km", note="Sun–Earth L2 halo orbit"),
                prop("Orbital period", 6, "months", note="Around L2"),
            ],
            facts=[
                "It observes in infrared, so it sees light from the earliest galaxies, redshifted out of the visible.",
                "L2 keeps the Sun, Earth and Moon all on one side, so a single shield blocks all three.",
            ],
            mission_ids=["jwst"],
            related_ids=["hubble", "earth"],
            concept_slugs=["light", "scale-of-the-universe"],
            appearance=Appearance(
                base_color="#D9B24C",
                accent_color="#C0C4C9",
                radius_km=0.01,
                texture=_T.ENGINEERED,
                albedo=0.6,
            ),
            field_depth=0.85,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="hubble",
            name="Hubble Space Telescope",
            kind=ObjectKind.TELESCOPE,
            classification="Optical and ultraviolet space observatory",
            tagline="Launched with a flawed mirror, fixed by hand in orbit, and observing for over three decades.",
            overview=(
                "Hubble's primary mirror was ground to the wrong shape by 2.2 micrometres, and "
                "the first images were blurred. Because the telescope was designed to be "
                "serviced, astronauts installed corrective optics in 1993 and it went on to "
                "become the most productive scientific instrument ever built."
            ),
            physical=[
                prop("Primary mirror diameter", 2.4, "m"),
                prop("Mass", 11_110, "kg"),
                prop("Length", 13.2, "m"),
                prop("Pointing accuracy", 0.007, "arcsec", note="Holding a laser on a coin 320 km away"),
            ],
            orbital=[
                prop("Altitude", 535, "km"),
                prop("Orbital period", 95, "minutes"),
                prop("Inclination", 28.5, "°"),
                prop("Orbital velocity", 7.59, "km/s"),
            ],
            facts=[
                "Five servicing missions replaced instruments, gyroscopes and solar arrays between 1993 and 2009.",
                "The Hubble Deep Field pointed at an apparently empty patch of sky for ten days and found thousands of galaxies.",
            ],
            mission_ids=["hubble"],
            related_ids=["jwst", "earth", "iss"],
            concept_slugs=["light", "orbital-decay"],
            appearance=Appearance(
                base_color="#B0B4B9",
                accent_color="#FFCF87",
                radius_km=0.007,
                texture=_T.ENGINEERED,
                albedo=0.55,
            ),
            field_depth=0.8,
            sources=[BUNDLED],
        ),

        CatalogObject(
            id="iss",
            name="International Space Station",
            kind=ObjectKind.STATION,
            classification="Crewed orbital laboratory",
            tagline="420 tonnes in low Earth orbit, continuously crewed since November 2000.",
            overview=(
                "The station orbits at around 408 km, low enough that residual atmosphere still "
                "drags on it. Left alone it would lose several hundred metres of altitude a "
                "month, so visiting vehicles periodically reboost it — a live demonstration that "
                "low Earth orbit is not empty and orbits are not permanent."
            ),
            physical=[
                prop("Mass", 419_725, "kg"),
                prop("Pressurised volume", 388, "m³"),
                prop("Truss length", 109, "m"),
                prop("Solar array area", 2500, "m²"),
                prop("Power generated", 120, "kW"),
            ],
            orbital=[
                prop("Mean altitude", 408, "km"),
                prop("Orbital velocity", 7.66, "km/s"),
                prop("Orbital period", 92.9, "minutes"),
                prop("Inclination", 51.64, "°", note="Set so Baikonur can reach it"),
                prop("Orbits per day", 15.5),
            ],
            facts=[
                "Its 51.6° inclination exists so that launches from Baikonur, at 45.6°N, can reach it.",
                "It has been crewed without interruption since 2 November 2000.",
                "Reboosts counter atmospheric drag that would otherwise bring it down within a couple of years.",
            ],
            mission_ids=["iss"],
            related_ids=["earth", "hubble"],
            concept_slugs=["orbital-decay", "orbital-mechanics", "atmospheric-drag"],
            appearance=Appearance(
                base_color="#C0C4C9",
                accent_color="#3A4E7A",
                radius_km=0.05,
                texture=_T.ENGINEERED,
                albedo=0.6,
            ),
            field_x=0.52,
            field_y=0.46,
            field_depth=0.95,
            sources=[BUNDLED],
        ),
    ]


#: Every id in the catalog, for validation and cross-reference checks.
SPACE_OBJECT_IDS = [
    "sol", "mercury", "venus", "earth", "mars", "jupiter", "saturn", "uranus", "neptune",
    "pluto", "ceres",
    "luna", "io", "europa", "ganymede", "callisto", "titan", "enceladus", "triton",
    "phobos", "deimos",
    "bennu", "ryugu", "eros", "psyche", "apophis", "halley", "churyumov-gerasimenko",
    "voyager-1", "voyager-2", "new-horizons", "parker-solar-probe",
    "perseverance", "curiosity", "chandrayaan-3", "jwst", "hubble", "iss",
]


def space_objects_by_id() -> Dict[str, CatalogObject]:
    """The catalog keyed by id."""
    return {obj.id: obj for obj in build_space_objects()}
