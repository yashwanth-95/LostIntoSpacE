/**
 * Physical constants used throughout the simulation engine.
 *
 * All values are in SI units.
 * Sources are cited inline. Do not change these without updating the source citation.
 *
 * @module physics/constants
 */

/**
 * Standard gravitational acceleration at sea level.
 * Source: NIST CODATA 2018
 * Unit: m/s²
 */
export const G0 = 9.80665;

/**
 * Mean radius of Earth.
 * Source: WGS-84 mean radius = (2a + b) / 3
 * Unit: m
 */
export const R_EARTH = 6_371_000;

/**
 * Specific gas constant for dry air.
 * Source: US Standard Atmosphere 1976, Table 2
 * Unit: J/(kg·K)
 */
export const R_AIR = 287.052_87;

/**
 * Standard sea-level temperature.
 * Source: US Standard Atmosphere 1976
 * Unit: K
 */
export const T0_SEA_LEVEL = 288.15;

/**
 * Standard sea-level pressure.
 * Source: US Standard Atmosphere 1976
 * Unit: Pa
 */
export const P0_SEA_LEVEL = 101_325;

/**
 * Standard sea-level density.
 * Derived: P0 / (R_AIR * T0)
 * Unit: kg/m³
 */
export const RHO0_SEA_LEVEL = P0_SEA_LEVEL / (R_AIR * T0_SEA_LEVEL);

/**
 * Ratio of specific heats for air (γ = cp/cv).
 * Source: US Standard Atmosphere 1976
 * Dimensionless
 */
export const GAMMA_AIR = 1.4;

/**
 * Speed of sound at sea level.
 * Derived: sqrt(γ * R_AIR * T0)
 * Unit: m/s
 */
export const A0_SEA_LEVEL = Math.sqrt(GAMMA_AIR * R_AIR * T0_SEA_LEVEL);

/**
 * US Standard Atmosphere 1976 layer definitions.
 * Each layer: [base_altitude_m, base_temperature_K, lapse_rate_K_per_m]
 *
 * Source: US Standard Atmosphere 1976, Table 4
 *
 * Lapse rate is in K/m (NOT K/km) for direct computation.
 * Positive lapse rate = temperature increases with altitude.
 */
export const ATMOSPHERE_LAYERS: ReadonlyArray<
  readonly [baseAltitude_m: number, baseTemp_K: number, lapseRate_K_per_m: number]
> = [
  [0,      288.15,  -0.0065],   // Troposphere
  [11_000, 216.65,   0.0],      // Tropopause
  [20_000, 216.65,   0.001],    // Stratosphere 1
  [32_000, 228.65,   0.0028],   // Stratosphere 2
  [47_000, 270.65,   0.0],      // Stratopause
  [51_000, 270.65,  -0.0028],   // Mesosphere 1
  [71_000, 214.65,  -0.002],    // Mesosphere 2
] as const;

/**
 * Maximum geopotential altitude (m) for which the US Std Atmosphere 1976
 * layer model is valid. Above this, we use exponential decay approximation.
 *
 * The 1976 standard tabulates layers up to 84 852 m geopotential
 * (= 86 000 m geometric). We use the round 86 km figure as the model ceiling
 * because the difference is immaterial at these densities (< 1e-5 kg/m³).
 *
 * Unit: m (geopotential)
 */
export const ATMOSPHERE_MAX_ALTITUDE = 86_000;

/**
 * Standard gravitational parameter of Earth (μ = G·M) used by this engine.
 *
 * Derived as μ = g₀·R² rather than taken from EGM96 (3.986 004 418e14).
 * The derived value is 0.13 % lower, and we accept that in exchange for the
 * engine being *internally consistent*: surface gravity is exactly g₀, so the
 * inverse-square force model, the orbital-element solver, and the reported
 * weight of a vehicle on the pad all agree with each other. An engine that
 * mixed the two would show a rocket weighing slightly less than g₀·m while
 * sitting on the launch pad.
 *
 * Unit: m³/s²
 */
export const MU_EARTH = G0 * R_EARTH * R_EARTH;

/**
 * The EGM96 value of Earth's gravitational parameter, for reference and for
 * documenting the deviation of {@link MU_EARTH}. Not used in computation.
 * Unit: m³/s²
 */
export const MU_EARTH_EGM96 = 3.986_004_418e14;

/**
 * Sidereal rotation period of Earth.
 * Source: IERS.
 * Unit: s
 */
export const EARTH_SIDEREAL_DAY_S = 86_164.0905;

/**
 * Equatorial surface speed due to Earth's rotation.
 * Derived: 2π·R_EARTH / sidereal day.
 * Unit: m/s
 */
export const EARTH_EQUATORIAL_SPEED = (2 * Math.PI * R_EARTH) / EARTH_SIDEREAL_DAY_S;

/**
 * Altitude at which drag is negligible for educational purposes.
 * Above this the atmosphere contributes < 0.01 % of typical vehicle drag.
 * Unit: m
 */
export const KARMAN_LINE = 100_000;

/**
 * Conversion: radians per degree.
 */
export const DEG_TO_RAD = Math.PI / 180;

/**
 * Conversion: degrees per radian.
 */
export const RAD_TO_DEG = 180 / Math.PI;
