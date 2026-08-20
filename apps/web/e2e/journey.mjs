/**
 * End-to-end prototype journey.
 *
 * Drives the complete product loop the brief specifies, through the same HTTP
 * endpoints the browser calls and through the same TypeScript builder the UI
 * uses — so a break in either the engine seam or the camelCase/snake_case
 * bridge fails here.
 *
 *   Rocket Lab (catalogue) -> Builder (design + analysis) -> Launch (config)
 *   -> Python simulation -> telemetry + events -> failure -> AI explanation
 *   -> search -> assistant
 *
 * Run against a live API:
 *
 *   node e2e/journey.mjs                       # expects http://localhost:8000
 *   API=http://host:8000 node e2e/journey.mjs
 *
 * Exits non-zero on the first failed assertion.
 */

import { createStockRegistry } from '../../../packages/simulation-engine/src/core/catalog.ts';
import { addComponent, addStage, createRocket } from '../../../packages/simulation-engine/src/core/rocket-design.ts';
import { analyzeRocket } from '../../../packages/simulation-engine/src/core/builder.ts';
import { vehicleFromAnalysis } from '../../../packages/simulation-engine/src/core/vehicle.ts';

const API = process.env.API ?? 'http://localhost:8000';
const BASE = `${API}/api/v1`;

let passed = 0;
const failures = [];

function check(label, condition, detail = '') {
  if (condition) {
    passed += 1;
    console.log(`  [32m✓[0m ${label}${detail ? ` [90m${detail}[0m` : ''}`);
  } else {
    failures.push(label);
    console.log(`  [31m✗[0m ${label}${detail ? ` [90m${detail}[0m` : ''}`);
  }
}

function step(title) {
  console.log(`\n[36m${title}[0m`);
}

async function get(path) {
  const response = await fetch(`${BASE}${path}`);
  const body = await response.json().catch(() => null);
  return { status: response.status, body };
}

async function post(path, payload) {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => null);
  return { status: response.status, body };
}

/** Mirrors apps/web/src/lib/simConfig.ts — the camelCase -> snake_case bridge. */
function toSimVehicle(vehicle) {
  const finite = (value, fallback) => (Number.isFinite(value) ? value : fallback);
  return {
    name: vehicle.name,
    design_id: vehicle.designId,
    payload_mass_kg: vehicle.payloadMass_kg,
    launch_mass_kg: vehicle.launchMass_kg,
    length_m: vehicle.length_m,
    diameter_m: vehicle.diameter_m,
    reference_area_m2: vehicle.referenceArea_m2,
    drag_coefficient: vehicle.dragCoefficient,
    stability_margin_wet_cal: finite(vehicle.stabilityMarginWet_cal, 0),
    stability_margin_dry_cal: finite(vehicle.stabilityMarginDry_cal, 0),
    max_axial_load_N: finite(vehicle.maxAxialLoad_N, 1e12),
    max_dynamic_pressure_Pa: finite(vehicle.maxDynamicPressure_Pa, 1e9),
    stages: vehicle.stages.map((stage) => ({
      stage_number: stage.stageNumber,
      name: stage.name,
      dry_mass_kg: stage.dryMass_kg,
      propellant_mass_kg: stage.propellantMass_kg,
      thrust_vacuum_N: stage.thrustVacuum_N,
      thrust_sea_level_N: stage.thrustSeaLevel_N,
      isp_vacuum_s: stage.ispVacuum_s,
      isp_sea_level_s: stage.ispSeaLevel_s,
      mass_flow_rate_kgs: stage.massFlowRate_kgs,
      burn_time_s: stage.burnTime_s,
      ignition_delay_s: stage.ignitionDelay_s,
      separation_delay_s: stage.separationDelay_s,
      can_fire: stage.canFire,
    })),
  };
}

function missionConfig(vehicle, { targetKm, type, guidance }) {
  return {
    vehicle: toSimVehicle(vehicle),
    mission: {
      name: 'E2E Flight',
      objective: `Reach ${targetKm} km`,
      target: { type, target_altitude_km: targetKm, inclination_deg: 28.4 },
      launch_site: {
        name: 'Cape Canaveral',
        latitude_deg: 28.396,
        longitude_deg: -80.605,
        altitude_m: 3,
      },
      environment: {
        temperature_K: 288.15,
        pressure_Pa: 101325,
        wind_speed_ms: 0,
        wind_direction_deg: 0,
      },
    },
    settings: { max_time_s: 2000, telemetry_sample_interval_s: 1 },
    guidance: {
      mode: guidance,
      launch_azimuth_deg: 90,
      pitchover_altitude_m: 200,
      pitch_program_end_altitude_m: Math.max(20000, targetKm * 1000 * 0.4),
      final_pitch_deg: 0,
      cutoff_on_target_orbit: type !== 'suborbital',
    },
    failures: { enabled: true, injections: [] },
    termination: { on_impact: true, on_fatal_failure: true, on_mission_complete: true },
  };
}

// ---------------------------------------------------------------------------

console.log(`[1mLostIntoSpacE — prototype journey[0m  (${API})`);

step('0. Server and engines');
{
  const health = await get('/health');
  check('API is live', health.status === 200 && health.body?.data?.state === 'ok');

  const engines = await get('/health/engines');
  const data = engines.body?.data ?? {};
  check('simulation engine reachable', data.simulation?.available === true, data.simulation?.reason ?? '');
  check('search engine reachable', data.search?.available === true, data.search?.reason ?? '');
  check('AI engine reachable', data.ai?.available === true, data.ai?.reason ?? '');
}

step('1. Rocket Lab — component catalogue');
const registry = createStockRegistry();
{
  const components = registry.listAll();
  check('catalogue has components', components.length > 20, `${components.length} parts`);
  check('engines are catalogued', registry.listByCategory('engine').length > 0);
  const engine = registry.listByCategory('engine')[0];
  check('an engine declares thrust and Isp', engine.thrustSeaLevel_N > 0 && engine.isp_vacuum_s > 0);
}

step('2. Builder — assemble and analyse a two-stage launcher');
let vehicle;
{
  let design = createRocket('E2E Launcher', 'Built by the end-to-end journey');
  design = addStage(design, 'First Stage');
  design = addStage(design, 'Second Stage');

  // One booster, not two. Two gives a liftoff TWR above 3, which accelerates
  // the vehicle so hard through dense air that it exceeds its own airframe's
  // 65 kPa dynamic-pressure limit and breaks up at max-Q — the engine is right
  // to destroy it, and real launchers fly 1.2-1.5 for exactly this reason.
  for (const id of ['engine_m_booster', 'tank_m_fuel', 'tank_m_ox', 'fin_m_grid', 'decoupler_m']) {
    design = addComponent(design, registry, id, 0);
  }
  for (const id of ['engine_m_vacuum', 'tank_m_upper_fuel', 'tank_m_upper_ox', 'guidance_inertial', 'payload_smallsat', 'nose_m_fairing']) {
    design = addComponent(design, registry, id, 1);
  }

  const analysis = analyzeRocket(design, registry);
  vehicle = vehicleFromAnalysis(analysis, design);

  check('design has two stages', analysis.stages.length === 2);
  check('launch mass is computed', analysis.totalWetMass_kg > 1000, `${(analysis.totalWetMass_kg / 1000).toFixed(1)} t`);
  check('liftoff TWR is above 1', analysis.liftoffTWR > 1, `TWR ${analysis.liftoffTWR.toFixed(2)}`);
  check('delta-v budget is computed', analysis.totalDeltaV_ms > 5000, `${analysis.totalDeltaV_ms.toFixed(0)} m/s`);
  check('static stability is computed', Number.isFinite(analysis.stabilityWet.stabilityMargin_cal));
}

step('3. Launch — run the Python simulation over HTTP');
let orbitalResult;
{
  const limits = await get('/simulations/limits');
  check('limits are published', limits.status === 200 && limits.body?.data?.max_time_s > 0);

  const config = missionConfig(vehicle, { targetKm: 200, type: 'leo', guidance: 'pitch_program' });
  const run = await post('/simulations/run', { config });

  check('simulation runs without a token (guest mode)', run.status === 200, `HTTP ${run.status}`);
  orbitalResult = run.body?.data;
  check('the engine identifies itself', run.body?.meta?.engine?.includes('python'), run.body?.meta?.engine ?? '');
  check('compute time recorded', (run.body?.meta?.compute_time_s ?? 0) > 0, `${run.body?.meta?.compute_time_s}s`);
}

step('4. Telemetry and mission events');
{
  const telemetry = orbitalResult?.telemetry ?? [];
  const events = orbitalResult?.events ?? [];

  check('telemetry was produced', telemetry.length > 50, `${telemetry.length} samples`);
  check('events were produced', events.length > 5, `${events.length} events`);
  check('telemetry is ordered in time', telemetry.every((p, i) => i === 0 || p.t >= telemetry[i - 1].t));

  const sample = telemetry[Math.floor(telemetry.length / 2)];
  check('altitude is reported', typeof sample.altitude_m === 'number');
  check('drag is non-zero somewhere in the atmosphere', telemetry.some((p) => p.drag_N > 0));
  check('mass decreases as propellant burns', telemetry[0].mass_kg > telemetry[telemetry.length - 1].mass_kg);
  check('dynamic pressure peaks in flight', orbitalResult.summary.max_dynamic_pressure_Pa > 1000,
    `max-Q ${(orbitalResult.summary.max_dynamic_pressure_Pa / 1000).toFixed(1)} kPa`);

  const types = new Set(events.map((e) => e.type));
  check('ignition event emitted', types.has('STAGE_IGNITION'));
  check('liftoff state reached', types.has('STATE_LIFTOFF'));
  check('stage separation occurred', types.has('STAGE_SEPARATED'), `${orbitalResult.summary.stages_separated} separated`);
}

step('5. Mission outcome — orbit achieved');
{
  check('the vehicle reached orbit', orbitalResult.telemetry.some((p) => p.in_orbit),
    `apogee ${(orbitalResult.summary.max_altitude_m / 1000).toFixed(0)} km`);
  check('outcome is success', orbitalResult.outcome === 'success', orbitalResult.outcome);
  check('orbital elements are reported', orbitalResult.telemetry.some((p) => p.semi_major_axis_m > 6_371_000));
  check('loss budget is accounted for', orbitalResult.summary.gravity_loss_ms > 0 && orbitalResult.summary.drag_loss_ms > 0,
    `gravity ${orbitalResult.summary.gravity_loss_ms.toFixed(0)} m/s, drag ${orbitalResult.summary.drag_loss_ms.toFixed(0)} m/s`);
}

step('6. Failure path — an underpowered vehicle');
let failedResult;
{
  const config = missionConfig(vehicle, { targetKm: 200, type: 'leo', guidance: 'pitch_program' });
  for (const stage of config.vehicle.stages) {
    stage.thrust_vacuum_N = 1000;
    stage.thrust_sea_level_N = 1000;
  }

  const run = await post('/simulations/run', { config });
  failedResult = run.body?.data;

  check('the flight fails', failedResult?.outcome === 'failure', failedResult?.outcome);
  check('a structured failure is reported', (failedResult?.failures?.length ?? 0) > 0);

  const failure = failedResult?.failures?.[0];
  check('the failure is insufficient thrust', failure?.mode_id === 'INSUFFICIENT_THRUST', failure?.mode_id ?? '');
  check('it carries machine-readable fields', typeof failure?.measured_value === 'number' && !!failure?.unit);
  check('it carries an explanation', (failure?.educational_explanation?.length ?? 0) > 40);
  check('it carries a recommended fix', (failure?.recommended_fix?.length ?? 0) > 10);
}

step('7. AI — explain the failure');
{
  const analysis = await post('/ai/explain-failure', {
    simulation_result: failedResult,
    vehicle_description: 'Two-stage launcher with under-sized engines',
  });

  check('the analysis is produced', analysis.status === 200, `HTTP ${analysis.status}`);
  const data = analysis.body?.data;
  check('it summarises the failure', (data?.summary?.length ?? 0) > 20);
  check('it identifies a likely cause', !!data?.likely_cause);
  check('it reads observations off the run', (data?.observations?.length ?? 0) > 0, `${data?.observations?.length} observations`);
  check('it names affected subsystems', (data?.affected_subsystems?.length ?? 0) > 0, (data?.affected_subsystems ?? []).join(', '));
  check('it states the simulation limitations', (data?.simulation_limitations?.length ?? 0) > 0,
    `${data?.simulation_limitations?.length} stated`);
  check('it cites sources', (data?.sources?.length ?? 0) > 0, `${data?.sources?.length} sources`);
  check('it suggests a mitigation', (data?.mitigations?.length ?? 0) > 0);
}

step('8. Search');
{
  const results = await get('/search?q=why%20do%20rockets%20have%20stages&limit=5');
  check('search responds', results.status === 200);
  const items = results.body?.data?.results ?? [];
  check('results are returned', items.length > 0, `${items.length} hits`);
  check('results are ranked', items.every((r, i) => i === 0 || r.score <= items[i - 1].score));
  check('results carry provenance', items.every((r) => (r.provenance?.sources?.length ?? 0) > 0));

  const missions = await get('/search?q=apollo%20moon%20landing&entity_type=MISSION&limit=5');
  const missionHits = missions.body?.data?.results ?? [];
  check('entity filtering works', missionHits.length > 0 && missionHits.every((r) => r.entity_type === 'MISSION'));
}

step('9. Assistant');
{
  const provider = await get('/ai/provider');
  check('the configured provider is published', provider.status === 200 && !!provider.body?.data?.selected_provider,
    provider.body?.data?.selected_provider ?? '');

  const answer = await post('/ai/ask', { question: 'What is specific impulse and why does it matter?' });
  check('the assistant answers', answer.status === 200);
  check('the answer is grounded in sources', (answer.body?.data?.sources?.length ?? 0) > 0,
    `${answer.body?.data?.sources?.length} sources`);
  check('a confidence level is reported', !!answer.body?.data?.confidence, answer.body?.data?.confidence ?? '');
}

step('10. The shipped presets actually do what their cards claim');
{
  // Added after a browser run found the Orbital Launcher preset — advertised as
  // reaching low Earth orbit — breaking up at max-Q, because it carried two
  // boosters and lifted off at TWR 3.2. This journey built its own rocket and
  // so never exercised the presets a user actually clicks. Now it does.
  const { PRESETS } = await import('../src/lib/presets.ts');
  const { analyzeRocket } = await import('../../../packages/simulation-engine/src/core/builder.ts');
  const { vehicleFromAnalysis } = await import('../../../packages/simulation-engine/src/core/vehicle.ts');

  const expectations = {
    sounding: { targetKm: 30, type: 'suborbital', guidance: 'vertical', reachesOrbit: false },
    orbital: { targetKm: 200, type: 'leo', guidance: 'pitch_program', reachesOrbit: true },
    underpowered: { targetKm: 200, type: 'leo', guidance: 'pitch_program', reachesOrbit: false },
  };

  for (const preset of PRESETS) {
    const expectation = expectations[preset.id];
    const design = preset.build();
    const analysis = analyzeRocket(design, registry);
    const presetVehicle = vehicleFromAnalysis(analysis, design);

    const run = await post('/simulations/run', {
      config: missionConfig(presetVehicle, expectation),
    });
    const flight = run.body?.data;
    const failures = (flight?.failures ?? []).map((f) => f.mode_id).join(', ') || 'none';

    if (expectation.reachesOrbit) {
      check(
        `preset "${preset.name}" reaches orbit as advertised`,
        flight?.telemetry?.some((p) => p.in_orbit) === true,
        `TWR ${analysis.liftoffTWR.toFixed(2)}, apogee ${(
          (flight?.summary?.max_altitude_m ?? 0) / 1000
        ).toFixed(0)} km, failures: ${failures}`,
      );
    } else {
      check(
        `preset "${preset.name}" flies without an unintended structural failure`,
        !(flight?.failures ?? []).some((f) => f.mode_id === 'MAX_Q_EXCEEDED'),
        `TWR ${analysis.liftoffTWR.toFixed(2)}, apogee ${(
          (flight?.summary?.max_altitude_m ?? 0) / 1000
        ).toFixed(1)} km, failures: ${failures}`,
      );
    }

    // A preset that a user is invited to fly should not be flagged by the very
    // pre-flight advice the Launch page gives, unless being broken is its point.
    if (preset.id !== 'underpowered') {
      check(
        `preset "${preset.name}" passes the liftoff-TWR advisory`,
        analysis.liftoffTWR >= 1 && analysis.liftoffTWR <= 2.5,
        `TWR ${analysis.liftoffTWR.toFixed(2)}`,
      );
    }
  }
}

step('11. Guest-mode reachability of the public surface');
{
  for (const [label, path] of [
    ['simulation limits', '/simulations/limits'],
    ['lessons', '/lessons'],
    ['space objects', '/space-objects'],
  ]) {
    const response = await get(path);
    // 200 = served; 503 = the database is not configured, which is a known and
    // documented blocker rather than a broken endpoint.
    check(`${label} reachable without a token`, response.status === 200 || response.status === 503,
      `HTTP ${response.status}`);
  }
}

// ---------------------------------------------------------------------------

console.log(`\n[1m${passed} passed, ${failures.length} failed[0m`);
if (failures.length > 0) {
  console.log('\nFailed:');
  for (const failure of failures) console.log(`  - ${failure}`);
  process.exit(1);
}
