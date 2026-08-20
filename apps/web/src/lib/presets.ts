/**
 * Starting designs.
 *
 * A blank canvas is the wrong first experience for a rocket builder: someone
 * who has never seen a staging diagram cannot tell whether their problem is a
 * missing decoupler or an under-sized engine. These give a working baseline to
 * modify — including one that is deliberately broken, because watching a rocket
 * fail for a reason you can read is the fastest way to learn what
 * thrust-to-weight means.
 *
 * Built from the engine's own stock catalogue, so every number comes from the
 * component definitions rather than being made up here.
 */

import {
  addComponent,
  addStage,
  createRocket,
} from '@lostintospace/simulation-engine/core/rocket-design';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import type { RocketDesign } from '@lostintospace/simulation-engine/core/component-types';

/** One registry shared by every preset — the definitions are immutable. */
const registry = createStockRegistry();

export interface Preset {
  id: string;
  name: string;
  summary: string;
  /** What this design is for, shown on the card. */
  teaches: string;
  difficulty: 'starter' | 'intermediate' | 'advanced';
  build: () => RocketDesign;
}

/** Apply a list of component ids to a stage, in order. */
function stack(design: RocketDesign, stageIndex: number, ids: string[]): RocketDesign {
  return ids.reduce((current, id) => addComponent(current, registry, id, stageIndex), design);
}

function soundingRocket(): RocketDesign {
  let design = createRocket(
    'Sounding Rocket',
    'A single solid stage. Goes straight up, comes straight back down.',
  );
  design = addStage(design, 'Solid Stage');
  return stack(design, 0, [
    'nose_s_conical',
    'body_s_short',
    'avionics_basic',
    'payload_instrument',
    'engine_s_solid',
    'fin_s_standard',
    'fin_s_standard',
    'fin_s_standard',
  ]);
}

function twoStageLauncher(): RocketDesign {
  let design = createRocket(
    'Orbital Launcher',
    'Two liquid stages. Enough delta-v to reach low Earth orbit if flown well.',
  );
  design = addStage(design, 'First Stage');
  design = addStage(design, 'Second Stage');

  design = stack(design, 0, [
    'engine_m_booster',
    'engine_m_booster',
    'tank_m_fuel',
    'tank_m_ox',
    'fin_m_grid',
    'fin_m_grid',
    'decoupler_m',
  ]);

  return stack(design, 1, [
    'engine_m_vacuum',
    'tank_m_upper_fuel',
    'tank_m_upper_ox',
    'guidance_inertial',
    'body_m_interstage',
    'payload_smallsat',
    'nose_m_fairing',
  ]);
}

function underpowered(): RocketDesign {
  let design = createRocket(
    'Too Heavy To Fly',
    'A heavy upper stage on a small engine. This one will not leave the pad — on purpose.',
  );
  design = addStage(design, 'Undersized Stage');
  return stack(design, 0, [
    'nose_m_fairing',
    'body_s_long',
    'tank_m_fuel',
    'tank_m_ox',
    'payload_smallsat',
    'avionics_basic',
    // A small liquid engine under a medium-class stack: TWR well below 1.
    'engine_s_liquid',
    'fin_s_standard',
    'fin_s_standard',
  ]);
}

export const PRESETS: readonly Preset[] = [
  {
    id: 'sounding',
    name: 'Sounding Rocket',
    summary: 'One solid stage, fins, a small instrument payload.',
    teaches: 'Vertical flight, max-Q, and why apogee is not orbit.',
    difficulty: 'starter',
    build: soundingRocket,
  },
  {
    id: 'orbital',
    name: 'Orbital Launcher',
    summary: 'Two liquid stages, grid fins, a smallsat under a fairing.',
    teaches: 'Staging, the pitch program, and orbital insertion.',
    difficulty: 'intermediate',
    build: twoStageLauncher,
  },
  {
    id: 'underpowered',
    name: 'Too Heavy To Fly',
    summary: 'A deliberately broken design: not enough thrust for its mass.',
    teaches: 'Thrust-to-weight, and how the simulation reports a failure.',
    difficulty: 'starter',
    build: underpowered,
  },
] as const;

export function buildPreset(id: string): RocketDesign | null {
  const preset = PRESETS.find((p) => p.id === id);
  return preset ? preset.build() : null;
}
