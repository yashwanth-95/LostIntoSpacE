import { describe, it, expect } from 'vitest';
import {
  enuBasis,
  enuToEarthCentered,
  altitudeFromEnu,
  downrangeFromEnu,
  enuVectorToEci,
  enuPositionToEci,
  directionFromPitchAzimuth,
  type SiteLocation,
} from '../../src/physics/frames.js';
import { vec3, magnitude, dot } from '../../src/physics/vec3.js';
import { R_EARTH, DEG_TO_RAD } from '../../src/physics/constants.js';

const EQUATOR_PRIME: SiteLocation = {
  latitude_deg: 0,
  longitude_deg: 0,
  altitude_m: 0,
};

/** Satish Dhawan Space Centre, the reference launch site in the RKT spec. */
const SDSC: SiteLocation = {
  latitude_deg: 13.7199,
  longitude_deg: 80.2304,
  altitude_m: 4,
};

describe('enuBasis', () => {
  it('produces an orthonormal right-handed basis', () => {
    for (const site of [EQUATOR_PRIME, SDSC, { latitude_deg: -45, longitude_deg: 170, altitude_m: 0 }]) {
      const b = enuBasis(site);

      expect(magnitude(b.east)).toBeCloseTo(1, 12);
      expect(magnitude(b.north)).toBeCloseTo(1, 12);
      expect(magnitude(b.up)).toBeCloseTo(1, 12);

      expect(dot(b.east, b.north)).toBeCloseTo(0, 12);
      expect(dot(b.north, b.up)).toBeCloseTo(0, 12);
      expect(dot(b.up, b.east)).toBeCloseTo(0, 12);
    }
  });

  it('points up along +X at the equator on the prime meridian', () => {
    const b = enuBasis(EQUATOR_PRIME);
    expect(b.up.x).toBeCloseTo(1, 12);
    expect(b.up.y).toBeCloseTo(0, 12);
    expect(b.up.z).toBeCloseTo(0, 12);
    // North there is the +Z (polar) direction.
    expect(b.north.z).toBeCloseTo(1, 12);
  });

  it('places the site origin at one Earth radius plus its elevation', () => {
    expect(magnitude(enuBasis(SDSC).origin)).toBeCloseTo(R_EARTH + 4, 6);
  });

  it('puts a site at latitude φ at height R·sin φ above the equatorial plane', () => {
    const b = enuBasis({ latitude_deg: 30, longitude_deg: 0, altitude_m: 0 });
    expect(b.origin.z).toBeCloseTo(R_EARTH * Math.sin(30 * DEG_TO_RAD), 6);
  });
});

describe('enuToEarthCentered', () => {
  it('translates the origin to the Earth centre', () => {
    const r = enuToEarthCentered(vec3(0, 0, 0), 0);
    expect(r.z).toBe(R_EARTH);
    expect(magnitude(r)).toBeCloseTo(R_EARTH, 6);
  });

  it('includes the site elevation', () => {
    expect(enuToEarthCentered(vec3(0, 0, 0), 4).z).toBe(R_EARTH + 4);
  });
});

describe('altitudeFromEnu', () => {
  it('is zero at the launch site', () => {
    expect(altitudeFromEnu(vec3(0, 0, 0), 0)).toBeCloseTo(0, 6);
  });

  it('equals the ENU z component directly above the pad', () => {
    expect(altitudeFromEnu(vec3(0, 0, 10_000), 0)).toBeCloseTo(10_000, 6);
  });

  it('accounts for Earth curvature downrange', () => {
    // 100 km downrange at ENU z = 0 is genuinely ~785 m above the sphere,
    // because the surface curves away underneath.
    const alt = altitudeFromEnu(vec3(100_000, 0, 0), 0);
    expect(alt).toBeGreaterThan(700);
    expect(alt).toBeLessThan(900);
  });
});

describe('downrangeFromEnu', () => {
  it('is zero at the launch site', () => {
    expect(downrangeFromEnu(vec3(0, 0, 0), 0)).toBeCloseTo(0, 6);
  });

  it('is zero straight up', () => {
    expect(downrangeFromEnu(vec3(0, 0, 100_000), 0)).toBeCloseTo(0, 6);
  });

  it('approximates the horizontal distance for short ranges', () => {
    // Over 10 km the arc and the chord agree to well under a metre.
    expect(downrangeFromEnu(vec3(10_000, 0, 0), 0)).toBeCloseTo(10_000, 0);
  });

  it('is direction-agnostic', () => {
    const east = downrangeFromEnu(vec3(50_000, 0, 0), 0);
    const north = downrangeFromEnu(vec3(0, 50_000, 0), 0);
    expect(east).toBeCloseTo(north, 6);
  });

  it('grows monotonically with horizontal distance', () => {
    let prev = -1;
    for (let d = 0; d <= 2_000_000; d += 100_000) {
      const range = downrangeFromEnu(vec3(d, 0, 0), 0);
      expect(range).toBeGreaterThan(prev);
      prev = range;
    }
  });
});

describe('ENU → ECI conversion', () => {
  it('preserves vector length', () => {
    const basis = enuBasis(SDSC);
    const v = vec3(120, -340, 900);
    expect(magnitude(enuVectorToEci(v, basis))).toBeCloseTo(magnitude(v), 9);
  });

  it('maps the launch site itself onto its own position vector', () => {
    const basis = enuBasis(SDSC);
    const eci = enuPositionToEci(vec3(0, 0, 0), basis);
    expect(eci.x).toBeCloseTo(basis.origin.x, 6);
    expect(eci.y).toBeCloseTo(basis.origin.y, 6);
    expect(eci.z).toBeCloseTo(basis.origin.z, 6);
  });

  it('preserves altitude through the rotation', () => {
    const basis = enuBasis(SDSC);
    const enu = vec3(200_000, 150_000, 300_000);
    const eci = enuPositionToEci(enu, basis);
    expect(magnitude(eci) - R_EARTH).toBeCloseTo(
      altitudeFromEnu(enu, SDSC.altitude_m),
      3,
    );
  });

  it('sends a due-east velocity at the equator into the +Y direction', () => {
    const basis = enuBasis(EQUATOR_PRIME);
    const eci = enuVectorToEci(vec3(7800, 0, 0), basis);
    expect(eci.x).toBeCloseTo(0, 6);
    expect(eci.y).toBeCloseTo(7800, 6);
    expect(eci.z).toBeCloseTo(0, 6);
  });
});

describe('directionFromPitchAzimuth', () => {
  it('points straight up at 90° pitch', () => {
    const d = directionFromPitchAzimuth(Math.PI / 2, 0);
    expect(d.z).toBeCloseTo(1, 12);
    expect(d.x).toBeCloseTo(0, 12);
    expect(d.y).toBeCloseTo(0, 12);
  });

  it('points due east at 0° pitch and 90° azimuth', () => {
    const d = directionFromPitchAzimuth(0, Math.PI / 2);
    expect(d.x).toBeCloseTo(1, 12);
    expect(d.y).toBeCloseTo(0, 12);
    expect(d.z).toBeCloseTo(0, 12);
  });

  it('points due north at 0° pitch and 0° azimuth', () => {
    const d = directionFromPitchAzimuth(0, 0);
    expect(d.y).toBeCloseTo(1, 12);
  });

  it('always returns a unit vector', () => {
    for (let pitch = -90; pitch <= 90; pitch += 15) {
      for (let az = 0; az < 360; az += 45) {
        const d = directionFromPitchAzimuth(pitch * DEG_TO_RAD, az * DEG_TO_RAD);
        expect(magnitude(d)).toBeCloseTo(1, 12);
      }
    }
  });
});
