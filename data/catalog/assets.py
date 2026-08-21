"""The asset library.

Every image the platform can show, in one place, with its metadata: what it
depicts, who took it, what licence it carries, and which parts of the product
use it. That last field is the reason this exists as a catalog rather than as a
folder — an asset nobody references is dead weight, and an asset referenced from
three screens needs to be findable from all three.

The imagery itself lives in `imagery.py`, verified. This module classifies it,
tags it, and links it to the objects, missions and lessons it illustrates.
"""

from typing import Dict, List

from ._helpers import BUNDLED
from .imagery import IMAGERY
from .models import AssetRecord

__all__ = ["build_assets", "assets_by_id", "ASSET_KINDS"]

#: Asset categories, in the order the library presents them.
ASSET_KINDS = [
    "planetary",
    "lunar",
    "small_body",
    "spacecraft",
    "launch",
    "deep_sky",
    "earth_observation",
    "facility",
]

#: Public-domain notice that applies to NASA media.
_NASA_LICENSE = (
    "Public domain (NASA media usage guidelines). Credit as shown; NASA does "
    "not endorse any use."
)

#: key -> (kind, tags, subjects it depicts, longer description)
_CLASSIFICATION: Dict[str, tuple] = {
    "sol": ("planetary", ["sun", "star", "corona", "plasma"], ["sol"],
            "The solar limb with an erupting prominence — the Sun's magnetic field made visible."),
    "mercury": ("planetary", ["mercury", "terrestrial", "craters"], ["mercury"],
                "A global mosaic assembled from MESSENGER's orbital imaging campaign."),
    "venus": ("planetary", ["venus", "radar", "terrestrial"], ["venus"],
              "Magellan mapped Venus by radar because its cloud deck is opaque to visible light."),
    "earth": ("planetary", ["earth", "home", "ocean", "atmosphere"], ["earth"],
              "A full-disc view of Earth, the reference body for every launch in this platform."),
    "luna": ("lunar", ["moon", "luna", "craters", "maria"], ["luna"],
             "The near side of the Moon, showing the contrast between dark maria and bright highlands."),
    "mars": ("planetary", ["mars", "terrestrial", "iron oxide"], ["mars"],
             "Mars in true colour — the red is iron oxide dust, distributed globally by wind."),
    "phobos": ("lunar", ["phobos", "mars", "moon"], ["phobos", "mars"],
               "Phobos, dominated by Stickney Crater, which is nearly half the moon's width."),
    "deimos": ("lunar", ["deimos", "mars", "moon"], ["deimos", "mars"],
               "Deimos, smoothed by regolith that has partly filled its craters."),
    "ceres": ("small_body", ["ceres", "dwarf planet", "asteroid belt"], ["ceres"],
              "Occator Crater's bright deposits, left by briny water reaching the surface."),
    "jupiter": ("planetary", ["jupiter", "gas giant", "bands", "great red spot"], ["jupiter"],
                "Jupiter's banded atmosphere, photographed by JunoCam on a close pass."),
    "io": ("lunar", ["io", "jupiter", "volcanism"], ["io", "jupiter"],
           "Io's surface, coloured by sulphur compounds from continuous volcanic resurfacing."),
    "europa": ("lunar", ["europa", "jupiter", "ice", "ocean"], ["europa", "jupiter"],
               "Europa's ice shell, cracked by the tidal flexing that also keeps its ocean liquid."),
    "ganymede": ("lunar", ["ganymede", "jupiter", "largest moon"], ["ganymede", "jupiter"],
                 "Ganymede, the largest moon in the solar system and the only one with a magnetic field."),
    "callisto": ("lunar", ["callisto", "jupiter", "craters"], ["callisto", "jupiter"],
                 "Callisto's surface has reached impact saturation: every new crater erases an old one."),
    "saturn": ("planetary", ["saturn", "gas giant", "rings"], ["saturn"],
               "Saturn with its rings, which are almost pure water ice and only metres thick."),
    "saturn-rings": ("planetary", ["saturn", "rings", "earth", "perspective"], ["saturn", "earth"],
                     "Earth seen as a point of light through the gap between Saturn's rings."),
    "titan": ("lunar", ["titan", "saturn", "atmosphere", "methane"], ["titan", "saturn"],
              "Titan's organic haze hides its surface completely at visible wavelengths."),
    "enceladus": ("lunar", ["enceladus", "saturn", "plumes", "ocean"], ["enceladus", "saturn"],
                  "Enceladus, the brightest body in the solar system, venting ocean water into space."),
    "uranus": ("planetary", ["uranus", "ice giant"], ["uranus"],
               "Uranus as Voyager 2 found it: an almost featureless disc, tipped on its side."),
    "neptune": ("planetary", ["neptune", "ice giant", "storms"], ["neptune"],
                "Neptune's Great Dark Spot and high-altitude methane cloud streaks."),
    "triton": ("lunar", ["triton", "neptune", "captured", "geysers"], ["triton", "neptune"],
               "Triton's cantaloupe terrain and bright polar cap, imaged during the 1989 flyby."),
    "pluto": ("small_body", ["pluto", "dwarf planet", "kuiper belt"], ["pluto"],
              "Pluto in enhanced colour, with the nitrogen ice plain of Sputnik Planitia at centre."),
    "apophis": ("small_body", ["apophis", "asteroid", "radar", "near-earth"], ["apophis"],
                "Radar imaging is how a small, fast-moving asteroid's shape and spin are measured."),
    "eros": ("small_body", ["eros", "asteroid", "near"], ["eros"],
             "Eros, the first asteroid orbited and the first landed on."),
    "psyche": ("spacecraft", ["psyche", "asteroid", "metal", "mission"], ["psyche"],
               "The Psyche spacecraft, en route to what may be an exposed planetary core."),
    "halley": ("small_body", ["halley", "comet", "nucleus"], ["halley"],
               "The nucleus of Halley's Comet — one of the darkest surfaces ever photographed."),
    "churyumov": ("small_body", ["67p", "comet", "rosetta"], ["churyumov-gerasimenko"],
                  "Comet 67P's contact-binary nucleus, active as it approached perihelion."),
    "voyager": ("spacecraft", ["voyager", "interstellar", "probe"], ["voyager-1", "voyager-2"],
                "The Voyager design: a high-gain dish, a boom of instruments, and three RTGs."),
    "cassini-craft": ("spacecraft", ["cassini", "saturn", "orbiter"], ["saturn", "titan"],
                      "Cassini spent thirteen years in the Saturn system before its Grand Finale."),
    "juno-craft": ("spacecraft", ["juno", "jupiter", "solar"], ["jupiter"],
                   "Juno runs on solar power at five astronomical units, which had never been done."),
    "new-horizons-craft": ("spacecraft", ["new horizons", "pluto", "flyby"], ["pluto", "new-horizons"],
                           "The highest-resolution surface detail returned from the Pluto encounter."),
    "parker": ("spacecraft", ["parker", "solar probe", "heat shield"], ["parker-solar-probe", "sol"],
               "Parker Solar Probe before launch — the carbon shield is the pale disc on top."),
    "perseverance": ("spacecraft", ["perseverance", "mars", "rover", "jezero"], ["perseverance", "mars"],
                     "The floor of Jezero Crater, an ancient river delta, from the rover's mast."),
    "curiosity": ("spacecraft", ["curiosity", "mars", "rover", "gale"], ["curiosity", "mars"],
                  "A rover selfie: a mosaic taken by the arm-mounted camera, arm edited out."),
    "ingenuity": ("spacecraft", ["ingenuity", "helicopter", "mars", "flight"], ["perseverance", "mars"],
                  "Ingenuity proved powered flight is possible in air one percent as dense as Earth's."),
    "jwst": ("spacecraft", ["webb", "telescope", "infrared", "mirror"], ["jwst"],
             "A beryllium mirror segment, gold-coated for infrared reflectivity, during assembly."),
    "hubble": ("spacecraft", ["hubble", "telescope", "servicing"], ["hubble"],
               "Hubble captured in the Shuttle payload bay — the only telescope ever repaired in orbit."),
    "iss": ("spacecraft", ["iss", "station", "orbit", "crewed"], ["iss", "earth"],
            "The station, 420 tonnes of it, held up by nothing but 7.66 km/s of horizontal speed."),
    "mars-surface": ("planetary", ["mars", "geology", "sediment"], ["mars", "perseverance"],
                     "Layered sedimentary rock — evidence that water once stood here long enough to deposit it."),
    "moon-surface": ("lunar", ["moon", "apollo", "regolith", "surface"], ["luna"],
                     "The lunar surface at close range: fine, sharp-edged regolith that has never been weathered."),
    "apollo11": ("launch", ["apollo", "moon", "crewed", "history"], ["luna"],
                 "Buzz Aldrin on the Sea of Tranquillity, July 1969."),
    "apollo13": ("launch", ["apollo", "failure", "recovery"], ["luna"],
                 "The Apollo 13 service module after separation, showing the blown-out panel."),
    "artemis1": ("launch", ["artemis", "sls", "night launch"], ["luna"],
                 "Artemis I lifting off — the first flight of the Space Launch System."),
    "saturn-v": ("launch", ["saturn v", "apollo", "heavy lift"], ["luna"],
                 "The Saturn V remains the most powerful launch vehicle to have flown operationally."),
    "sls": ("facility", ["sls", "assembly", "core stage"], [],
            "The SLS core stage during assembly — the scale of a launch vehicle is easiest to read here."),
    "falcon": ("launch", ["falcon 9", "reusable", "dragon"], [],
               "A Falcon 9 on the transporter-erector, before rotating vertical."),
    "kennedy": ("facility", ["kennedy", "vab", "crawler", "pad"], [],
                "Rollout from the Vehicle Assembly Building: a Saturn V moving at 1.6 km/h."),
    "baikonur": ("launch", ["baikonur", "soyuz", "roscosmos"], [],
                 "A Soyuz departing Baikonur, from the pad Gagarin flew from."),
    "kourou": ("launch", ["kourou", "ariane", "esa", "equatorial"], [],
               "Launching from 5°N buys almost all of Earth's rotational velocity."),
    "vandenberg": ("facility", ["vandenberg", "polar", "pacific"], [],
                   "Vandenberg launches south over open ocean, which is what makes polar orbits reachable."),
    "orion-nebula": ("deep_sky", ["orion", "nebula", "star formation", "infrared"], [],
                     "The Orion Nebula in infrared, which sees through the dust that hides its young stars."),
    "nebula": ("deep_sky", ["eagle nebula", "star formation"], [],
               "The Eagle Nebula: columns of cold gas being eroded by the stars they helped form."),
    "carina": ("deep_sky", ["carina", "webb", "star formation"], ["jwst"],
               "The Cosmic Cliffs — one of Webb's first released images, and a demonstration of what infrared buys."),
    "milky-way": ("deep_sky", ["milky way", "galactic centre", "stars"], [],
                  "Toward the galactic centre, where stellar density is thousands of times higher than locally."),
    "galaxy": ("deep_sky", ["galaxy", "spiral"], [],
               "A spiral galaxy seen face-on, its arms traced by regions of active star formation."),
    "star-field": ("deep_sky", ["deep field", "galaxies", "cosmology"], ["hubble"],
                   "A deep field: point the telescope at apparently empty sky for long enough and it fills with galaxies."),
    "earthrise": ("earth_observation", ["earthrise", "apollo", "perspective"], ["earth", "luna"],
                  "Earth rising over the Moon — the image usually credited with starting the environmental movement."),
    "pale-blue-dot": ("earth_observation", ["voyager", "earth", "perspective", "scale"], ["earth", "voyager-1"],
                      "Earth from 6 billion kilometres: a single pixel, caught in a band of scattered sunlight."),
    "aurora": ("earth_observation", ["aurora", "magnetosphere", "iss"], ["earth", "iss"],
               "Aurora is the solar wind meeting Earth's magnetic field, photographed from inside the same orbit."),
}


def build_assets() -> List[AssetRecord]:
    """Every asset in the library."""
    assets = []
    for key, image in IMAGERY.items():
        kind, tags, subjects, description = _CLASSIFICATION.get(
            key, ("planetary", [key], [], image.title)
        )
        assets.append(
            AssetRecord(
                id="asset-{0}".format(key),
                title=image.title,
                kind=kind,
                url=image.url,
                thumbnail_url=image.url.replace("~medium.jpg", "~small.jpg"),
                credit=image.credit,
                license=_NASA_LICENSE,
                alt=image.alt,
                description=description,
                tags=sorted(set(tags + [kind.replace("_", " ")])),
                subject_ids=subjects,
                nasa_id=image.nasa_id,
                date=image.date,
                sources=[BUNDLED],
            )
        )
    return sorted(assets, key=lambda a: (ASSET_KINDS.index(a.kind), a.title))


def assets_by_id() -> Dict[str, AssetRecord]:
    return {asset.id: asset for asset in build_assets()}
