import { describe, it, expect } from 'vitest';
import {
  atmosphere,
  atmosphereAtGeopotential,
  geopotentialAltitude,
  geometricAltitude,
  machNumber,
  dynamicPressure,
} from '../../src/physics/atmosphere.js';
import {
  T0_SEA_LEVEL,
  P0_SEA_LEVEL,
  RHO0_SEA_LEVEL,
  A0_SEA_LEVEL,
  ATMOSPHERE_MAX_ALTITUDE,
} from '../../src/physics/constants.js';

describe('geopotential / geometric altitude conversion', () => {
  it('is the identity at sea level', () => {
    expect(geopotentialAltitude(0)).toBe(0);
    expect(geometricAltitude(0)).toBe(0);
  });

  it('reports geopotential altitude below geometric altitude', () => {
    // Gravity weakens with height, so a given geopotential is reached slightly
    // higher up than the naive number suggests.
    expect(geopotentialAltitude(11_000)).toBeLessThan(11_000);
    expect(geopotentialAltitude(11_000)).toBeCloseTo(10_981, 0);
  });

  it('round-trips', () => {
    for (const h of [1_000, 11_000, 20_000, 50_000, 86_000]) {
      expect(geometricAltitude(geopotentialAltitude(h))).toBeCloseTo(h, 6);
    }
  });
});

describe('atmosphereAtGeopotential — USSA-1976 table values', () => {
  // The published tables are indexed by geopotential altitude, so these check
  // the layer model itself against the standard.

  it('matches sea level', () => {
    const sl = atmosphereAtGeopotential(0);
    expect(sl.temperature_K).toBeCloseTo(T0_SEA_LEVEL, 2);
    expect(sl.pressure_Pa).toBeCloseTo(P0_SEA_LEVEL, 0);
    expect(sl.density_kgm3).toBeCloseTo(RHO0_SEA_LEVEL, 3);
    expect(sl.speedOfSound_ms).toBeCloseTo(A0_SEA_LEVEL, 1);
  });

  it('matches the tropopause at 11 km', () => {
    const tp = atmosphereAtGeopotential(11_000);
    expect(tp.temperature_K).toBeCloseTo(216.65, 1);
    expect(tp.pressure_Pa).toBeCloseTo(22_632, -1);
    expect(tp.density_kgm3).toBeCloseTo(0.3639, 2);
  });

  it('matches the stratosphere at 20 km', () => {
    const s = atmosphereAtGeopotential(20_000);
    expect(s.temperature_K).toBeCloseTo(216.65, 1);
    expect(s.pressure_Pa).toBeCloseTo(5474.9, -1);
  });

  it('matches the stratopause at 47 km', () => {
    const s = atmosphereAtGeopotential(47_000);
    expect(s.temperature_K).toBeCloseTo(270.65, 1);
    expect(s.pressure_Pa).toBeCloseTo(110.9, 0);
  });
});

describe('atmosphere — geometric altitude entry point', () => {
  it('agrees with the geopotential form at sea level', () => {
    expect(atmosphere(0).pressure_Pa).toBeCloseTo(P0_SEA_LEVEL, 6);
  });

  it('reports slightly higher pressure than the naive table lookup', () => {
    // Geometric 11 km maps to geopotential ~10.98 km, which is a bit denser.
    const geometric = atmosphere(11_000);
    const naive = atmosphereAtGeopotential(11_000);
    expect(geometric.pressure_Pa).toBeGreaterThan(naive.pressure_Pa);
    // …but only by a fraction of a percent.
    expect(geometric.pressure_Pa / naive.pressure_Pa).toBeLessThan(1.01);
  });

  it('is very low but positive at 50 km', () => {
    const ha = atmosphere(50_000);
    expect(ha.pressure_Pa).toBeLessThan(100);
    expect(ha.pressure_Pa).toBeGreaterThan(0);
    expect(ha.density_kgm3).toBeLessThan(0.01);
    expect(ha.density_kgm3).toBeGreaterThan(0);
  });

  it('clamps negative altitude to sea level', () => {
    const neg = atmosphere(-100);
    const sl = atmosphere(0);
    expect(neg.temperature_K).toBe(sl.temperature_K);
    expect(neg.pressure_Pa).toBe(sl.pressure_Pa);
  });
});

describe('atmosphere — monotonicity', () => {
  it('pressure decreases with altitude from 0 to 200 km', () => {
    let prevPressure = Infinity;
    for (let alt = 0; alt <= 200_000; alt += 2_000) {
      const atm = atmosphere(alt);
      expect(atm.pressure_Pa).toBeLessThan(prevPressure);
      expect(atm.pressure_Pa).toBeGreaterThan(0);
      prevPressure = atm.pressure_Pa;
    }
  });

  it('density decreases with altitude from 0 to 200 km', () => {
    let prevDensity = Infinity;
    for (let alt = 0; alt <= 200_000; alt += 2_000) {
      const atm = atmosphere(alt);
      expect(atm.density_kgm3).toBeLessThan(prevDensity);
      expect(atm.density_kgm3).toBeGreaterThan(0);
      prevDensity = atm.density_kgm3;
    }
  });
});

describe('atmosphere — above the layer model ceiling', () => {
  it('is continuous across the 86 km boundary', () => {
    // Straddle the handover by 1 cm, so any residual difference is a genuine
    // discontinuity rather than the atmosphere's own decay over the gap.
    const below = atmosphereAtGeopotential(ATMOSPHERE_MAX_ALTITUDE - 0.01);
    const above = atmosphereAtGeopotential(ATMOSPHERE_MAX_ALTITUDE + 0.01);

    // The remaining ~4e-6 is the atmosphere's own decay over 2 cm; a real
    // handover discontinuity in this model would show up at the percent level.
    expect(above.temperature_K / below.temperature_K).toBeCloseTo(1, 5);
    expect(above.pressure_Pa / below.pressure_Pa).toBeCloseTo(1, 5);
    expect(above.density_kgm3 / below.density_kgm3).toBeCloseTo(1, 5);
  });

  it('returns finite positive values far above the ceiling', () => {
    const high = atmosphere(300_000);
    expect(high.temperature_K).toBeGreaterThan(0);
    expect(high.pressure_Pa).toBeGreaterThan(0);
    expect(high.density_kgm3).toBeGreaterThan(0);
    expect(high.speedOfSound_ms).toBeGreaterThan(0);
  });

  it('decays exponentially with a consistent scale height', () => {
    // Measured in geopotential, where the decay is exactly exponential —
    // in geometric altitude the conversion makes the steps unequal.
    const a = atmosphereAtGeopotential(100_000);
    const b = atmosphereAtGeopotential(110_000);
    const c = atmosphereAtGeopotential(120_000);
    expect(a.pressure_Pa / b.pressure_Pa).toBeCloseTo(b.pressure_Pa / c.pressure_Pa, 6);
  });
});

describe('machNumber', () => {
  it('returns 1.0 at the speed of sound', () => {
    const atm = atmosphere(0);
    expect(machNumber(atm.speedOfSound_ms, atm)).toBeCloseTo(1.0, 6);
  });

  it('returns ~2.0 at twice the speed of sound', () => {
    const atm = atmosphere(0);
    expect(machNumber(2 * atm.speedOfSound_ms, atm)).toBeCloseTo(2.0, 6);
  });

  it('treats speed as a magnitude', () => {
    const atm = atmosphere(0);
    expect(machNumber(-atm.speedOfSound_ms, atm)).toBeCloseTo(1.0, 6);
  });
});

describe('dynamicPressure', () => {
  it('returns 0.5 · rho · v²', () => {
    const v = 300;
    const rho = 1.225;
    expect(dynamicPressure(v, rho)).toBeCloseTo(0.5 * rho * v * v, 6);
  });

  it('is zero when speed is zero', () => {
    expect(dynamicPressure(0, 1.225)).toBe(0);
  });
});
