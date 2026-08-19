/**
 * US Standard Atmosphere 1976 model.
 *
 * Computes temperature, pressure, density, and speed of sound
 * for a given altitude (0–86 km layer model, exponential decay
 * approximation above 86 km).
 *
 * Source: US Standard Atmosphere 1976, NASA-TM-X-74335
 *
 * Assumptions:
 *   - Hydrostatic equilibrium
 *   - Ideal gas behavior, constant mean molecular weight below 86 km
 *   - No moisture, wind, or local weather effects
 *   - Above 86 km: isothermal exponential decay, NOT the real thermosphere
 *   - Valid for educational simulation — not weather prediction, not re-entry
 *     heating analysis
 *
 * ## Geometric vs geopotential altitude
 *
 * The 1976 standard tabulates its layers against *geopotential* altitude H,
 * which folds the variation of gravity with height into the altitude variable.
 * Real vehicles fly at *geometric* altitude h. The two are related by
 *
 *     H = R·h / (R + h)
 *
 * `atmosphere(h)` takes geometric altitude and converts internally, so it
 * returns the physically correct conditions at the height a vehicle actually
 * occupies. `atmosphereAtGeopotential(H)` is exposed for checking directly
 * against the published USSA-1976 tables.
 *
 * @module physics/atmosphere
 */

import {
  G0,
  R_AIR,
  R_EARTH,
  GAMMA_AIR,
  ATMOSPHERE_LAYERS,
  ATMOSPHERE_MAX_ALTITUDE,
  P0_SEA_LEVEL,
} from './constants.js';

/** Atmospheric conditions at a given altitude. All SI units. */
export interface AtmosphereState {
  /** Temperature. Unit: K */
  readonly temperature_K: number;
  /** Pressure. Unit: Pa */
  readonly pressure_Pa: number;
  /** Density. Unit: kg/m³ */
  readonly density_kgm3: number;
  /** Speed of sound. Unit: m/s */
  readonly speedOfSound_ms: number;
}

/**
 * Convert geometric altitude to geopotential altitude.
 *
 * H = R·h / (R + h)
 *
 * @param geometricAltitude_m - Height above mean sea level. Unit: m.
 * @returns Geopotential altitude. Unit: m.
 */
export function geopotentialAltitude(geometricAltitude_m: number): number {
  return (R_EARTH * geometricAltitude_m) / (R_EARTH + geometricAltitude_m);
}

/**
 * Convert geopotential altitude back to geometric altitude.
 *
 * h = R·H / (R − H)
 *
 * @param geopotentialAltitude_m - Geopotential altitude. Unit: m.
 * @returns Geometric altitude. Unit: m.
 */
export function geometricAltitude(geopotentialAltitude_m: number): number {
  return (R_EARTH * geopotentialAltitude_m) / (R_EARTH - geopotentialAltitude_m);
}

/**
 * Pre-computed base pressures for each atmosphere layer.
 *
 * Computed once at module load by integrating the hydrostatic equation upward
 * from sea level through each layer boundary.
 */
const BASE_PRESSURES: readonly number[] = (() => {
  const pressures: number[] = [P0_SEA_LEVEL];

  for (let i = 0; i < ATMOSPHERE_LAYERS.length - 1; i++) {
    const [baseAlt, baseTemp, lapseRate] = ATMOSPHERE_LAYERS[i]!;
    const [nextAlt] = ATMOSPHERE_LAYERS[i + 1]!;
    pressures.push(
      pressureInLayer(pressures[i]!, baseTemp, lapseRate, nextAlt - baseAlt),
    );
  }

  return Object.freeze(pressures);
})();

/**
 * Pressure after rising `dh` metres through a layer with a linear temperature
 * profile, starting from `basePressure_Pa` at `baseTemp_K`.
 *
 * Isothermal layer:  P = P₀·exp(−g₀·dh / (R·T₀))
 * Gradient layer:    P = P₀·(T/T₀)^(−g₀ / (L·R))
 */
function pressureInLayer(
  basePressure_Pa: number,
  baseTemp_K: number,
  lapseRate_K_per_m: number,
  dh_m: number,
): number {
  if (Math.abs(lapseRate_K_per_m) < 1e-10) {
    return basePressure_Pa * Math.exp((-G0 * dh_m) / (R_AIR * baseTemp_K));
  }
  const tempAtTop = baseTemp_K + lapseRate_K_per_m * dh_m;
  const exponent = -G0 / (lapseRate_K_per_m * R_AIR);
  return basePressure_Pa * Math.pow(tempAtTop / baseTemp_K, exponent);
}

/**
 * Find the atmosphere layer index for a given geopotential altitude.
 *
 * Layers are few (7), so a reverse linear scan is faster than a binary search
 * and allocates nothing. This runs on every integration substep.
 */
function findLayerIndex(geopotentialAltitude_m: number): number {
  for (let i = ATMOSPHERE_LAYERS.length - 1; i >= 0; i--) {
    if (geopotentialAltitude_m >= ATMOSPHERE_LAYERS[i]![0]) {
      return i;
    }
  }
  return 0;
}

/**
 * State at the top of the modelled layer region (86 km geopotential).
 *
 * Precomputed once so the above-86 km branch is continuous with the layer model
 * and needs no recursive call. The scale height is derived from the boundary
 * temperature and the local gravity there, which makes pressure, density, and
 * temperature all continuous across the boundary.
 */
const CEILING = (() => {
  const idx = findLayerIndex(ATMOSPHERE_MAX_ALTITUDE);
  const [baseAlt, baseTemp, lapseRate] = ATMOSPHERE_LAYERS[idx]!;
  const dh = ATMOSPHERE_MAX_ALTITUDE - baseAlt;
  const temperature_K = baseTemp + lapseRate * dh;
  const pressure_Pa = pressureInLayer(BASE_PRESSURES[idx]!, baseTemp, lapseRate, dh);

  // Local gravity at the ceiling, for a physically consistent scale height.
  const h_geometric = geometricAltitude(ATMOSPHERE_MAX_ALTITUDE);
  const gRatio = R_EARTH / (R_EARTH + h_geometric);
  const gCeiling = G0 * gRatio * gRatio;

  return {
    temperature_K,
    pressure_Pa,
    /** Scale height H = R·T / g. Unit: m */
    scaleHeight_m: (R_AIR * temperature_K) / gCeiling,
  };
})();

/**
 * Compute atmospheric conditions at a given **geopotential** altitude.
 *
 * Use this to compare against published USSA-1976 tables, which are indexed by
 * geopotential altitude. For flight simulation use {@link atmosphere} instead.
 *
 * @param geopotentialAltitude_m - Geopotential altitude. Unit: m.
 *   Values below 0 are clamped to 0.
 * @returns Atmospheric state.
 */
export function atmosphereAtGeopotential(geopotentialAltitude_m: number): AtmosphereState {
  const H = Math.max(0, geopotentialAltitude_m);

  if (H >= ATMOSPHERE_MAX_ALTITUDE) {
    // Isothermal exponential decay, continuous with the layer model.
    const temperature_K = CEILING.temperature_K;
    const pressure_Pa =
      CEILING.pressure_Pa *
      Math.exp(-(H - ATMOSPHERE_MAX_ALTITUDE) / CEILING.scaleHeight_m);
    return {
      temperature_K,
      pressure_Pa,
      density_kgm3: pressure_Pa / (R_AIR * temperature_K),
      speedOfSound_ms: Math.sqrt(GAMMA_AIR * R_AIR * temperature_K),
    };
  }

  const layerIdx = findLayerIndex(H);
  const [baseAlt, baseTemp, lapseRate] = ATMOSPHERE_LAYERS[layerIdx]!;
  const dh = H - baseAlt;

  const temperature_K = baseTemp + lapseRate * dh;
  const pressure_Pa = pressureInLayer(BASE_PRESSURES[layerIdx]!, baseTemp, lapseRate, dh);

  return {
    temperature_K,
    pressure_Pa,
    // Ideal gas law
    density_kgm3: pressure_Pa / (R_AIR * temperature_K),
    speedOfSound_ms: Math.sqrt(GAMMA_AIR * R_AIR * temperature_K),
  };
}

/**
 * Compute atmospheric conditions at a given **geometric** altitude.
 *
 * This is the entry point the simulation uses: it takes the height a vehicle
 * actually occupies and converts to geopotential internally.
 *
 * @param altitude_m - Geometric altitude above mean sea level. Unit: m.
 *   Values below 0 are clamped to 0 (sea-level conditions).
 * @returns Atmospheric state (temperature, pressure, density, speed of sound).
 */
export function atmosphere(altitude_m: number): AtmosphereState {
  return atmosphereAtGeopotential(geopotentialAltitude(Math.max(0, altitude_m)));
}

/**
 * Compute Mach number from speed and atmospheric conditions.
 *
 * @param speed_ms - Speed magnitude. Unit: m/s.
 * @param atm - Atmospheric conditions at current altitude.
 * @returns Mach number (dimensionless).
 */
export function machNumber(speed_ms: number, atm: AtmosphereState): number {
  if (atm.speedOfSound_ms <= 0) return 0;
  return Math.abs(speed_ms) / atm.speedOfSound_ms;
}

/**
 * Compute dynamic pressure (q).
 *
 * q = 0.5 × ρ × v²
 *
 * @param speed_ms - Speed magnitude. Unit: m/s.
 * @param density_kgm3 - Air density. Unit: kg/m³.
 * @returns Dynamic pressure. Unit: Pa.
 */
export function dynamicPressure(speed_ms: number, density_kgm3: number): number {
  return 0.5 * density_kgm3 * speed_ms * speed_ms;
}
