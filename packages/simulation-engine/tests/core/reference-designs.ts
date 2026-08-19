/**
 * Reference rocket designs, built from the stock catalogue.
 *
 * These are the fixtures every core and sim test flies. Keeping them in one
 * place means a change to the catalogue shows up as a single, reviewable
 * change in expected behaviour rather than as noise across a dozen test files.
 *
 * All of them are built with explicit timestamps so designs are byte-identical
 * between runs.
 */

import {
  createRocket,
  addStage,
  addComponent,
  configureComponent,
} from '../../src/core/rocket-design.js';
import { createStockRegistry } from '../../src/core/catalog.js';
import type { ComponentRegistry } from '../../src/core/component-registry.js';
import type { RocketDesign } from '../../src/core/component-types.js';

export const FIXED_TIMESTAMP = '2026-01-01T00:00:00.000Z';

/** A registry loaded with the stock catalogue. */
export function stockRegistry(): ComponentRegistry {
  return createStockRegistry();
}

/**
 * A single-stage S-class sounding rocket with a solid motor.
 *
 * Layout, bottom to top: fins, solid motor, body tube, avionics, instrument
 * package, nose cone.
 *
 * The large fin set and the 150 kg instrument package are both there for
 * stability. A solid motor puts almost all of the vehicle's mass at the tail,
 * so the fully-loaded centre of gravity sits far aft; forward mass and fin area
 * are what pull the static margin back above one caliber before burnout.
 *
 * This one reaches roughly 165 km — past the Kármán line — and then **breaks up
 * on the way back down**. That is the correct answer, not a bug: falling
 * ballistically from that height it re-enters at over 1.6 km/s and sees more
 * dynamic pressure on descent than it did on ascent. It is the fixture for the
 * "a vehicle that goes to space needs a way to come back" lesson. For a flight
 * that survives, see {@link recoverableSoundingRocket}.
 */
export function soundingRocket(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Vega-S Sounding Rocket', 'Single-stage solid sounding rocket', {
    id: 'ref-sounding',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'Solid Stage', 0);

  // offset_z is the axial position of each part's aft end, up from the stage base.
  design = addComponent(design, registry, 'fin_s_large', 0, { z: 0 });
  design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
  design = addComponent(design, registry, 'body_s_short', 0, { z: 2.5 });
  design = addComponent(design, registry, 'avionics_basic', 0, { z: 3.5 });
  design = addComponent(design, registry, 'payload_instrument', 0, { z: 3.8 });
  const payloadId = design.components[design.components.length - 1]!.instanceId;
  design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 4.4 });

  // Ballast the instrument bay up to 150 kg — forward mass buys static margin.
  design = configureComponent(design, payloadId, { mass_kg: 150 });

  return design;
}

/**
 * A low-apogee sounding rocket that completes its flight and lands.
 *
 * The same motor as {@link soundingRocket} under a much heavier payload. The
 * extra mass cuts delta-v to around 750 m/s and apogee to roughly 30 km, low
 * enough that the vehicle re-enters slowly and stays inside its airframe
 * limits. This is the reference for a *successful* suborbital profile.
 */
export function recoverableSoundingRocket(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Vega-S Light', 'Low-apogee recoverable sounding rocket', {
    id: 'ref-recoverable',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'Solid Stage', 0);

  design = addComponent(design, registry, 'fin_s_large', 0, { z: 0 });
  design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
  design = addComponent(design, registry, 'body_s_short', 0, { z: 2.5 });
  design = addComponent(design, registry, 'avionics_basic', 0, { z: 3.5 });
  design = addComponent(design, registry, 'parachute_s_main', 0, { z: 3.8 });
  design = addComponent(design, registry, 'payload_smallsat', 0, { z: 4.3 });
  const payloadId = design.components[design.components.length - 1]!.instanceId;
  design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 6.5 });

  design = configureComponent(design, payloadId, { mass_kg: 1_500 });

  return design;
}

/**
 * A single-stage S-class liquid rocket.
 *
 * Layout, bottom to top: fins, liquid engine, oxidizer tank, fuel tank,
 * avionics, instrument package, nose cone.
 */
export function liquidSoundingRocket(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Vega-L Sounding Rocket', 'Single-stage liquid sounding rocket', {
    id: 'ref-liquid-sounding',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'Liquid Stage', 0);

  design = addComponent(design, registry, 'fin_s_standard', 0, { z: 0 });
  design = addComponent(design, registry, 'engine_s_liquid', 0, { z: 0 });
  design = addComponent(design, registry, 'tank_s_ox', 0, { z: 1.1 });
  design = addComponent(design, registry, 'tank_s_fuel', 0, { z: 3.6 });
  design = addComponent(design, registry, 'avionics_basic', 0, { z: 5.6 });
  design = addComponent(design, registry, 'payload_instrument', 0, { z: 5.9 });
  const payloadId = design.components[design.components.length - 1]!.instanceId;
  design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 6.5 });

  // 150 kg of instrument. Besides buying static margin, the extra dry mass caps
  // burnout acceleration: with only 25 kg aboard this vehicle pulls over 20 g in
  // its last seconds, because thrust is constant while mass keeps falling.
  design = configureComponent(design, payloadId, { mass_kg: 150 });

  return design;
}

/**
 * A two-stage M-class orbital launcher.
 *
 * Stage 0: booster engine, oxidizer tank, fuel tank, grid fins, separation ring.
 * Stage 1: vacuum engine, oxidizer tank, fuel tank, guidance, avionics,
 *          satellite, fairing.
 */
export function orbitalLauncher(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Meridian-2 Launcher', 'Two-stage orbital launch vehicle', {
    id: 'ref-orbital',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'First Stage', 0);
  design = addStage(design, 'Second Stage', 4);

  // --- Stage 0: engine, tanks, grid fins low on the body, separation ring on top ---
  design = addComponent(design, registry, 'engine_m_booster', 0, { z: 0 });
  design = addComponent(design, registry, 'tank_m_ox', 0, { z: 3.0 });
  design = addComponent(design, registry, 'tank_m_fuel', 0, { z: 19.0 });
  design = addComponent(design, registry, 'fin_m_grid', 0, { z: 3.2 });
  design = addComponent(design, registry, 'decoupler_m', 0, { z: 31.0 });

  // --- Stage 1: vacuum engine, smaller upper-stage tanks, avionics, payload ---
  design = addComponent(design, registry, 'engine_m_vacuum', 1, { z: 0 });
  design = addComponent(design, registry, 'tank_m_upper_ox', 1, { z: 3.4 });
  design = addComponent(design, registry, 'tank_m_upper_fuel', 1, { z: 10.4 });
  design = addComponent(design, registry, 'guidance_inertial', 1, { z: 15.4 });
  design = addComponent(design, registry, 'avionics_basic', 1, { z: 15.75 });
  design = addComponent(design, registry, 'payload_smallsat', 1, { z: 16.05 });
  design = addComponent(design, registry, 'nose_m_fairing', 1, { z: 18.25 });

  return design;
}

/**
 * A rocket that cannot lift off: an 8 t satellite bolted to a small solid motor.
 *
 * Liftoff thrust-to-weight lands near 0.44, so this is the fixture for the
 * "never left the pad" failure path.
 */
export function underpoweredRocket(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Anchor', 'Deliberately underpowered test article', {
    id: 'ref-underpowered',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'Only Stage', 0);
  design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
  design = addComponent(design, registry, 'body_s_short', 0, { z: 2.5 });
  design = addComponent(design, registry, 'payload_smallsat', 0, { z: 3.5 });
  const payloadId = design.components[design.components.length - 1]!.instanceId;
  design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 5.7 });

  design = configureComponent(design, payloadId, { mass_kg: 8_000 });

  return design;
}

/** A finless rocket, for exercising the stability rules. */
export function finlessRocket(registry: ComponentRegistry): RocketDesign {
  let design = createRocket('Tumbler', 'Finless test article', {
    id: 'ref-finless',
    timestamp: FIXED_TIMESTAMP,
  });

  design = addStage(design, 'Only Stage', 0);
  design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
  design = addComponent(design, registry, 'body_s_long', 0, { z: 2.5 });
  design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 5.5 });

  return design;
}
