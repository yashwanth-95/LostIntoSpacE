"""Real launch sites.

Latitude is the field that does the work. It fixes the lowest inclination
reachable without a plane change — you cannot launch into an orbit whose
inclination is below your launch latitude, not without spending delta-v you
almost certainly do not have — and it sets how much of Earth's 465 m/s
equatorial rotation an eastward launch inherits, by the cosine of latitude.

That is why Kourou at 5.2°N is worth building a spaceport in a rainforest for,
and why a polar mission flies from Vandenberg rather than from Florida.

Azimuth ranges are the other operational constraint: a site cannot fly over
populated land, so its usable azimuths — and therefore its reachable
inclinations — are narrower than geometry alone would allow.
"""

import math
from typing import Dict, List

from ._helpers import BUNDLED, prop
from .models import LaunchSiteRecord

__all__ = ["build_launch_sites", "launch_sites_by_id", "LAUNCH_SITE_IDS"]

#: Earth's equatorial rotation speed. Unit: m/s.
EQUATORIAL_ROTATION_MS = 465.1


def rotation_bonus_ms(latitude_deg: float) -> float:
    """Eastward velocity a launch inherits from Earth's rotation at this latitude.

    v = v_equator · cos(latitude). Due east is the only azimuth that collects all
    of it; a polar launch collects none.
    """
    return EQUATORIAL_ROTATION_MS * math.cos(math.radians(latitude_deg))


def _site(**kwargs) -> LaunchSiteRecord:
    latitude = kwargs["latitude_deg"]
    kwargs.setdefault("min_inclination_deg", round(abs(latitude), 3))
    kwargs.setdefault("earth_rotation_bonus_ms", round(rotation_bonus_ms(latitude), 1))
    kwargs.setdefault("sources", [BUNDLED])
    return LaunchSiteRecord(**kwargs)


def build_launch_sites() -> List[LaunchSiteRecord]:
    return [
        _site(
            id="ksc-lc39a",
            name="Kennedy Space Center, Launch Complex 39A",
            short_name="Kennedy LC-39A",
            country="United States",
            operator="NASA / SpaceX",
            latitude_deg=28.6084,
            longitude_deg=-80.6043,
            elevation_m=3.0,
            pads=["LC-39A", "LC-39B"],
            azimuth_range_deg=[35.0, 120.0],
            typical_orbits=["LEO", "ISS (51.6°)", "GTO", "Lunar injection"],
            vehicles=["Saturn V", "Space Shuttle", "Falcon 9", "Falcon Heavy", "SLS"],
            established_year=1962,
            notes=(
                "Every Apollo lunar launch flew from LC-39A. The Atlantic downrange corridor "
                "means debris falls over water, but the azimuth is limited to the north-east "
                "to south-east by the Carolinas and the Caribbean."
            ),
        ),
        _site(
            id="ccsfs-slc40",
            name="Cape Canaveral Space Force Station, Space Launch Complex 40",
            short_name="Cape Canaveral SLC-40",
            country="United States",
            operator="United States Space Force / SpaceX",
            latitude_deg=28.5619,
            longitude_deg=-80.5772,
            elevation_m=3.0,
            pads=["SLC-40", "SLC-41", "SLC-37"],
            azimuth_range_deg=[35.0, 120.0],
            typical_orbits=["LEO", "GTO", "Interplanetary"],
            vehicles=["Falcon 9", "Atlas V", "Vulcan", "Delta IV"],
            established_year=1949,
            notes="The busiest orbital launch site in the world by cadence.",
        ),
        _site(
            id="vandenberg-slc4e",
            name="Vandenberg Space Force Base, Space Launch Complex 4E",
            short_name="Vandenberg SLC-4E",
            country="United States",
            operator="United States Space Force / SpaceX",
            latitude_deg=34.6321,
            longitude_deg=-120.6106,
            elevation_m=100.0,
            pads=["SLC-4E", "SLC-6", "SLC-2W"],
            azimuth_range_deg=[158.0, 201.0],
            typical_orbits=["Polar", "Sun-synchronous", "Retrograde"],
            vehicles=["Falcon 9", "Delta II", "Minotaur", "Firefly Alpha"],
            established_year=1958,
            notes=(
                "Launches south over open Pacific, which is what makes polar and "
                "Sun-synchronous orbits possible from United States soil. A southward launch "
                "gets no help from Earth's rotation — and a retrograde one pays for it."
            ),
        ),
        _site(
            id="baikonur-site1",
            name="Baikonur Cosmodrome, Site 1/5",
            short_name="Baikonur Site 1",
            country="Kazakhstan",
            operator="Roscosmos",
            latitude_deg=45.9650,
            longitude_deg=63.3050,
            elevation_m=90.0,
            pads=["Site 1/5 (Gagarin's Start)", "Site 31/6", "Site 81", "Site 200"],
            azimuth_range_deg=[34.0, 99.0],
            typical_orbits=["LEO", "ISS (51.6°)", "GTO", "GEO"],
            vehicles=["Soyuz", "Proton", "R-7"],
            established_year=1955,
            notes=(
                "Sputnik and Gagarin both flew from Site 1/5. Its 45.96°N latitude is why the "
                "International Space Station is inclined 51.6° — the station had to be reachable "
                "from here."
            ),
        ),
        _site(
            id="kourou-ela3",
            name="Guiana Space Centre, Ensemble de Lancement Ariane 3",
            short_name="Kourou ELA-3",
            country="French Guiana",
            operator="ESA / CNES / Arianespace",
            latitude_deg=5.2390,
            longitude_deg=-52.7680,
            elevation_m=12.0,
            pads=["ELA-3", "ELA-4", "ZLS (Soyuz)", "ZLV (Vega)"],
            azimuth_range_deg=[-10.5, 93.5],
            typical_orbits=["GTO", "GEO", "Sun-synchronous", "L2 transfer"],
            vehicles=["Ariane 5", "Ariane 6", "Soyuz-ST", "Vega-C"],
            established_year=1968,
            notes=(
                "At 5.2° from the equator this is the best-placed major spaceport on Earth for "
                "geostationary missions: it collects 463 m/s of the 465 available, and needs "
                "almost no plane change to reach a zero-inclination orbit. Webb launched from here."
            ),
        ),
        _site(
            id="sriharikota-slp",
            name="Satish Dhawan Space Centre, Second Launch Pad",
            short_name="Sriharikota SLP",
            country="India",
            operator="ISRO",
            latitude_deg=13.7199,
            longitude_deg=80.2304,
            elevation_m=12.0,
            pads=["First Launch Pad", "Second Launch Pad"],
            azimuth_range_deg=[100.0, 140.0],
            typical_orbits=["LEO", "Sun-synchronous", "GTO", "Lunar injection"],
            vehicles=["PSLV", "GSLV", "LVM3", "SSLV"],
            established_year=1971,
            notes=(
                "Chandrayaan-3 and Mangalyaan both departed from the Second Launch Pad. "
                "Eastward launches must dogleg around Sri Lanka and the Indonesian archipelago, "
                "which costs a little performance."
            ),
        ),
        _site(
            id="tanegashima-lc1",
            name="Tanegashima Space Center, Yoshinobu Launch Complex",
            short_name="Tanegashima LC-1",
            country="Japan",
            operator="JAXA",
            latitude_deg=30.4000,
            longitude_deg=130.9700,
            elevation_m=25.0,
            pads=["Yoshinobu LP1", "Yoshinobu LP2"],
            azimuth_range_deg=[80.0, 120.0],
            typical_orbits=["LEO", "GTO", "ISS resupply"],
            vehicles=["H-IIA", "H-IIB", "H3"],
            established_year=1969,
            notes=(
                "Often described as the most beautiful launch site in the world. Historically "
                "constrained to two short launch windows a year by fishing-industry agreements."
            ),
        ),
        _site(
            id="wenchang-lc101",
            name="Wenchang Space Launch Site, LC-101",
            short_name="Wenchang LC-101",
            country="China",
            operator="CNSA",
            latitude_deg=19.6144,
            longitude_deg=110.9510,
            elevation_m=10.0,
            pads=["LC-101", "LC-201"],
            azimuth_range_deg=[80.0, 120.0],
            typical_orbits=["LEO", "GTO", "Lunar injection", "Space station"],
            vehicles=["Long March 5", "Long March 7", "Long March 8"],
            established_year=2014,
            notes=(
                "China's lowest-latitude site, built on Hainan island so that spent stages fall "
                "into the sea rather than inland — a problem the older inland sites still have."
            ),
        ),
        _site(
            id="plesetsk-site43",
            name="Plesetsk Cosmodrome, Site 43",
            short_name="Plesetsk Site 43",
            country="Russia",
            operator="Russian Aerospace Forces",
            latitude_deg=62.9271,
            longitude_deg=40.5777,
            elevation_m=140.0,
            pads=["Site 43/3", "Site 43/4", "Site 133"],
            azimuth_range_deg=[0.0, 90.0],
            typical_orbits=["Polar", "Molniya", "Sun-synchronous"],
            vehicles=["Soyuz-2", "Angara", "Rockot"],
            established_year=1957,
            notes=(
                "At 62.9°N this is the highest-latitude major spaceport, and the natural home "
                "for Molniya orbits, whose 63.4° inclination it reaches with no plane change at all."
            ),
        ),
        _site(
            id="starbase-orbital",
            name="Starbase, Orbital Launch Pad A",
            short_name="Starbase OLP-A",
            country="United States",
            operator="SpaceX",
            latitude_deg=25.9970,
            longitude_deg=-97.1550,
            elevation_m=5.0,
            pads=["OLP-A", "OLP-B"],
            azimuth_range_deg=[80.0, 120.0],
            typical_orbits=["Suborbital test", "LEO"],
            vehicles=["Starship / Super Heavy"],
            established_year=2019,
            notes=(
                "The lowest-latitude launch site in the continental United States, and the only "
                "one currently flying a fully reusable super-heavy vehicle."
            ),
        ),
    ]


LAUNCH_SITE_IDS = [
    "ksc-lc39a", "ccsfs-slc40", "vandenberg-slc4e", "baikonur-site1", "kourou-ela3",
    "sriharikota-slp", "tanegashima-lc1", "wenchang-lc101", "plesetsk-site43",
    "starbase-orbital",
]


def launch_sites_by_id() -> Dict[str, LaunchSiteRecord]:
    return {site.id: site for site in build_launch_sites()}
