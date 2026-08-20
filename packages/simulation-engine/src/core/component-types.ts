/**
 * Comprehensive rocket component domain types using discriminated unions.
 *
 * Each component category has specific physical, structural, and propulsion
 * properties. The `category` field is the discriminant.
 *
 * All values are SI units. No React/Three.js dependencies.
 *
 * @module core/component-types
 */

// ============================================================
// Component Categories
// ============================================================

export const COMPONENT_CATEGORIES = [
  // Airframe
  'body', 'nose_cone', 'fairing', 'coupler', 'interstage',
  // Propulsion
  'engine', 'motor_mount', 'fuel_tank', 'oxidizer_tank',
  // Aerodynamics
  'fin',
  // Structure
  'bulkhead', 'centering_ring',
  // Avionics and power
  'avionics', 'guidance', 'sensor', 'battery',
  // Mission
  'payload', 'decoupler',
  // Recovery and thermal
  'parachute', 'heat_shield', 'landing_leg',
  // Escape hatch for user-defined parts
  'custom',
] as const;

export type ComponentCategory = typeof COMPONENT_CATEGORIES[number];

// ============================================================
// Shared Property Types
// ============================================================

/** Thermal properties common to components that experience heating. */
export interface ThermalProperties {
  /** Maximum operating temperature. Unit: K */
  readonly maxTemperature_K: number;
  /** Thermal mass (specific heat × mass). Unit: J/K */
  readonly thermalMass_JperK: number;
  /** Emissivity for radiative cooling (0–1, dimensionless). */
  readonly emissivity: number;
}

/** Structural properties for load-bearing components. */
export interface StructuralProperties {
  /** Maximum axial load before failure. Unit: N */
  readonly maxAxialLoad_N: number;
  /** Maximum lateral load before failure. Unit: N */
  readonly maxLateralLoad_N: number;
  /** Maximum dynamic pressure the component can withstand. Unit: Pa */
  readonly maxDynamicPressure_Pa: number;
}

/** Reference to a 3D visual asset for rendering. */
export interface VisualAssetRef {
  /** Asset identifier or path (resolved by renderer layer). */
  readonly assetId: string;
  /** Fallback: use procedural geometry if asset not found. */
  readonly fallbackProcedural: boolean;
  /** Base color for procedural rendering. */
  readonly color?: string;
}

/** A mode in which a component can fail. */
export interface FailureMode {
  /** Machine-readable failure identifier. */
  readonly id: string;
  /** Human-readable failure name. */
  readonly name: string;
  /** Condition description (for educational display). */
  readonly condition: string;
  /** Severity if this failure occurs. */
  readonly severity: 'warning' | 'critical' | 'fatal';
  /** Which parameter to monitor. */
  readonly monitoredParameter: string;
  /** Threshold value at which failure triggers. */
  readonly threshold: number;
  /** Unit of the threshold for display. */
  readonly thresholdUnit: string;
}

/** Attachment point where another component can connect. */
export interface AttachmentPoint {
  /** Identifier for this attachment point. */
  readonly id: string;
  /** Which component categories can attach here. */
  readonly accepts: readonly ComponentCategory[];
  /** Position offset from component origin. Unit: m */
  readonly offset_x: number;
  readonly offset_y: number;
  readonly offset_z: number;
}

// ============================================================
// Base Component Definition
// ============================================================

/** Fields shared by all component definitions. */
export interface BaseComponentDef {
  /** Globally unique identifier for this component definition. */
  readonly id: string;
  /** Human-readable name. */
  readonly name: string;
  /** Detailed description for UI/educational display. */
  readonly description: string;
  /** Component category (discriminant field). */
  readonly category: ComponentCategory;
  /** Dry mass of this component. Unit: kg */
  readonly mass_kg: number;
  /** Outer diameter. Unit: m */
  readonly outerDiameter_m: number;
  /** Length along longitudinal axis. Unit: m */
  readonly length_m: number;
  /** Structural properties. */
  readonly structural: StructuralProperties;
  /** Thermal limits. */
  readonly thermal: ThermalProperties;
  /** Known failure modes. */
  readonly failureModes: readonly FailureMode[];
  /** Attachment points for connecting other components. */
  readonly attachmentPoints: readonly AttachmentPoint[];
  /** Visual asset reference for 3D rendering. */
  readonly visual: VisualAssetRef;
  /** Cost in arbitrary units (for gamification). */
  readonly cost: number;
}

// ============================================================
// Category-Specific Definitions (Discriminated Union Members)
// ============================================================

export interface BodyDef extends BaseComponentDef {
  readonly category: 'body';
  /** Inner diameter (for internal volume). Unit: m */
  readonly innerDiameter_m: number;
  /** Wall thickness. Unit: m */
  readonly wallThickness_m: number;
  /** Material name (for display). */
  readonly material: string;
}

/**
 * Nose cone profiles.
 *
 * These are not cosmetic labels. Each names a different generating curve, and
 * the curve determines both the silhouette the renderer lathes and the wave
 * drag the vehicle carries. Von Kármán in particular is the minimum-drag shape
 * for a given length and base diameter at supersonic speed, which is why it is
 * on the front of most launch vehicles.
 */
export type NoseConeShape =
  | 'conical'
  | 'ogive'
  | 'tangent_ogive'
  | 'secant_ogive'
  | 'von_karman'
  | 'haack'
  | 'elliptical'
  | 'parabolic'
  | 'power_series'
  | 'blunt'
  | 'custom';

export interface NoseConeDef extends BaseComponentDef {
  readonly category: 'nose_cone';
  /** Generating curve. Drives both the drawn profile and the wave drag. */
  readonly shape: NoseConeShape;
  /** Fineness ratio (length / base diameter). Dimensionless. */
  readonly finenessRatio: number;
  /** Drag coefficient contribution. Dimensionless. */
  readonly dragCoefficient: number;
  /**
   * Shape parameter for the families that take one.
   *
   * - `power_series`: the exponent n in r = R·(x/L)^n. 0.5 is a common choice.
   * - `parabolic`: K′ in [0, 1]. 0 is a cone, 1 is the full parabola.
   * - `haack`: C. 0 gives the LD-Haack (von Kármán) minimum-drag body,
   *   1/3 gives the LV-Haack.
   * - `secant_ogive`: the ratio of the generating radius to the tangent-ogive
   *   radius, greater than 1.
   *
   * Ignored by the shapes that have no free parameter.
   */
  readonly shapeParameter?: number;
  /** Tip radius, for a blunted nose. 0 is a sharp point. Unit: m */
  readonly tipRadius_m?: number;
  /** Wall thickness. Unit: m */
  readonly wallThickness_m?: number;
  /** Material name, for display and for the mass estimate. */
  readonly material?: string;
  /** Whether this cone doubles as a payload fairing that separates. */
  readonly isSeparable?: boolean;
}

/** One sample of a motor's measured thrust over time. */
export interface ThrustCurvePoint {
  /** Time since ignition. Unit: s */
  readonly t: number;
  /** Thrust at that instant, at sea level. Unit: N */
  readonly thrust_N: number;
}

/**
 * NAR/TRA impulse class.
 *
 * Each letter doubles the total impulse of the one before it: A is up to
 * 2.5 N·s, B up to 5, C up to 10, and so on. It is the standard way motors are
 * described, and worth carrying because it makes two motors comparable at a
 * glance in a way that raw newton-seconds does not.
 */
export type MotorClass =
  | 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J' | 'K' | 'L'
  | 'M' | 'N' | 'O' | 'P' | 'Q' | 'R' | 'S' | 'T' | 'orbital';

export interface EngineDef extends BaseComponentDef {
  readonly category: 'engine';
  /**
   * Propellant cast into the motor itself, as solid motors carry it. Unit: kg.
   *
   * Zero for liquid engines, which draw from separate tanks. A motor with
   * integral propellant needs no tanks in its stage, and `mass_kg` for such a
   * motor is the *empty casing* mass, excluding this.
   */
  readonly integralPropellant_kg: number;
  /** Vacuum thrust. Unit: N */
  readonly thrust_N: number;
  /** Sea-level thrust. Unit: N */
  readonly thrustSeaLevel_N: number;
  /** Vacuum specific impulse. Unit: s */
  readonly isp_vacuum_s: number;
  /** Sea-level specific impulse. Unit: s */
  readonly isp_seaLevel_s: number;
  /** Propellant type consumed. */
  readonly propellantType: PropellantType;
  /** Nozzle exit area. Unit: m² */
  readonly nozzleExitArea_m2: number;
  /** Expansion ratio (exit/throat). Dimensionless. */
  readonly expansionRatio: number;
  /** Number of ignitions supported. */
  readonly maxIgnitions: number;
  /** Minimum throttle (0–1). Dimensionless. */
  readonly minThrottle: number;
  /** Whether the engine can gimbal for thrust vectoring. */
  readonly gimballed: boolean;
  /** Maximum gimbal angle. Unit: rad */
  readonly maxGimbalAngle_rad: number;

  // ── Motor characterisation ──────────────────────────────────
  //
  // A liquid engine is defined by a steady thrust and a burn duration set by
  // how much propellant it is fed. A solid motor is defined by its *curve* —
  // it has a startup transient, a peak, and a tail-off, and none of that is
  // optional because the grain geometry decides it. Carrying the curve is what
  // lets the simulation fly a real motor rather than a rectangle.

  /**
   * Measured thrust against time, at sea level. Empty for a throttleable
   * liquid engine, where thrust is commanded rather than fixed.
   */
  readonly thrustCurve?: readonly ThrustCurvePoint[];
  /** Nominal burn duration. Unit: s */
  readonly burnTime_s?: number;
  /** Thrust integrated over the burn. Unit: N·s */
  readonly totalImpulse_Ns?: number;
  /** Mean thrust over the burn. Unit: N */
  readonly averageThrust_N?: number;
  /** Peak thrust reached. Usually during the startup transient. Unit: N */
  readonly maxThrust_N?: number;
  /** NAR/TRA impulse class. */
  readonly motorClass?: MotorClass;
  /** Manufacturer's designation, e.g. "F52", "Merlin 1D", "RS-25". */
  readonly designation?: string;
  /** Whether the motor can be shut down once lit. Never true for a solid. */
  readonly canShutdown?: boolean;
  /** Whether it can be throttled continuously between min and full. */
  readonly throttleable?: boolean;
}

export type PropellantType =
  | 'solid'
  | 'liquid_bipropellant'
  | 'liquid_monopropellant'
  | 'hybrid'
  | 'cold_gas';

export interface FuelTankDef extends BaseComponentDef {
  readonly category: 'fuel_tank';
  /** Maximum fuel capacity. Unit: kg */
  readonly capacity_kg: number;
  /** Fuel type identifier. */
  readonly fuelType: string;
  /** Fuel density. Unit: kg/m³ */
  readonly fuelDensity_kgm3: number;
  /** Internal volume. Unit: m³ */
  readonly volume_m3: number;
  /** Tank pressurization pressure. Unit: Pa */
  readonly pressurization_Pa: number;
}

export interface OxidizerTankDef extends BaseComponentDef {
  readonly category: 'oxidizer_tank';
  /** Maximum oxidizer capacity. Unit: kg */
  readonly capacity_kg: number;
  /** Oxidizer type identifier. */
  readonly oxidizerType: string;
  /** Oxidizer density. Unit: kg/m³ */
  readonly oxidizerDensity_kgm3: number;
  /** Internal volume. Unit: m³ */
  readonly volume_m3: number;
  /** Tank pressurization pressure. Unit: Pa */
  readonly pressurization_Pa: number;
}

export interface AvionicsDef extends BaseComponentDef {
  readonly category: 'avionics';
  /** Power consumption. Unit: W */
  readonly powerConsumption_W: number;
  /** Whether this provides flight computer capability. */
  readonly hasFlightComputer: boolean;
  /** Whether this provides telemetry downlink. */
  readonly hasTelemetry: boolean;
}

export interface GuidanceDef extends BaseComponentDef {
  readonly category: 'guidance';
  /** Power consumption. Unit: W */
  readonly powerConsumption_W: number;
  /** Guidance method. */
  readonly guidanceType: 'inertial' | 'gps' | 'star_tracker' | 'radio';
  /** Pointing accuracy. Unit: rad */
  readonly accuracy_rad: number;
}

/**
 * Fin planforms.
 *
 * The planform sets where the fin's own centre of pressure sits, which feeds
 * straight into the vehicle's static margin through the Barrowman equations.
 * A delta and a swept fin of the same area do not give the same stability.
 */
export type FinShape =
  | 'trapezoidal'
  | 'delta'
  | 'clipped_delta'
  | 'swept'
  | 'elliptical'
  | 'rectangular'
  | 'grid'
  | 'custom';

export interface FinDef extends BaseComponentDef {
  readonly category: 'fin';
  /** Number of fins in the set. */
  readonly finCount: number;
  /** Planform. Drives the drawn shape and the centre-of-pressure estimate. */
  readonly shape?: FinShape;
  /** Root chord length, where the fin meets the body. Unit: m */
  readonly rootChord_m: number;
  /** Tip chord length. Zero for a true delta. Unit: m */
  readonly tipChord_m: number;
  /** Span, measured from the body surface outwards. Unit: m */
  readonly span_m: number;
  /** Leading-edge sweep angle. Unit: rad */
  readonly sweepAngle_rad: number;
  /** Fin thickness. Unit: m */
  readonly thickness_m?: number;
  /** Airfoil profile. */
  readonly airfoil: 'flat' | 'symmetric' | 'cambered';
  /** Drag coefficient contribution per fin. Dimensionless. */
  readonly dragCoefficient: number;
  /**
   * Distance from the aft end of the parent body to the fin root's trailing
   * edge. Moving the set aft increases the static margin. Unit: m
   */
  readonly positionFromRear_m?: number;
  /** Material name. */
  readonly material?: string;
  /** Cant angle, for a set deliberately set to induce roll. Unit: rad */
  readonly cantAngle_rad?: number;
}

export interface PayloadDef extends BaseComponentDef {
  readonly category: 'payload';
  /** Whether mass is adjustable by the user. */
  readonly massAdjustable: boolean;
  /** Minimum payload mass if adjustable. Unit: kg */
  readonly minMass_kg: number;
  /** Maximum payload mass if adjustable. Unit: kg */
  readonly maxMass_kg: number;
  /** Payload type classification. */
  readonly payloadType: 'satellite' | 'crew_capsule' | 'probe' | 'cargo' | 'custom';
}

export interface DecouplerDef extends BaseComponentDef {
  readonly category: 'decoupler';
  /** Separation force. Unit: N */
  readonly separationForce_N: number;
  /** Time to separate. Unit: s */
  readonly separationTime_s: number;
  /** Whether this acts as the stage boundary. */
  readonly isStageSeparator: boolean;
}

export interface HeatShieldDef extends BaseComponentDef {
  readonly category: 'heat_shield';
  /** Ablative material thickness. Unit: m */
  readonly ablatorThickness_m: number;
  /** Maximum heat flux the shield can withstand. Unit: W/m² */
  readonly maxHeatFlux_Wm2: number;
  /** Shield diameter (may differ from mounting body). Unit: m */
  readonly shieldDiameter_m: number;
}

export interface LandingLegDef extends BaseComponentDef {
  readonly category: 'landing_leg';
  /** Number of legs in the set. */
  readonly legCount: number;
  /** Deployed length. Unit: m */
  readonly deployedLength_m: number;
  /** Maximum landing velocity the legs can absorb. Unit: m/s */
  readonly maxLandingVelocity_ms: number;
  /** Whether legs deploy automatically. */
  readonly autoDeployAltitude_m: number;
}

export interface ParachuteDef extends BaseComponentDef {
  readonly category: 'parachute';
  /** Canopy diameter when deployed. Unit: m */
  readonly canopyDiameter_m: number;
  /** Drag coefficient when deployed. Dimensionless. */
  readonly deployedDragCoefficient: number;
  /** Deployment altitude trigger. Unit: m */
  readonly deployAltitude_m: number;
  /** Minimum safe deployment speed. Unit: m/s */
  readonly minDeploySpeed_ms: number;
  /** Maximum safe deployment speed. Unit: m/s */
  readonly maxDeploySpeed_ms: number;
  /** Parachute type. */
  readonly parachuteType: 'drogue' | 'main' | 'drogue_main';
}

// ============================================================
// Airframe: couplers, interstages, fairings
// ============================================================

/**
 * A coupler joins two body tubes.
 *
 * It slips inside both, so its outer diameter is the *inner* diameter of the
 * tubes it links. Getting that backwards produces a design that cannot
 * physically be assembled, which is why validation checks it.
 */
export interface CouplerDef extends BaseComponentDef {
  readonly category: 'coupler';
  /** How far the coupler inserts into each tube. Unit: m */
  readonly insertionDepth_m: number;
  /** Wall thickness. Unit: m */
  readonly wallThickness_m: number;
  /** Material name. */
  readonly material: string;
  /** Whether the joint carries axial load, or only aligns the tubes. */
  readonly loadBearing: boolean;
}

/** The structure between two stages, carrying load until separation. */
export interface InterstageDef extends BaseComponentDef {
  readonly category: 'interstage';
  /** Diameter at the forward end, which may differ from aft. Unit: m */
  readonly forwardDiameter_m: number;
  /** Diameter at the aft end. Unit: m */
  readonly aftDiameter_m: number;
  /** Wall thickness. Unit: m */
  readonly wallThickness_m: number;
  readonly material: string;
  /** Whether the upper stage lights before separation. */
  readonly ventedForHotStaging: boolean;
}

/** A payload fairing: two halves that protect the payload and then leave. */
export interface FairingDef extends BaseComponentDef {
  readonly category: 'fairing';
  /** Internal diameter available to the payload. Unit: m */
  readonly usableDiameter_m: number;
  /** Internal length available to the payload. Unit: m */
  readonly usableLength_m: number;
  /** Number of separating halves. Almost always 2. */
  readonly segments: number;
  /** Altitude at which it is jettisoned. Unit: m */
  readonly jettisonAltitude_m: number;
  /** Nose profile of the fairing itself. */
  readonly shape: NoseConeShape;
  readonly material: string;
}

// ============================================================
// Structure: bulkheads, centering rings, motor mounts
// ============================================================

/** A disc closing off a tube section and carrying load across it. */
export interface BulkheadDef extends BaseComponentDef {
  readonly category: 'bulkhead';
  /** Thickness of the disc. Unit: m */
  readonly thickness_m: number;
  readonly material: string;
  /** Whether it seals the section against pressure. */
  readonly pressureSealing: boolean;
  /** Load it can transmit along the vehicle axis. Unit: N */
  readonly loadCapacity_N: number;
  /** Diameter of a central hole, for a bulkhead a shaft passes through. Unit: m */
  readonly boreDiameter_m: number;
}

/**
 * A ring that holds a smaller tube concentric inside a larger one.
 *
 * The usual job is holding a motor mount tube inside the airframe. It is a
 * small part with an outsized effect on where mass sits, which is why it is a
 * modelled component rather than a rounding error in the airframe mass.
 */
export interface CenteringRingDef extends BaseComponentDef {
  readonly category: 'centering_ring';
  /** Outer diameter, matching the airframe's inner diameter. Unit: m */
  readonly outerFitDiameter_m: number;
  /** Inner diameter, matching the tube it centres. Unit: m */
  readonly innerFitDiameter_m: number;
  readonly thickness_m: number;
  readonly material: string;
}

/** The tube an engine sits in, transferring its thrust into the airframe. */
export interface MotorMountDef extends BaseComponentDef {
  readonly category: 'motor_mount';
  /** Inner diameter, which the motor must fit inside. Unit: m */
  readonly motorDiameter_m: number;
  /** Length available for the motor. Unit: m */
  readonly motorLength_m: number;
  /** How many motors this mount holds. */
  readonly motorCount: number;
  /** Thrust it can transmit into the airframe. Unit: N */
  readonly thrustCapacity_N: number;
  /** Whether it includes a retainer that stops the motor being ejected. */
  readonly hasRetainer: boolean;
  readonly material: string;
}

// ============================================================
// Avionics and power
// ============================================================

/** What a sensor measures. */
export type SensorKind =
  | 'accelerometer'
  | 'gyroscope'
  | 'barometer'
  | 'magnetometer'
  | 'gps'
  | 'thermocouple'
  | 'pressure_transducer'
  | 'strain_gauge'
  | 'camera';

export interface SensorDef extends BaseComponentDef {
  readonly category: 'sensor';
  readonly sensorKind: SensorKind;
  /** Samples per second. Unit: Hz */
  readonly sampleRate_Hz: number;
  /** Full-scale range, in whatever unit the sensor measures. */
  readonly range: number;
  readonly rangeUnit: string;
  /** Measurement accuracy, in the same unit. */
  readonly accuracy: number;
  readonly powerConsumption_W: number;
}

export interface BatteryDef extends BaseComponentDef {
  readonly category: 'battery';
  /** Stored energy. Unit: W·h */
  readonly capacity_Wh: number;
  /** Nominal terminal voltage. Unit: V */
  readonly voltage_V: number;
  /** Peak current it can deliver. Unit: A */
  readonly maxCurrent_A: number;
  readonly chemistry: 'lipo' | 'li_ion' | 'nimh' | 'alkaline' | 'silver_zinc';
  /** Lowest temperature at which it still delivers rated capacity. Unit: K */
  readonly minOperatingTemperature_K: number;
}

// ============================================================
// User-defined parts
// ============================================================

/**
 * A component the user defined themselves.
 *
 * The schema has to stay open to parts nobody anticipated, and it has to do
 * that without letting an imported project file introduce a component type the
 * physics has no model for. The compromise: a custom component contributes
 * mass at a position and a drag area, which every part does, and declares
 * nothing the engine would have to interpret.
 */
export interface CustomComponentDef extends BaseComponentDef {
  readonly category: 'custom';
  /** Free-text classification, for display only. Never interpreted. */
  readonly kindLabel: string;
  /** Frontal area contributed to drag. Unit: m² */
  readonly dragArea_m2: number;
  /** Drag coefficient contribution. Dimensionless. */
  readonly dragCoefficient: number;
  readonly material: string;
  /** User notes. */
  readonly notes: string;
}

// ============================================================
// Discriminated Union
// ============================================================

/** A component definition — discriminated by `category`. */
export type ComponentDef =
  | BodyDef
  | NoseConeDef
  | FairingDef
  | CouplerDef
  | InterstageDef
  | EngineDef
  | MotorMountDef
  | FuelTankDef
  | OxidizerTankDef
  | FinDef
  | BulkheadDef
  | CenteringRingDef
  | AvionicsDef
  | GuidanceDef
  | SensorDef
  | BatteryDef
  | PayloadDef
  | DecouplerDef
  | ParachuteDef
  | HeatShieldDef
  | LandingLegDef
  | CustomComponentDef;

// ============================================================
// Placed Component (instance in a design)
// ============================================================

/** A component placed within a RocketDesign. */
export interface PlacedComponent {
  /** Unique instance ID within the design. */
  readonly instanceId: string;
  /** Reference to the component definition. */
  readonly defId: string;
  /** Stage this component belongs to. */
  readonly stageIndex: number;
  /** Position offset relative to stage origin. Unit: m */
  readonly offset_x: number;
  readonly offset_y: number;
  readonly offset_z: number;
  /** Configuration overrides (e.g. adjusted payload mass). */
  readonly configOverrides: Readonly<Record<string, number>>;
}

// ============================================================
// Connection between components
// ============================================================

export type ConnectionType = 'structural' | 'fuel_line' | 'electrical' | 'staging';

/** A connection between two placed components. */
export interface Connection {
  /** Unique connection ID. */
  readonly id: string;
  /** Instance ID of the source component. */
  readonly fromInstanceId: string;
  /** Attachment point ID on the source. */
  readonly fromAttachmentId: string;
  /** Instance ID of the target component. */
  readonly toInstanceId: string;
  /** Attachment point ID on the target. */
  readonly toAttachmentId: string;
  /** Type of connection. */
  readonly type: ConnectionType;
}

// ============================================================
// Stage
// ============================================================

/** A stage within a rocket design. */
export interface DesignStage {
  /** Stage index (0-based, 0 = bottom/first to fire). */
  readonly index: number;
  /** Human-readable name. */
  readonly name: string;
  /** Separation order (lower fires first). */
  readonly separationOrder: number;
  /** Delay after previous stage burnout before this stage ignites. Unit: s */
  readonly ignitionDelay_s: number;
}

// ============================================================
// Rocket Design
// ============================================================

/** A complete rocket design — the output of the builder. */
export interface RocketDesign {
  /** Unique design ID. */
  readonly id: string;
  /** Human-readable name. */
  readonly name: string;
  /** Design description. */
  readonly description: string;
  /** Ordered stages (index 0 = bottom). */
  readonly stages: readonly DesignStage[];
  /** All placed components. */
  readonly components: readonly PlacedComponent[];
  /** All connections between components. */
  readonly connections: readonly Connection[];
  /** Design creation timestamp (ISO string). */
  readonly createdAt: string;
  /** Last modification timestamp (ISO string). */
  readonly updatedAt: string;
}

// ============================================================
// Mission & Celestial Body
// ============================================================

/** A celestial body that can be a mission target or gravity source. */
export interface CelestialBody {
  readonly id: string;
  readonly name: string;
  /** Mass. Unit: kg */
  readonly mass_kg: number;
  /** Mean radius. Unit: m */
  readonly radius_m: number;
  /** Surface gravity. Unit: m/s² */
  readonly surfaceGravity_ms2: number;
  /** Whether this body has an atmosphere. */
  readonly hasAtmosphere: boolean;
  /** Atmospheric scale height (0 if no atmosphere). Unit: m */
  readonly atmosphereScaleHeight_m: number;
  /** Surface pressure (0 if no atmosphere). Unit: Pa */
  readonly surfacePressure_Pa: number;
  /** Mean orbital radius around parent body. Unit: m */
  readonly orbitalRadius_m: number;
  /** Sidereal rotation period. Unit: s */
  readonly rotationPeriod_s: number;
  /** Parent body ID (null for the Sun). */
  readonly parentBodyId: string | null;
  /** Visual asset reference. */
  readonly visual: VisualAssetRef;
}

/** Full mission configuration (extends sim-layer MissionConfig). */
export interface MissionConfiguration {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  /** Target celestial body. */
  readonly targetBody: CelestialBody;
  /** Mission type. */
  readonly missionType: 'suborbital' | 'orbital' | 'transfer' | 'landing' | 'flyby';
  /** Target altitude above body surface. Unit: m */
  readonly targetAltitude_m: number;
  /** Target orbital inclination. Unit: rad */
  readonly targetInclination_rad: number;
  /** Launch site specification. */
  readonly launchSite: {
    readonly name: string;
    readonly latitude_deg: number;
    readonly longitude_deg: number;
    readonly altitude_m: number;
  };
  /** Launch environment. */
  readonly environment: {
    readonly temperature_K: number;
    readonly pressure_Pa: number;
    readonly windSpeed_ms: number;
    readonly windDirection_rad: number;
  };
  /** Associated rocket design ID. */
  readonly rocketDesignId: string;
}

// ============================================================
// Failure Definition
// ============================================================

/** A structured failure definition for the failure engine. */
export interface FailureDefinition {
  readonly id: string;
  readonly name: string;
  readonly description: string;
  /** Which subsystem this failure affects. */
  readonly subsystem: 'propulsion' | 'structure' | 'aerodynamics' | 'thermal' | 'avionics' | 'recovery';
  /** What triggers this failure. */
  readonly triggerType: 'threshold_exceeded' | 'duration_exceeded' | 'state_mismatch' | 'random';
  /** Parameter to monitor. */
  readonly monitoredParameter: string;
  /** Threshold value. */
  readonly threshold: number;
  /** Threshold unit for display. */
  readonly thresholdUnit: string;
  /** Severity. */
  readonly severity: 'warning' | 'critical' | 'fatal';
  /** Consequence description. */
  readonly consequence: string;
  /** Educational explanation for students. */
  readonly educationalExplanation: string;
  /** Recommended fix. */
  readonly recommendedFix: string;
  /** Related lesson slugs. */
  readonly relatedLessons: readonly string[];
}
