/**
 * Rocket design validation.
 *
 * Two layers of checking exist in this package:
 *
 * 1. `validateDesign` in `core/rocket-design.ts` — **structural**. Are the
 *    references intact? Cheap enough to run on every keystroke in the builder.
 * 2. `validateRocket` here — **engineering**. Will it fly? Runs the full
 *    analysis and applies aerospace rules of thumb.
 *
 * Every issue carries a machine-readable code, the measured value, the expected
 * value, and a plain-language explanation. That shape is deliberate: P1 renders
 * it, P2 stores it, and P4's explanation pipeline grounds its answers in it
 * rather than inventing physics.
 *
 * @module core/validation
 */

import type { RocketDesign } from './component-types.js';
import type { ComponentRegistry } from './component-registry.js';
import { validateDesign } from './rocket-design.js';
import { analyzeRocket, type RocketAnalysis } from './builder.js';

// ============================================================
// Result types
// ============================================================

/** How much an issue matters. */
export type ValidationSeverity = 'error' | 'warning' | 'info';

/** Stable issue codes. Backend and AI layers may switch on these. */
export type ValidationCode =
  // Structural
  | 'NO_STAGES'
  | 'NO_COMPONENTS'
  | 'MISSING_DEF'
  | 'INVALID_STAGE_REF'
  | 'DANGLING_CONNECTION'
  | 'DUPLICATE_INSTANCE_ID'
  | 'EMPTY_STAGE'
  // Propulsion
  | 'NO_ENGINE'
  | 'ENGINE_WITHOUT_PROPELLANT'
  | 'PROPELLANT_WITHOUT_ENGINE'
  | 'STAGE_CANNOT_FIRE'
  | 'INSUFFICIENT_LIFTOFF_TWR'
  | 'MARGINAL_LIFTOFF_TWR'
  | 'EXCESSIVE_LIFTOFF_TWR'
  | 'SHORT_BURN_TIME'
  // Structure & aero
  | 'NO_NOSE_CONE'
  | 'STATICALLY_UNSTABLE'
  | 'MARGINAL_STABILITY'
  | 'OVERSTABLE'
  // Systems
  | 'NO_AVIONICS'
  | 'NO_PAYLOAD'
  | 'NO_RECOVERY'
  // Mission fit
  | 'INSUFFICIENT_DELTA_V';

/** One validation finding. */
export interface ValidationIssue {
  readonly code: ValidationCode;
  readonly severity: ValidationSeverity;
  /** One-line statement of the problem. */
  readonly message: string;
  /** Why this matters, in terms a student can follow. */
  readonly explanation: string;
  /** What to change to fix it. */
  readonly recommendation: string;
  /** Stage the issue belongs to, if it is stage-specific. */
  readonly stageIndex?: number;
  /** Component instance the issue belongs to, if it is component-specific. */
  readonly componentId?: string;
  /** The measured value that triggered the rule. */
  readonly actual?: number;
  /** The threshold the rule expects. */
  readonly expected?: number;
  /** Unit of `actual` and `expected`, for display. */
  readonly unit?: string;
}

/** Outcome of validating a design. */
export interface ValidationResult {
  /** True when there are no errors. Warnings do not block. */
  readonly valid: boolean;
  /**
   * Whether the simulation can run. Same as `valid` today, but kept separate
   * because a design can be flyable-but-doomed, which is a fine thing to
   * simulate and a bad thing to call valid.
   */
  readonly canSimulate: boolean;
  /** Every issue found, in the order the rules ran. */
  readonly issues: readonly ValidationIssue[];
  /** Issues with severity `error`. */
  readonly errors: readonly ValidationIssue[];
  /** Issues with severity `warning`. */
  readonly warnings: readonly ValidationIssue[];
  /** Issues with severity `info`. */
  readonly infos: readonly ValidationIssue[];
  /** The analysis the rules ran against, so callers need not recompute it. */
  readonly analysis: RocketAnalysis;
}

// ============================================================
// Thresholds
// ============================================================

/**
 * Engineering thresholds the rules apply. Exposed so a lesson can tighten or
 * relax them, and so the numbers in the UI have one source.
 */
export interface ValidationThresholds {
  /** Below this liftoff TWR the vehicle cannot leave the pad. Dimensionless. */
  readonly minLiftoffTWR: number;
  /** Below this the vehicle rises but wastes most of its propellant fighting gravity. */
  readonly recommendedLiftoffTWR: number;
  /** Above this the vehicle pulls uncomfortable g-loads off the pad. */
  readonly maxLiftoffTWR: number;
  /** Minimum static margin for a stable vehicle. Unit: calibers. */
  readonly minStabilityMargin_cal: number;
  /** Above this the vehicle weathercocks into crosswinds. Unit: calibers. */
  readonly maxStabilityMargin_cal: number;
  /** Burns shorter than this leave no room for guidance to act. Unit: s. */
  readonly minBurnTime_s: number;
}

/** Default thresholds, drawn from conventional launch-vehicle practice. */
export const DEFAULT_THRESHOLDS: ValidationThresholds = {
  minLiftoffTWR: 1.0,
  recommendedLiftoffTWR: 1.2,
  maxLiftoffTWR: 8.0,
  minStabilityMargin_cal: 1.0,
  maxStabilityMargin_cal: 3.0,
  minBurnTime_s: 1.0,
} as const;

// ============================================================
// Validation
// ============================================================

/** Options for {@link validateRocket}. */
export interface ValidateRocketOptions {
  /** Override any threshold. Unspecified fields keep their default. */
  readonly thresholds?: Partial<ValidationThresholds>;
  /**
   * Delta-v the intended mission requires. Unit: m/s. When given, the vehicle's
   * total ideal delta-v is checked against it.
   *
   * Reference figures: ~9 400 m/s to low Earth orbit including losses,
   * ~1 800 m/s for a 100 km suborbital hop.
   */
  readonly requiredDeltaV_ms?: number;
  /** Whether the mission needs a recovery system. Defaults to false. */
  readonly requiresRecovery?: boolean;
}

/**
 * Validate a rocket design for flight.
 *
 * Runs the structural checks first, then the engineering rules against a full
 * {@link analyzeRocket} pass.
 *
 * @param design - Design to validate.
 * @param registry - Registry resolving component definitions.
 * @param options - Thresholds and mission requirements.
 * @returns Issues found, plus the analysis they were derived from.
 */
export function validateRocket(
  design: RocketDesign,
  registry: ComponentRegistry,
  options: ValidateRocketOptions = {},
): ValidationResult {
  const thresholds: ValidationThresholds = {
    ...DEFAULT_THRESHOLDS,
    ...options.thresholds,
  };
  const issues: ValidationIssue[] = [];
  const analysis = analyzeRocket(design, registry);

  // --- Structural ---------------------------------------------------------
  const structural = validateDesign(design, registry);
  for (const error of structural.errors) {
    issues.push({
      code: error.code as ValidationCode,
      severity: 'error',
      message: error.message,
      explanation:
        'The design references something that does not exist. This usually ' +
        'means a component was deleted while something else still pointed at it.',
      recommendation: 'Remove or repair the broken reference in the builder.',
      ...(error.stageIndex !== undefined ? { stageIndex: error.stageIndex } : {}),
      ...(error.componentId !== undefined ? { componentId: error.componentId } : {}),
    });
  }
  for (const stage of design.stages) {
    if (!design.components.some(c => c.stageIndex === stage.index)) {
      issues.push({
        code: 'EMPTY_STAGE',
        severity: 'warning',
        message: `Stage ${stage.index} ("${stage.name}") is empty`,
        explanation:
          'An empty stage adds a separation event but no mass, thrust, or ' +
          'propellant. The simulation will step straight past it.',
        recommendation: 'Add components to the stage, or remove it.',
        stageIndex: stage.index,
      });
    }
  }

  // Nothing further is meaningful without stages and components.
  if (design.stages.length === 0 || design.components.length === 0) {
    return buildResult(issues, analysis);
  }

  // --- Propulsion ---------------------------------------------------------
  const anyEngine = analysis.stages.some(s => s.engineCount > 0);
  if (!anyEngine) {
    issues.push({
      code: 'NO_ENGINE',
      severity: 'error',
      message: 'The rocket has no engines',
      explanation:
        'Without an engine there is no thrust, so the vehicle cannot ' +
        'accelerate against gravity. It would simply sit on the pad.',
      recommendation: 'Add at least one engine to the first stage.',
    });
  }

  for (const stage of analysis.stages) {
    if (stage.engineCount > 0 && stage.propellantMass_kg <= 0) {
      issues.push({
        code: 'ENGINE_WITHOUT_PROPELLANT',
        severity: 'error',
        message: `Stage ${stage.index} has ${stage.engineCount} engine(s) but no propellant`,
        explanation:
          'Engines convert propellant into momentum. With empty tanks the ' +
          'stage produces thrust for zero seconds.',
        recommendation: `Add fuel and oxidizer tanks to stage ${stage.index}.`,
        stageIndex: stage.index,
      });
    }

    if (stage.engineCount === 0 && stage.propellantMass_kg > 0) {
      issues.push({
        code: 'PROPELLANT_WITHOUT_ENGINE',
        severity: 'warning',
        message: `Stage ${stage.index} carries propellant but has no engine`,
        explanation:
          'The propellant will be carried as dead weight for the whole ' +
          'flight, costing delta-v in every stage below it.',
        recommendation: `Add an engine to stage ${stage.index}, or remove its tanks.`,
        stageIndex: stage.index,
        actual: stage.propellantMass_kg,
        unit: 'kg',
      });
    }

    if (stage.canFire && stage.burnTime_s < thresholds.minBurnTime_s) {
      issues.push({
        code: 'SHORT_BURN_TIME',
        severity: 'warning',
        message: `Stage ${stage.index} burns for only ${stage.burnTime_s.toFixed(2)} s`,
        explanation:
          'A burn this short gives the guidance system almost no time to ' +
          'steer, and the stage mass barely pays for itself.',
        recommendation:
          'Add propellant, or use a smaller engine so the same propellant lasts longer.',
        stageIndex: stage.index,
        actual: stage.burnTime_s,
        expected: thresholds.minBurnTime_s,
        unit: 's',
      });
    }

    if (!stage.canFire && stage.wetMass_kg > 0 && stage.engineCount > 0) {
      issues.push({
        code: 'STAGE_CANNOT_FIRE',
        severity: 'error',
        message: `Stage ${stage.index} cannot produce thrust`,
        explanation:
          'The stage has engines but the combination of throttle, thrust, and ' +
          'specific impulse yields no usable mass flow.',
        recommendation: 'Check the engine ratings and the throttle setting.',
        stageIndex: stage.index,
      });
    }
  }

  // --- Liftoff thrust-to-weight ------------------------------------------
  if (anyEngine) {
    const twr = analysis.liftoffTWR;
    if (twr < thresholds.minLiftoffTWR) {
      issues.push({
        code: 'INSUFFICIENT_LIFTOFF_TWR',
        severity: 'error',
        message: `Liftoff thrust-to-weight is ${twr.toFixed(2)}, below 1.0`,
        explanation:
          'Thrust must exceed weight for the vehicle to accelerate upward. ' +
          'Below a ratio of 1.0 the rocket never leaves the pad, however long ' +
          'it burns.',
        recommendation:
          'Add engines, use a higher-thrust engine, or cut mass — especially propellant in upper stages.',
        actual: twr,
        expected: thresholds.minLiftoffTWR,
        unit: 'ratio',
      });
    } else if (twr < thresholds.recommendedLiftoffTWR) {
      issues.push({
        code: 'MARGINAL_LIFTOFF_TWR',
        severity: 'warning',
        message: `Liftoff thrust-to-weight is ${twr.toFixed(2)}, below the recommended ${thresholds.recommendedLiftoffTWR}`,
        explanation:
          'The rocket will lift off, but it climbs so slowly that most of the ' +
          'early burn is spent simply holding itself up. That loss is called ' +
          'gravity drag and it is paid in delta-v.',
        recommendation: 'Aim for a liftoff ratio between 1.2 and 2.0.',
        actual: twr,
        expected: thresholds.recommendedLiftoffTWR,
        unit: 'ratio',
      });
    } else if (twr > thresholds.maxLiftoffTWR) {
      issues.push({
        code: 'EXCESSIVE_LIFTOFF_TWR',
        severity: 'warning',
        message: `Liftoff thrust-to-weight is ${twr.toFixed(2)}, above ${thresholds.maxLiftoffTWR}`,
        explanation:
          'Very high initial acceleration drives the vehicle to high speed ' +
          'while still deep in the atmosphere, which raises peak dynamic ' +
          'pressure and the structural loads that come with it.',
        recommendation: 'Throttle the first stage down, or carry more propellant.',
        actual: twr,
        expected: thresholds.maxLiftoffTWR,
        unit: 'ratio',
      });
    }
  }

  // --- Aerodynamics -------------------------------------------------------
  const hasNoseCone = analysis.layout.components.some(c => c.category === 'nose_cone');
  if (!hasNoseCone) {
    issues.push({
      code: 'NO_NOSE_CONE',
      severity: 'warning',
      message: 'The rocket has no nose cone',
      explanation:
        'A flat front face has several times the drag of a cone, and it puts ' +
        'the centre of pressure right at the tip, which hurts stability.',
      recommendation: 'Add a nose cone to the topmost stage.',
    });
  }

  // The dry case is checked because a vehicle usually becomes *less* stable as
  // propellant drains from tanks that sit forward of the fins.
  const margin = Math.min(
    analysis.stabilityWet.stabilityMargin_cal,
    analysis.stabilityDry.stabilityMargin_cal,
  );

  // A vehicle with a gimballed engine and a guidance unit can steer its way out
  // of static instability — which is exactly how every real orbital launcher
  // flies, since a tall stack full of propellant always has its centre of
  // gravity too far aft to be stable on fins alone. Flagging that as a warning
  // would teach the wrong lesson, so it is reported as information instead.
  const hasActiveControl =
    analysis.layout.components.some(
      c => c.category === 'engine' && c.def.category === 'engine' && c.def.gimballed,
    ) &&
    analysis.layout.components.some(c => c.category === 'guidance');

  if (margin < 0.5) {
    issues.push({
      code: 'STATICALLY_UNSTABLE',
      severity: hasActiveControl ? 'info' : 'warning',
      message: `Static margin falls to ${margin.toFixed(2)} calibers during flight`,
      explanation: hasActiveControl
        ? 'The centre of pressure sits ahead of the centre of gravity, so the ' +
          'vehicle is not stable on its aerodynamics alone. It does not need to ' +
          'be: the gimballed engine and guidance unit steer it actively, which ' +
          'is how every large launch vehicle flies. Note that this also means ' +
          'the vehicle depends on that control system — losing it is not ' +
          'recoverable.'
        : 'The centre of pressure is at or ahead of the centre of gravity, so ' +
          'aerodynamic forces amplify any disturbance instead of correcting it. ' +
          'With no gimballed engine to steer with, the vehicle will tumble once ' +
          'it has enough airspeed.',
      recommendation: hasActiveControl
        ? 'No change needed, as long as the guidance and gimbal remain in the design.'
        : 'Move mass forward, add fins further aft, or fit a gimballed engine and a guidance unit.',
      actual: margin,
      expected: thresholds.minStabilityMargin_cal,
      unit: 'calibers',
    });
  } else if (margin < thresholds.minStabilityMargin_cal) {
    issues.push({
      code: 'MARGINAL_STABILITY',
      severity: 'warning',
      message: `Static margin falls to ${margin.toFixed(2)} calibers during flight`,
      explanation:
        'The vehicle self-corrects, but weakly. Wind or a thrust misalignment ' +
        'could still push it off course faster than it recovers.',
      recommendation: 'Aim for 1 to 2 calibers of margin across the whole flight.',
      actual: margin,
      expected: thresholds.minStabilityMargin_cal,
      unit: 'calibers',
    });
  } else if (margin > thresholds.maxStabilityMargin_cal) {
    issues.push({
      code: 'OVERSTABLE',
      severity: 'info',
      message: `Static margin is ${margin.toFixed(2)} calibers — more than needed`,
      explanation:
        'A very stable rocket turns hard into any crosswind. That is called ' +
        'weathercocking, and it costs altitude because thrust ends up pointed ' +
        'sideways.',
      recommendation: 'Smaller fins, or move them slightly forward.',
      actual: margin,
      expected: thresholds.maxStabilityMargin_cal,
      unit: 'calibers',
    });
  }

  // --- Systems ------------------------------------------------------------
  const hasAvionics = analysis.layout.components.some(
    c => c.category === 'avionics' || c.category === 'guidance',
  );
  if (!hasAvionics) {
    issues.push({
      code: 'NO_AVIONICS',
      severity: 'warning',
      message: 'The rocket has no avionics or guidance',
      explanation:
        'Nothing on board can sense attitude, run the pitch program, or ' +
        'command staging. The simulation will still fly the scripted profile, ' +
        'but a real vehicle would be uncontrolled.',
      recommendation: 'Add an avionics bay or a guidance unit.',
    });
  }

  if (analysis.payloadMass_kg <= 0) {
    issues.push({
      code: 'NO_PAYLOAD',
      severity: 'info',
      message: 'The rocket carries no payload',
      explanation:
        'A rocket with no payload can still fly a test profile, but it has no ' +
        'mission objective to succeed at.',
      recommendation: 'Add a payload component to the topmost stage.',
    });
  }

  if (options.requiresRecovery) {
    const hasRecovery = analysis.layout.components.some(
      c => c.category === 'parachute' || c.category === 'landing_leg',
    );
    if (!hasRecovery) {
      issues.push({
        code: 'NO_RECOVERY',
        severity: 'warning',
        message: 'The mission requires recovery but the rocket has no recovery system',
        explanation:
          'Without a parachute or landing legs the vehicle arrives at the ' +
          'surface at terminal velocity.',
        recommendation: 'Add a parachute or landing legs.',
      });
    }
  }

  // --- Mission fit --------------------------------------------------------
  if (options.requiredDeltaV_ms !== undefined) {
    if (analysis.totalDeltaV_ms < options.requiredDeltaV_ms) {
      const shortfall = options.requiredDeltaV_ms - analysis.totalDeltaV_ms;
      issues.push({
        code: 'INSUFFICIENT_DELTA_V',
        severity: 'warning',
        message:
          `Total ideal delta-v is ${Math.round(analysis.totalDeltaV_ms)} m/s, ` +
          `${Math.round(shortfall)} m/s short of the mission requirement`,
        explanation:
          'Delta-v is the total velocity change a vehicle can produce. It ' +
          'comes from the rocket equation, so it grows with the logarithm of ' +
          'the mass ratio — adding propellant has rapidly diminishing returns, ' +
          'while cutting dry mass helps disproportionately. Note that the ' +
          'figure quoted here is ideal, and gravity and drag losses will ' +
          'consume a further 1.5–2 km/s on an ascent to orbit.',
        recommendation:
          'Add propellant, reduce dry mass, add a stage, or choose engines with a higher specific impulse.',
        actual: analysis.totalDeltaV_ms,
        expected: options.requiredDeltaV_ms,
        unit: 'm/s',
      });
    }
  }

  return buildResult(issues, analysis);
}

/** Split issues by severity and assemble the result. */
function buildResult(
  issues: readonly ValidationIssue[],
  analysis: RocketAnalysis,
): ValidationResult {
  const errors = issues.filter(i => i.severity === 'error');
  const warnings = issues.filter(i => i.severity === 'warning');
  const infos = issues.filter(i => i.severity === 'info');

  return {
    valid: errors.length === 0,
    canSimulate: errors.length === 0,
    issues: Object.freeze([...issues]),
    errors: Object.freeze(errors),
    warnings: Object.freeze(warnings),
    infos: Object.freeze(infos),
    analysis,
  };
}
