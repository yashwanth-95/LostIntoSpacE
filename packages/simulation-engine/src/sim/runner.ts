/**
 * Simulation runner — the flight loop.
 *
 * `Simulation` owns the mutable state of one flight and exposes it through the
 * documented API: `step`, `pause`, `resume`, `reset`, `getTelemetry`,
 * `getEvents`, `getMissionState`. Nothing outside this class mutates a flight.
 *
 * ## The loop, in order
 *
 * 1. **Sequencing** — ignite, cut off, and separate stages whose time has come.
 * 2. **Guidance** — compute the commanded attitude.
 * 3. **Forces** — evaluate thrust, drag, and gravity.
 * 4. **Integrate** — advance position and velocity with RK4.
 * 5. **Mass** — deplete propellant analytically (see `physics/integrator.ts`).
 * 6. **Failures** — run detection rules and scripted injections.
 * 7. **Mission state** — advance the state machine and emit its events.
 * 8. **Telemetry** — sample if the interval elapsed or an event fired.
 * 9. **Termination** — check the stop conditions.
 *
 * ## Determinism
 *
 * No wall-clock reads, no `Math.random()`. A run is a pure function of its
 * config, and `tests/sim/determinism.test.ts` asserts that.
 *
 * @module sim/runner
 */

import { G0, R_EARTH } from '../physics/constants.js';
import type { Vec3 } from '../physics/vec3.js';
import { vec3, magnitude, dot, scale } from '../physics/vec3.js';
import { getIntegrator, type KinematicState } from '../physics/integrator.js';
import { orbitalElements, type OrbitalElements } from '../physics/orbital.js';
import { enuBasis, enuPositionToEci, enuVectorToEci, downrangeFromEnu } from '../physics/frames.js';
import { currentMass, hasRemainingStages } from '../core/vehicle.js';
import type { SimConfig } from './config.js';
import {
  advanceMissionState,
  isTerminalState,
  type MissionState,
  type TransitionContext,
} from './mission-state.js';
import {
  makeEvent,
  makeFailureEvent,
  type FailureDetail,
  type SimEvent,
} from './events.js';
import {
  checkInjections,
  combinedEffects,
  detectFailures,
  failureEventType,
  SeededRandom,
  type FailureEffects,
} from './failures.js';
import {
  computeGuidance,
  angleOfAttack,
  initialCommand,
  localUpVector,
  type GuidanceCommand,
} from './guidance.js';
import { computeAcceleration, computeForces, type ForceInputs } from './forces.js';
import {
  buildTelemetryPoint,
  TelemetrySampler,
  EMPTY_TELEMETRY,
  type TelemetryPoint,
} from './telemetry.js';
import {
  initialStageStates,
  updateStage,
  type FlightPhase,
  type SimulationState,
  type SimStatus,
  type StageState,
  type VehicleState,
} from './state.js';

/**
 * Altitude at which orbital elements start being reported.
 *
 * Below this the two-body solution describes a trajectory that intersects the
 * ground and drag dominates anyway, so the numbers would be noise. The Kármán
 * line is a conventional and defensible place to draw it.
 */
const ORBIT_REPORTING_ALTITUDE_M = 100_000;

/**
 * Altitude below which the vehicle counts as having reached the surface.
 *
 * Not exactly zero: RK4 lands between steps, so a small band avoids a vehicle
 * skipping from +3 m to −40 m without ever registering.
 */
const SURFACE_BAND_M = 0.5;

/** Altitude at which a descending vehicle is treated as re-entering. */
const ENTRY_INTERFACE_M = 100_000;

/** Speed above which entry is aerodynamically significant. Unit: m/s. */
const ENTRY_SPEED_MS = 2_000;

/** The complete result of a finished run. */
export interface SimResult {
  /** Whether the mission met its objective. */
  readonly success: boolean;
  /** Outcome classification. */
  readonly outcome: 'success' | 'partial' | 'failure';
  /** Final mission state. */
  readonly finalState: MissionState;
  /** Why the run ended. */
  readonly terminationReason: string;
  /** The full telemetry series. */
  readonly telemetry: readonly TelemetryPoint[];
  /** Every event, oldest first. */
  readonly events: readonly SimEvent[];
  /** Every failure, oldest first. */
  readonly failures: readonly FailureDetail[];
  /** Aggregate statistics. */
  readonly summary: import('./events.js').SimSummary;
  /** Integration steps taken. */
  readonly totalSteps: number;
  /** Simulated flight time. Unit: s. */
  readonly flightTime_s: number;
  /** The state at the moment the run ended. */
  readonly finalSimState: SimulationState;
}

/** Running peaks, accumulated as the flight proceeds. */
interface RunningPeaks {
  maxAltitude_m: number;
  maxSpeed_ms: number;
  maxAcceleration_g: number;
  maxDynamicPressure_Pa: number;
  maxQAltitude_m: number;
  maxMach: number;
  maxDownrange_m: number;
  apogeeTime_s: number;
  stagesSeparated: number;
  propellantUsed_kg: number;
  gravityLoss_ms: number;
  dragLoss_ms: number;
  velocityGained_ms: number;
}

/**
 * One rocket flight.
 *
 * Construct with a config, then drive it with {@link step} — or hand it to
 * {@link runSimulation} to fly the whole thing at once.
 */
export class Simulation {
  private readonly _config: SimConfig;
  private readonly _rng: SeededRandom;
  private readonly _firedInjections = new Set<string>();
  private readonly _sampler: TelemetrySampler;
  private readonly _siteRadius_m: number;
  private readonly _basis: ReturnType<typeof enuBasis>;
  private readonly _integrate: ReturnType<typeof getIntegrator>;
  private readonly _initialPropellant: readonly number[];

  private _time_s: number;
  private _stepCount = 0;
  private _status: SimStatus = 'ready';
  private _missionState: MissionState = 'PREPARATION';
  private _timeInState_s = 0;
  private _terminationReason: string | null = null;

  private _kinematics: KinematicState;
  private _stages: StageState[];
  private _activeStage = 0;
  private _command: GuidanceCommand;
  private _acceleration: Vec3 = vec3(0, 0, 0);

  private _events: SimEvent[] = [];
  private _failures: FailureDetail[] = [];
  private _effects: FailureEffects = combinedEffects([]);

  private _hasLiftedOff = false;
  private _burnTimeOnPad_s = 0;
  private _payloadDeployed = false;
  private _previousDynamicPressure_Pa = 0;
  private _lastTelemetry: TelemetryPoint = EMPTY_TELEMETRY;
  private _peaks: RunningPeaks;
  private _passedSupersonic = false;
  private _maxQPassed = false;

  /** @param config - The flight to run. */
  constructor(config: SimConfig) {
    this._config = config;
    this._rng = new SeededRandom(config.failures.seed);
    this._sampler = new TelemetrySampler(
      config.settings.telemetrySampleInterval_s,
      -config.settings.countdown_s,
    );
    this._siteRadius_m = R_EARTH + config.mission.launchSite.altitude_m;
    this._basis = enuBasis(config.mission.launchSite);
    this._integrate = getIntegrator(config.settings.integrator);
    this._initialPropellant = config.vehicle.stages.map(s => s.propellantMass_kg);

    this._time_s = -config.settings.countdown_s;
    this._kinematics = { position: vec3(0, 0, 0), velocity: vec3(0, 0, 0) };
    this._stages = initialStageStates(this._initialPropellant);
    this._command = initialCommand(config.guidance);
    this._peaks = freshPeaks();
  }

  // ============================================================
  // Public API
  // ============================================================

  /** The config this simulation was built from. */
  get config(): SimConfig {
    return this._config;
  }

  /** Current run status. */
  get status(): SimStatus {
    return this._status;
  }

  /** Simulated time. Negative during countdown. Unit: s. */
  get time_s(): number {
    return this._time_s;
  }

  /** Whether the run has ended, either way. */
  get isFinished(): boolean {
    return this._status === 'complete' || this._status === 'failed';
  }

  /** The current mission state. */
  getMissionState(): MissionState {
    return this._missionState;
  }

  /** Every telemetry sample recorded so far. */
  getTelemetry(): readonly TelemetryPoint[] {
    return this._sampler.points;
  }

  /** The most recent telemetry sample. */
  getLatestTelemetry(): TelemetryPoint {
    return this._lastTelemetry;
  }

  /** Every event emitted so far. */
  getEvents(): readonly SimEvent[] {
    return this._events;
  }

  /** Every failure so far. */
  getFailures(): readonly FailureDetail[] {
    return this._failures;
  }

  /** A snapshot of the complete state, safe to serialize or hand to a renderer. */
  getState(): SimulationState {
    return {
      time_s: this._time_s,
      stepCount: this._stepCount,
      missionState: this._missionState,
      vehicle: this._vehicleState(),
      telemetry: this._lastTelemetry,
      events: this._events,
      status: this._status,
      orbit: this._orbitalElements(),
      terminationReason: this._terminationReason,
    };
  }

  /** Pause a running simulation. A no-op unless it is running. */
  pause(): void {
    if (this._status === 'running') this._status = 'paused';
  }

  /** Resume a paused simulation. A no-op unless it is paused. */
  resume(): void {
    if (this._status === 'paused') this._status = 'running';
  }

  /** Return to the initial state, discarding all telemetry and events. */
  reset(): void {
    this._time_s = -this._config.settings.countdown_s;
    this._stepCount = 0;
    this._status = 'ready';
    this._missionState = 'PREPARATION';
    this._timeInState_s = 0;
    this._terminationReason = null;

    this._kinematics = { position: vec3(0, 0, 0), velocity: vec3(0, 0, 0) };
    this._stages = initialStageStates(this._initialPropellant);
    this._activeStage = 0;
    this._command = initialCommand(this._config.guidance);
    this._acceleration = vec3(0, 0, 0);

    this._events = [];
    this._failures = [];
    this._effects = combinedEffects([]);
    this._firedInjections.clear();

    this._hasLiftedOff = false;
    this._burnTimeOnPad_s = 0;
    this._payloadDeployed = false;
    this._previousDynamicPressure_Pa = 0;
    this._lastTelemetry = EMPTY_TELEMETRY;
    this._peaks = freshPeaks();
    this._passedSupersonic = false;
    this._maxQPassed = false;

    this._sampler.reset(-this._config.settings.countdown_s);
  }

  /**
   * Advance the simulation by one timestep.
   *
   * The step size comes from the config and depends on whether anything is
   * burning — see `SimSettings.dt_coast_s` for why they differ.
   *
   * @returns The state after the step. Calling `step` on a finished simulation
   *   returns the final state unchanged rather than throwing, so a render loop
   *   can keep calling it harmlessly.
   */
  step(): SimulationState {
    if (this.isFinished || this._status === 'paused') {
      return this.getState();
    }
    this._status = 'running';

    const dt = this._currentTimestep();
    const eventsBefore = this._events.length;

    // 1. Sequencing ---------------------------------------------------------
    const { ignited, separating } = this._sequenceStages(dt);

    // 2. Guidance -----------------------------------------------------------
    this._command = computeGuidance(
      {
        altitude_m: this._altitude(),
        velocity: this._kinematics.velocity,
        localUp: localUpVector(this._kinematics.position, this._siteRadius_m),
        guidanceFailed: this._effects.freezeGuidance,
        lastCommand: this._command,
      },
      this._config.guidance,
    );

    // 3. Forces -------------------------------------------------------------
    const forces = computeForces(this._forceInputs(this._kinematics, 0));

    // 4. Integrate ----------------------------------------------------------
    // Mass is evaluated analytically at each substep time rather than being
    // carried in the state vector — see the module docs on operator splitting.
    const massFlow = this._currentMassFlow();
    const previousSpeed = magnitude(this._kinematics.velocity);

    this._kinematics = this._integrate(
      this._kinematics,
      this._time_s,
      dt,
      (t, position, velocity) =>
        computeAcceleration(
          this._forceInputs({ position, velocity }, t - this._time_s),
        ),
    );

    // 5. Mass ---------------------------------------------------------------
    this._depletePropellant(massFlow * dt);

    this._time_s += dt;
    this._stepCount++;
    this._timeInState_s += dt;
    this._acceleration = forces.acceleration;

    // The pad holds the vehicle down until thrust genuinely exceeds weight.
    this._applyGroundConstraint();

    if (!this._hasLiftedOff) {
      if (this._time_s > 0 && this._heightAboveGround() > SURFACE_BAND_M) {
        this._hasLiftedOff = true;
        this._emit('tower_clear', 'Vehicle cleared the pad', {
          t: this._time_s,
          mass_kg: this._currentMass(),
        });
      } else if (forces.thrustMagnitude_N > 0) {
        this._burnTimeOnPad_s += dt;
      }
    }

    // 6. Failures -----------------------------------------------------------
    this._checkFailures(dt, forces, ignited, separating);

    // 7. Mission state ------------------------------------------------------
    this._advanceMissionState(dt, forces, separating.length > 0);

    // 8. Telemetry ----------------------------------------------------------
    this._recordTelemetry(forces, massFlow, this._events.length > eventsBefore);
    this._updatePeaks(forces, dt, previousSpeed);
    this._previousDynamicPressure_Pa = forces.dynamicPressure_Pa;

    // 9. Termination --------------------------------------------------------
    this._checkTermination(forces);

    return this.getState();
  }

  /**
   * Run until the simulation terminates.
   *
   * @param maxSteps - Optional cap, overriding the config's. Useful for
   *   stepping a long flight in chunks without blocking a frame.
   * @returns The complete result.
   */
  run(maxSteps?: number): SimResult {
    const cap = maxSteps ?? this._config.settings.maxSteps;
    let taken = 0;

    while (!this.isFinished && taken < cap) {
      this.step();
      taken++;
    }

    if (!this.isFinished) {
      this._terminate('step_limit', `Reached the ${cap} step limit`, 'complete');
    }

    return this.getResult();
  }

  /**
   * Assemble the result. Valid at any point; on an unfinished run it describes
   * the flight so far.
   *
   * @returns The result.
   */
  getResult(): SimResult {
    const outcome = this._classifyOutcome();
    return {
      success: outcome === 'success',
      outcome,
      finalState: this._missionState,
      terminationReason: this._terminationReason ?? 'still running',
      telemetry: this._sampler.points,
      events: this._events,
      failures: this._failures,
      summary: this._buildSummary(),
      totalSteps: this._stepCount,
      flightTime_s: Math.max(0, this._time_s),
      finalSimState: this.getState(),
    };
  }

  // ============================================================
  // Step internals
  // ============================================================

  /** Coast steps are longer; see `SimSettings.dt_coast_s`. */
  private _currentTimestep(): number {
    return this._isBurning()
      ? this._config.settings.dt_powered_s
      : this._config.settings.dt_coast_s;
  }

  /**
   * Altitude above mean sea level. Unit: m.
   *
   * This is what the atmosphere and gravity models want. It is *not* zero on
   * the pad — a launch site is usually some metres above sea level, and
   * conflating the two makes a vehicle look airborne before it has moved.
   */
  private _altitude(): number {
    const p = this._kinematics.position;
    return (
      Math.sqrt(p.x * p.x + p.y * p.y + (p.z + this._siteRadius_m) ** 2) - R_EARTH
    );
  }

  /**
   * Height above the ground beneath the vehicle. Unit: m.
   *
   * Zero on the pad. This is the measure liftoff and impact are detected
   * against. The ground is modelled as a sphere at the launch site's elevation,
   * so a vehicle that flies a long way downrange still lands at height zero.
   */
  private _heightAboveGround(): number {
    return this._altitude() - this._config.mission.launchSite.altitude_m;
  }

  /**
   * Hold the vehicle on the pad until thrust can lift it.
   *
   * Before liftoff the launch pad exerts a normal force that exactly cancels
   * whatever the net force would otherwise do downward. Without this the
   * vehicle falls through the ground during the countdown, and a vehicle whose
   * thrust-to-weight never reaches 1.0 burrows instead of sitting still.
   */
  private _applyGroundConstraint(): void {
    if (this._hasLiftedOff) return;
    if (this._heightAboveGround() > 0) return;

    // Pin it to the pad and cancel any downward velocity the integrator gave it.
    this._kinematics = {
      position: vec3(0, 0, 0),
      velocity: vec3(0, 0, 0),
    };
  }

  /** Rate of climb — the radial component of velocity. Unit: m/s. */
  private _verticalSpeed(): number {
    const up = localUpVector(this._kinematics.position, this._siteRadius_m);
    return dot(this._kinematics.velocity, up);
  }

  /** Whether any stage is producing thrust. */
  private _isBurning(): boolean {
    if (this._effects.killThrust) return false;
    return this._stages.some(s => s.status === 'burning');
  }

  /** The stage currently burning, if any. */
  private _burningStage(): StageState | undefined {
    if (this._effects.killThrust) return undefined;
    return this._stages.find(s => s.status === 'burning');
  }

  /** Propellant flow right now. Unit: kg/s. */
  private _currentMassFlow(): number {
    const burning = this._burningStage();
    if (!burning) return 0;
    return this._config.vehicle.stages[burning.index]?.massFlowRate_kgs ?? 0;
  }

  /** Total mass right now. Unit: kg. */
  private _currentMass(): number {
    const active = this._stages[this._activeStage];
    return currentMass(
      this._config.vehicle,
      this._activeStage,
      active?.propellantRemaining_kg ?? 0,
    );
  }

  /**
   * Build the force-model inputs.
   *
   * @param kinematics - Position and velocity to evaluate at.
   * @param dtIntoStep_s - How far into the current step this substep sits, so
   *   mass can be evaluated analytically at the right instant.
   */
  private _forceInputs(kinematics: KinematicState, dtIntoStep_s: number): ForceInputs {
    const burning = this._burningStage();
    const stage = burning ? this._config.vehicle.stages[burning.index] : undefined;

    // Exact linear depletion within the step.
    const massFlow = stage?.massFlowRate_kgs ?? 0;
    const propellantAtSubstep = burning
      ? Math.max(0, burning.propellantRemaining_kg - massFlow * dtIntoStep_s)
      : (this._stages[this._activeStage]?.propellantRemaining_kg ?? 0);

    const mass = currentMass(
      this._config.vehicle,
      this._activeStage,
      propellantAtSubstep,
    );

    // A stage with no propellant left produces no thrust, even mid-substep.
    const thrusting = burning !== undefined && propellantAtSubstep > 0;

    return {
      position: kinematics.position,
      velocity: kinematics.velocity,
      mass_kg: Math.max(1e-6, mass),
      thrustDirection: this._command.thrustDirection,
      thrustVacuum_N: thrusting ? (stage?.thrustVacuum_N ?? 0) : 0,
      thrustSeaLevel_N: thrusting ? (stage?.thrustSeaLevel_N ?? 0) : 0,
      referenceArea_m2: this._config.vehicle.referenceArea_m2,
      dragCoefficient: this._config.vehicle.dragCoefficient,
      siteRadius_m: this._siteRadius_m,
      useMachDragRise: this._config.settings.useMachDragRise,
      useAltitudeCompensation: this._config.settings.useAltitudeCompensation,
    };
  }

  /**
   * Ignite, cut off, and separate stages whose moment has arrived.
   *
   * @returns Which stages ignited and which are separating this step, for the
   *   injection scheduler.
   */
  private _sequenceStages(dt: number): {
    ignited: number[];
    separating: number[];
  } {
    const ignited: number[] = [];
    const separating: number[] = [];
    const vehicle = this._config.vehicle;

    // Guards read `this._time_s` — the state at the *start* of the step, which
    // is the only state actually known when the decision is made. Everything
    // recorded, though, is stamped with the time at the *end* of the step,
    // because that is the state the resulting telemetry sample describes.
    // Without that split, a cutoff event lands one timestep before the
    // telemetry row that shows the engine off, and the two records disagree.
    const t = this._time_s + dt;

    // --- Ignition --------------------------------------------------------
    const active = this._stages[this._activeStage];
    if (
      active &&
      active.status === 'stowed' &&
      this._time_s >= 0 &&
      !this._effects.killThrust
    ) {
      const stage = vehicle.stages[this._activeStage];
      const readyAt = this._ignitionReadyTime(this._activeStage);

      if (this._time_s >= readyAt) {
        if (stage?.canFire) {
          this._stages = updateStage(this._stages, this._activeStage, {
            status: 'burning',
            ignitionTime_s: t,
          });
          ignited.push(this._activeStage);
          // Always `stage_ignition` here. The mission-level `ignition` event
          // belongs to the state machine's COUNTDOWN → IGNITION transition, and
          // emitting both from here would double it up in the timeline.
          this._emitAt(t, 'stage_ignition', `Stage ${this._activeStage} ignition`, {
            stage: this._activeStage,
            thrust_N: stage.thrustSeaLevel_N,
            altitude_m: this._altitude(),
          });
        } else {
          // A stage that cannot fire is skipped rather than stalling the flight.
          this._stages = updateStage(this._stages, this._activeStage, {
            status: 'shutdown',
            cutoffTime_s: t,
          });
        }
      }
    }

    // --- Cutoff on reaching the target orbit ------------------------------
    // Guidance shuts the engines down when the mission's orbit is achieved,
    // rather than burning to depletion. See `GuidanceConfig.cutoffOnTargetOrbit`.
    const guidedCutoff = this._burningStage();
    if (guidedCutoff && this._config.guidance.cutoffOnTargetOrbit) {
      const orbit = this._orbitalElements();
      const targetAltitude_m = this._config.mission.target.targetAltitude_km * 1000;
      if (orbit && orbit.isStableOrbit && orbit.periapsisAltitude_m >= targetAltitude_m) {
        this._stages = updateStage(this._stages, guidedCutoff.index, {
          status: 'shutdown',
          cutoffTime_s: t,
        });
        this._emitAt(t, 'meco', `Stage ${guidedCutoff.index} cutoff on reaching target orbit`, {
          stage: guidedCutoff.index,
          periapsisAltitude_m: orbit.periapsisAltitude_m,
          apoapsisAltitude_m: Number.isFinite(orbit.apoapsisAltitude_m)
            ? orbit.apoapsisAltitude_m
            : -1,
          propellantRemaining_kg: guidedCutoff.propellantRemaining_kg,
        });
      }
    }

    // --- Cutoff on propellant depletion ------------------------------------
    const burning = this._burningStage();
    if (burning && burning.propellantRemaining_kg <= 0) {
      this._stages = updateStage(this._stages, burning.index, {
        status: 'shutdown',
        cutoffTime_s: t,
        propellantRemaining_kg: 0,
        propellantFraction: 0,
      });
      this._emitAt(t, 'meco', `Stage ${burning.index} engine cutoff`, {
        stage: burning.index,
        altitude_m: this._altitude(),
        speed_ms: magnitude(this._kinematics.velocity),
      });
    }

    // Thrust killed by a failure while a stage was still burning.
    if (this._effects.killThrust) {
      for (const s of this._stages) {
        if (s.status === 'burning' || s.status === 'igniting') {
          this._stages = updateStage(this._stages, s.index, {
            status: 'failed',
            cutoffTime_s: t,
          });
        }
      }
    }

    // --- Separation -------------------------------------------------------
    const spent = this._stages[this._activeStage];
    if (
      spent &&
      (spent.status === 'shutdown' || spent.status === 'failed') &&
      spent.cutoffTime_s !== null &&
      this._activeStage < vehicle.stages.length - 1
    ) {
      const delay = vehicle.stages[this._activeStage]?.separationDelay_s ?? 0;
      if (t >= spent.cutoffTime_s + delay) {
        if (this._effects.blockSeparation) {
          // The stage stays attached. Its dead mass is still carried, which is
          // exactly the point of the separation-failure mode.
          separating.push(this._activeStage);
        } else {
          this._stages = updateStage(this._stages, this._activeStage, {
            status: 'separated',
            separationTime_s: t,
          });
          separating.push(this._activeStage);
          this._peaks.stagesSeparated++;
          this._emitAt(t, 'staging', `Stage ${this._activeStage} separation`, {
            stage: this._activeStage,
            altitude_m: this._altitude(),
            speed_ms: magnitude(this._kinematics.velocity),
          });
          this._activeStage++;
        }
      }
    }

    return { ignited, separating };
  }

  /** The time a stage is cleared to ignite. Unit: s. */
  private _ignitionReadyTime(stageIndex: number): number {
    if (stageIndex === 0) return 0;
    const below = this._stages[stageIndex - 1];
    const delay = this._config.vehicle.stages[stageIndex]?.ignitionDelay_s ?? 0;
    // Measured from the separation of the stage below, which is when the
    // engines above it are clear to light.
    return below?.separationTime_s !== null && below?.separationTime_s !== undefined
      ? below.separationTime_s + delay
      : Number.POSITIVE_INFINITY;
  }

  /** Burn propellant out of the active stage. */
  private _depletePropellant(consumed_kg: number): void {
    const burning = this._burningStage();
    if (!burning || consumed_kg <= 0) return;

    const remaining = Math.max(0, burning.propellantRemaining_kg - consumed_kg);
    const initial = this._initialPropellant[burning.index] ?? 0;

    this._peaks.propellantUsed_kg += burning.propellantRemaining_kg - remaining;

    this._stages = updateStage(this._stages, burning.index, {
      propellantRemaining_kg: remaining,
      propellantFraction: initial > 0 ? remaining / initial : 0,
    });
  }

  /** Run detection and injection, and apply whatever fires. */
  private _checkFailures(
    dt: number,
    forces: ReturnType<typeof computeForces>,
    ignited: readonly number[],
    separating: readonly number[],
  ): void {
    const mass = this._currentMass();
    const gLoad_g =
      mass > 0 ? (forces.thrustMagnitude_N + forces.dragMagnitude_N) / mass / G0 : 0;

    const inputs = {
      t: this._time_s,
      dt_s: dt,
      altitude_m: forces.altitude_m,
      speed_ms: magnitude(this._kinematics.velocity),
      verticalSpeed_ms: this._verticalSpeed(),
      gLoad_g,
      dynamicPressure_Pa: forces.dynamicPressure_Pa,
      thrust_N: forces.thrustMagnitude_N,
      mass_kg: mass,
      activeStage: this._activeStage,
      isBurning: this._isBurning(),
      hasLiftedOff: this._hasLiftedOff,
      burnTimeOnPad_s: this._burnTimeOnPad_s,
    };

    const fresh = [
      ...detectFailures(inputs, this._config.vehicle, this._config.failures),
      ...checkInjections(
        {
          ...inputs,
          stagesIgnitedThisStep: ignited,
          stagesSeparatingThisStep: separating,
          maxAltitudeSoFar_m: this._peaks.maxAltitude_m,
        },
        this._config.failures,
        this._rng,
        this._firedInjections,
      ),
    ];

    if (fresh.length === 0) return;

    for (const failure of fresh) {
      // The same detection rule can fire on consecutive steps while the
      // condition persists. Only the first occurrence is a new failure.
      // Matched on occurrence id, so two scripted faults of the same mode both
      // register while one rule firing repeatedly does not.
      if (this._failures.some(f => f.id === failure.id)) continue;
      this._failures.push(failure);
      this._events.push(makeFailureEvent(failureEventType(failure), failure));
    }

    this._effects = combinedEffects(this._failures);

    if (this._effects.dumpPropellant) {
      const active = this._stages[this._activeStage];
      if (active && active.propellantRemaining_kg > 0) {
        this._stages = updateStage(this._stages, this._activeStage, {
          propellantRemaining_kg: 0,
          propellantFraction: 0,
        });
      }
    }
  }

  /** Advance the state machine and emit the events its transitions carry. */
  private _advanceMissionState(
    dt: number,
    forces: ReturnType<typeof computeForces>,
    separatedThisStep: boolean,
  ): void {
    const altitude = forces.altitude_m;
    const speed = magnitude(this._kinematics.velocity);
    const verticalSpeed = this._verticalSpeed();
    const orbit = this._orbitalElements();
    const active = this._stages[this._activeStage];

    // Supersonic is a milestone, not a state — emit it directly.
    if (!this._passedSupersonic && forces.mach >= 1) {
      this._passedSupersonic = true;
      this._emit('supersonic', 'Vehicle passed Mach 1', {
        altitude_m: altitude,
        speed_ms: speed,
        mach: forces.mach,
      });
    }

    const ctx: TransitionContext = {
      time_s: this._time_s,
      altitude_m: altitude,
      speed_ms: speed,
      verticalSpeed_ms: verticalSpeed,
      dynamicPressure_Pa: forces.dynamicPressure_Pa,
      previousDynamicPressure_Pa: this._previousDynamicPressure_Pa,
      maxQPassed: this._maxQPassed,
      thrust_N: forces.thrustMagnitude_N,
      isBurning: this._isBurning(),
      activeStage: this._activeStage,
      activeStageSpent:
        active !== undefined &&
        (active.status === 'shutdown' || active.status === 'failed'),
      // Edge-triggered: true only on the step where a stage actually left.
      separationDue: separatedThisStep,
      hasRemainingStages: hasRemainingStages(
        this._config.vehicle,
        this._activeStage + 1,
      ),
      isInStableOrbit: orbit?.isStableOrbit ?? false,
      targetAltitudeReached:
        altitude >= this._config.mission.target.targetAltitude_km * 1000,
      payloadDeployed: this._payloadDeployed,
      hasFatalFailure: this._effects.destroyVehicle,
      hasImpacted: this._hasLiftedOff && this._heightAboveGround() <= SURFACE_BAND_M,
      isReentering:
        verticalSpeed < 0 && altitude < ENTRY_INTERFACE_M && speed > ENTRY_SPEED_MS,
      objectivesComplete: this._payloadDeployed && (orbit?.isStableOrbit ?? false),
      timeInState_s: this._timeInState_s,
    };

    const { state, taken } = advanceMissionState(
      this._missionState,
      ctx,
      this._config.profile,
    );

    if (taken.length === 0) return;

    for (const transition of taken) {
      if (transition.to === 'PAYLOAD_DEPLOYMENT') this._payloadDeployed = true;
      if (transition.to === 'MAX_Q') this._maxQPassed = true;
      if (transition.event) {
        this._emit(transition.event, transition.description, {
          from: transition.from,
          to: transition.to,
          altitude_m: altitude,
          speed_ms: speed,
        });
      }
    }

    this._missionState = state;
    this._timeInState_s = 0;
    void dt;
  }

  /** Osculating orbital elements, or null while they carry no meaning. */
  private _orbitalElements(): OrbitalElements | null {
    if (this._altitude() < ORBIT_REPORTING_ALTITUDE_M) return null;

    // Elements are only meaningful in a frame aligned with the equator, so the
    // state vector is rotated out of the launch site's ENU axes first.
    const positionEci = enuPositionToEci(this._kinematics.position, this._basis);
    const velocityEci = enuVectorToEci(this._kinematics.velocity, this._basis);

    try {
      return orbitalElements(positionEci, velocityEci);
    } catch {
      // A degenerate state vector is not worth ending a flight over.
      return null;
    }
  }

  /** Assemble the vehicle state for a snapshot. */
  private _vehicleState(): VehicleState {
    const altitude = this._altitude();
    const verticalSpeed = this._verticalSpeed();

    return {
      position: this._kinematics.position,
      velocity: this._kinematics.velocity,
      acceleration: this._acceleration,
      attitude: {
        pitch_rad: this._command.pitch_rad,
        yaw_rad: this._command.yaw_rad,
        roll_rad: 0,
      },
      mass_kg: this._currentMass(),
      altitude_m: altitude,
      speed_ms: magnitude(this._kinematics.velocity),
      downrange_m: downrangeFromEnu(
        this._kinematics.position,
        this._config.mission.launchSite.altitude_m,
      ),
      verticalSpeed_ms: verticalSpeed,
      activeStage: this._activeStage,
      stages: this._stages,
      phase: this._flightPhase(verticalSpeed),
    };
  }

  /** The coarse flight phase the force model and renderer switch on. */
  private _flightPhase(verticalSpeed_ms: number): FlightPhase {
    if (this._status === 'complete' || this._status === 'failed') return 'terminated';
    if (this._time_s < 0 || !this._hasLiftedOff) return 'prelaunch';
    if (this._isBurning()) return 'powered';
    return verticalSpeed_ms < 0 ? 'descent' : 'coast';
  }

  /** Sample telemetry if the interval elapsed, or unconditionally on an event. */
  private _recordTelemetry(
    forces: ReturnType<typeof computeForces>,
    massFlow_kgs: number,
    eventFired: boolean,
  ): void {
    const active = this._stages[this._activeStage];
    const burning = this._burningStage();

    const point = buildTelemetryPoint({
      t: this._time_s,
      position: this._kinematics.position,
      velocity: this._kinematics.velocity,
      acceleration: this._acceleration,
      altitude_m: forces.altitude_m,
      downrange_m: downrangeFromEnu(
        this._kinematics.position,
        this._config.mission.launchSite.altitude_m,
      ),
      verticalSpeed_ms: this._verticalSpeed(),
      mass_kg: this._currentMass(),
      fuelRemaining_kg: active?.propellantRemaining_kg ?? 0,
      fuelFraction: active?.propellantFraction ?? 0,
      thrust_N: forces.thrustMagnitude_N,
      massFlow_kgs,
      drag_N: forces.dragMagnitude_N,
      dynamicPressure_Pa: forces.dynamicPressure_Pa,
      mach: forces.mach,
      airDensity_kgm3: forces.atmosphere.density_kgm3,
      ambientPressure_Pa: forces.atmosphere.pressure_Pa,
      localGravity_ms2: forces.localGravity_ms2,
      pitch_rad: this._command.pitch_rad,
      yaw_rad: this._command.yaw_rad,
      angleOfAttack_rad: angleOfAttack(
        this._command.thrustDirection,
        this._kinematics.velocity,
      ),
      orbit: this._orbitalElements(),
      stage: this._activeStage,
      stageStatus: active?.status ?? 'separated',
      engineOn: burning !== undefined,
      missionState: this._missionState,
      phase: this._flightPhase(this._verticalSpeed()),
    });

    this._lastTelemetry = point;
    this._sampler.offer(point, eventFired);
  }

  /** Track running peaks and the velocity-loss accounting. */
  private _updatePeaks(
    forces: ReturnType<typeof computeForces>,
    dt: number,
    previousSpeed_ms: number,
  ): void {
    const p = this._peaks;
    const t = this._lastTelemetry;

    if (t.altitude_m > p.maxAltitude_m) {
      p.maxAltitude_m = t.altitude_m;
      p.apogeeTime_s = t.t;
    }
    if (t.speed_ms > p.maxSpeed_ms) p.maxSpeed_ms = t.speed_ms;
    if (Math.abs(t.gLoad_g) > p.maxAcceleration_g) p.maxAcceleration_g = Math.abs(t.gLoad_g);
    if (t.dynamicPressure_Pa > p.maxDynamicPressure_Pa) {
      p.maxDynamicPressure_Pa = t.dynamicPressure_Pa;
      p.maxQAltitude_m = t.altitude_m;
    }
    if (t.mach > p.maxMach) p.maxMach = t.mach;
    if (t.downrange_m > p.maxDownrange_m) p.maxDownrange_m = t.downrange_m;

    p.velocityGained_ms += magnitude(this._kinematics.velocity) - previousSpeed_ms;

    // Velocity-loss accounting. Both terms integrate the component of the
    // relevant acceleration that acts *against* the direction of travel, which
    // is what makes them comparable with the ideal delta-v.
    const mass = Math.max(1e-6, this._currentMass());
    const speed = magnitude(this._kinematics.velocity);

    if (speed > 1) {
      const heading = scale(this._kinematics.velocity, 1 / speed);
      // Gravity loss: the component of gravity opposing motion.
      p.gravityLoss_ms += -dot(forces.gravity, heading) / mass * dt;
      // Drag loss: drag is always anti-parallel to velocity, so this is just
      // its magnitude over mass.
      p.dragLoss_ms += (forces.dragMagnitude_N / mass) * dt;
    }
  }

  /** Apply the configured termination rules. */
  private _checkTermination(forces: ReturnType<typeof computeForces>): void {
    const term = this._config.termination;
    const altitude = forces.altitude_m;

    if (term.onFatalFailure && this._effects.destroyVehicle) {
      this._terminate(
        'fatal_failure',
        'A fatal failure destroyed the vehicle',
        'failed',
      );
      return;
    }

    if (
      term.onImpact &&
      this._hasLiftedOff &&
      this._heightAboveGround() <= SURFACE_BAND_M
    ) {
      const speed = magnitude(this._kinematics.velocity);
      this._emit('impact', 'Vehicle reached the surface', {
        speed_ms: speed,
        downrange_m: this._lastTelemetry.downrange_m,
      });
      this._terminate('impact', 'Vehicle reached the surface', 'complete');
      return;
    }

    // A vehicle that never lifted off and has burnt out has nothing left to do.
    if (
      !this._hasLiftedOff &&
      this._time_s > 0 &&
      !this._isBurning() &&
      this._stages.every(s => s.status !== 'stowed')
    ) {
      this._terminate(
        'never_launched',
        'The vehicle never left the pad',
        'failed',
      );
      return;
    }

    if (term.onStableOrbit) {
      const orbit = this._orbitalElements();
      if (orbit?.isStableOrbit && !this._isBurning()) {
        this._terminate('orbit_achieved', 'Stable orbit achieved', 'complete');
        return;
      }
    }

    if (
      term.onTargetAltitude &&
      altitude >= this._config.mission.target.targetAltitude_km * 1000
    ) {
      this._emit('target_reached', 'Target altitude reached', { altitude_m: altitude });
      this._terminate('target_reached', 'Target altitude reached', 'complete');
      return;
    }

    if (term.onMissionComplete && isTerminalState(this._missionState)) {
      this._terminate(
        this._missionState === 'FAILURE' ? 'mission_failed' : 'mission_complete',
        this._missionState === 'FAILURE'
          ? 'The mission ended in failure'
          : 'The mission completed',
        this._missionState === 'FAILURE' ? 'failed' : 'complete',
      );
      return;
    }

    if (this._time_s >= this._config.settings.maxTime_s) {
      this._emit('timeout', 'Simulation time limit reached', { t: this._time_s });
      this._terminate('timeout', 'Simulation time limit reached', 'complete');
      return;
    }

    if (this._stepCount >= this._config.settings.maxSteps) {
      this._terminate('step_limit', 'Integration step limit reached', 'complete');
    }
  }

  /** End the run. */
  private _terminate(
    _reason: string,
    description: string,
    status: 'complete' | 'failed',
  ): void {
    this._terminationReason = description;
    this._status = status;
  }

  /** Append an event at the current simulation time. */
  private _emit(
    type: Parameters<typeof makeEvent>[1],
    description: string,
    data: Readonly<Record<string, number | string | boolean>> = {},
  ): void {
    this._emitAt(this._time_s, type, description, data);
  }

  /**
   * Append an event at an explicit time.
   *
   * Used by stage sequencing, which decides from the state at the start of a
   * step but must report at the end of it — see {@link _sequenceStages}.
   */
  private _emitAt(
    t: number,
    type: Parameters<typeof makeEvent>[1],
    description: string,
    data: Readonly<Record<string, number | string | boolean>> = {},
  ): void {
    this._events.push(makeEvent(t, type, description, data));
  }

  /** Classify the overall outcome. */
  private _classifyOutcome(): 'success' | 'partial' | 'failure' {
    if (this._failures.some(f => f.isTerminal)) return 'failure';
    if (this._missionState === 'FAILURE') return 'failure';
    if (this._missionState === this._config.profile.successState) return 'success';
    if (this._missionState === 'COMPLETE') return 'success';
    if (this._failures.length > 0) return 'partial';
    return this._hasLiftedOff ? 'partial' : 'failure';
  }

  /** Build the summary statistics. */
  private _buildSummary(): import('./events.js').SimSummary {
    const p = this._peaks;
    const impact = this._events.find(e => e.type === 'impact');

    // Ideal delta-v of the stages that actually fired.
    let deltaVIdeal_ms = 0;
    for (const stageState of this._stages) {
      const stage = this._config.vehicle.stages[stageState.index];
      if (!stage || stageState.ignitionTime_s === null) continue;
      const burnt = (this._initialPropellant[stageState.index] ?? 0) -
        stageState.propellantRemaining_kg;
      if (burnt <= 0) continue;
      const initial = currentMass(
        this._config.vehicle,
        stageState.index,
        this._initialPropellant[stageState.index] ?? 0,
      );
      const final = initial - burnt;
      if (final > 0) {
        deltaVIdeal_ms += stage.ispVacuum_s * G0 * Math.log(initial / final);
      }
    }

    return {
      maxAltitude_m: p.maxAltitude_m,
      maxSpeed_ms: p.maxSpeed_ms,
      maxAcceleration_g: p.maxAcceleration_g,
      maxDynamicPressure_Pa: p.maxDynamicPressure_Pa,
      maxQAltitude_m: p.maxQAltitude_m,
      maxMach: p.maxMach,
      flightTime_s: Math.max(0, this._time_s),
      apogeeTime_s: p.apogeeTime_s,
      maxDownrange_m: p.maxDownrange_m,
      impactSpeed_ms:
        typeof impact?.data['speed_ms'] === 'number' ? impact.data['speed_ms'] : null,
      stagesSeparated: p.stagesSeparated,
      propellantUsed_kg: p.propellantUsed_kg,
      deltaVAchieved_ms: p.maxSpeed_ms,
      deltaVIdeal_ms,
      gravityLoss_ms: p.gravityLoss_ms,
      dragLoss_ms: p.dragLoss_ms,
    };
  }
}

/** Zeroed peaks for a fresh run. */
function freshPeaks(): RunningPeaks {
  return {
    maxAltitude_m: 0,
    maxSpeed_ms: 0,
    maxAcceleration_g: 0,
    maxDynamicPressure_Pa: 0,
    maxQAltitude_m: 0,
    maxMach: 0,
    maxDownrange_m: 0,
    apogeeTime_s: 0,
    stagesSeparated: 0,
    propellantUsed_kg: 0,
    gravityLoss_ms: 0,
    dragLoss_ms: 0,
    velocityGained_ms: 0,
  };
}

// ============================================================
// Convenience API
// ============================================================

/**
 * Create a simulation without running it.
 *
 * @param config - The flight to prepare.
 * @returns A simulation sitting at T−countdown, ready to step.
 */
export function initializeMission(config: SimConfig): Simulation {
  return new Simulation(config);
}

/**
 * Run a complete flight and return the result.
 *
 * This blocks until the flight terminates. For a long orbital ascent that can
 * be tens of thousands of steps, so call it in a Web Worker — or step the
 * simulation yourself — if it must not block a frame.
 *
 * @param config - The flight to run.
 * @returns The complete result.
 */
export function runSimulation(config: SimConfig): SimResult {
  return new Simulation(config).run();
}

/**
 * Advance a simulation by one step.
 *
 * A free-function form of {@link Simulation.step}, for callers who prefer the
 * documented functional API.
 *
 * @param simulation - The simulation to advance.
 * @returns The state after the step.
 */
export function stepSimulation(simulation: Simulation): SimulationState {
  return simulation.step();
}

/** Pause a simulation. @param simulation - The simulation to pause. */
export function pauseSimulation(simulation: Simulation): void {
  simulation.pause();
}

/** Resume a simulation. @param simulation - The simulation to resume. */
export function resumeSimulation(simulation: Simulation): void {
  simulation.resume();
}

/** Reset a simulation to its initial state. @param simulation - The simulation. */
export function resetSimulation(simulation: Simulation): void {
  simulation.reset();
}

/** Read a simulation's telemetry. @param simulation - The simulation. */
export function getTelemetry(simulation: Simulation): readonly TelemetryPoint[] {
  return simulation.getTelemetry();
}

/** Read a simulation's events. @param simulation - The simulation. */
export function getEvents(simulation: Simulation): readonly SimEvent[] {
  return simulation.getEvents();
}

/** Read a simulation's mission state. @param simulation - The simulation. */
export function getMissionState(simulation: Simulation): MissionState {
  return simulation.getMissionState();
}
