"""
Physical constants used throughout the simulation engine.

All values are in SI units. Sources are cited inline.
Ported from packages/simulation-engine/src/physics/constants.ts — values must
remain identical between the Python and TypeScript implementations.
"""

from __future__ import annotations

import math

# ──────────────────────────────────────────────────────────────
# Fundamental constants
# ──────────────────────────────────────────────────────────────

#: Standard acceleration of gravity. Unit: m/s².
#: Source: NIST CODATA 2018.
G0: float = 9.80665

#: Newtonian gravitational constant. Unit: m³/(kg·s²).
#: Source: NIST CODATA 2018.
G_GRAVITATIONAL: float = 6.67430e-11

#: Universal gas constant. Unit: J/(mol·K).
#: Source: NIST CODATA 2018.
R_UNIVERSAL: float = 8.31446

#: Molar mass of dry air. Unit: kg/mol.
#: Source: US Standard Atmosphere 1976.
M_AIR: float = 0.0289644

#: Ratio of specific heats for dry air. Dimensionless.
#: Source: US Standard Atmosphere 1976.
GAMMA_AIR: float = 1.4

#: Specific gas constant for dry air. R*/M_air. Unit: J/(kg·K).
R_AIR: float = R_UNIVERSAL / M_AIR

# ──────────────────────────────────────────────────────────────
# Earth parameters (WGS-84 nominal)
# ──────────────────────────────────────────────────────────────

#: Mean radius of Earth. Unit: m.
#: Source: WGS-84 nominal value.
R_EARTH: float = 6_371_000.0

#: Mass of Earth. Unit: kg.
#: Source: derived from μ/G.
M_EARTH: float = 5.972e24

#: Standard gravitational parameter of Earth. μ = GM. Unit: m³/s².
#: Source: WGS-84 derived.
MU_EARTH: float = G_GRAVITATIONAL * M_EARTH

# ──────────────────────────────────────────────────────────────
# Atmosphere reference values
# ──────────────────────────────────────────────────────────────

#: Sea-level temperature. Unit: K.
#: Source: US Standard Atmosphere 1976.
T0: float = 288.15

#: Sea-level pressure. Unit: Pa.
#: Source: US Standard Atmosphere 1976.
P0: float = 101_325.0

#: Sea-level density. Unit: kg/m³.
#: Source: US Standard Atmosphere 1976.
RHO0: float = 1.225

#: Speed of sound at sea level. Unit: m/s.
#: Source: derived from √(γ·R_air·T0).
A0: float = math.sqrt(GAMMA_AIR * R_AIR * T0)

# ──────────────────────────────────────────────────────────────
# Conversion factors
# ──────────────────────────────────────────────────────────────

#: Degrees to radians.
DEG_TO_RAD: float = math.pi / 180.0

#: Radians to degrees.
RAD_TO_DEG: float = 180.0 / math.pi

#: Kilometres to metres.
KM_TO_M: float = 1000.0
