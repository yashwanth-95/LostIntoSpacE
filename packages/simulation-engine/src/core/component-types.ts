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
  'body', 'nose_cone', 'engine', 'fuel_tank', 'oxidizer_tank',
  'avionics', 'guidance', 'fin', 'payload', 'decoupler',
  'heat_shield', 'landing_leg', 'parachute',
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

export interface NoseConeDef extends BaseComponentDef {
  readonly category: 'nose_cone';
  /** Nose cone shape profile. */
  readonly shape: 'conical' | 'ogive' | 'parabolic' | 'haack';
  /** Fineness ratio (length / base diameter). Dimensionless. */
  readonly finenessRatio: number;
  /** Drag coefficient contribution. Dimensionless. */
  readonly dragCoefficient: number;
}

export interface EngineDef extends BaseComponentDef {
  readonly category: 'engine';
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

export interface FinDef extends BaseComponentDef {
  readonly category: 'fin';
  /** Number of fins in the set. */
  readonly finCount: number;
  /** Root chord length. Unit: m */
  readonly rootChord_m: number;
  /** Tip chord length. Unit: m */
  readonly tipChord_m: number;
  /** Span (height from body surface). Unit: m */
  readonly span_m: number;
  /** Sweep angle. Unit: rad */
  readonly sweepAngle_rad: number;
  /** Airfoil profile. */
  readonly airfoil: 'flat' | 'symmetric' | 'cambered';
  /** Drag coefficient contribution per fin. Dimensionless. */
  readonly dragCoefficient: number;
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
// Discriminated Union
// ============================================================

/** A component definition — discriminated by `category`. */
export type ComponentDef =
  | BodyDef
  | NoseConeDef
  | EngineDef
  | FuelTankDef
  | OxidizerTankDef
  | AvionicsDef
  | GuidanceDef
  | FinDef
  | PayloadDef
  | DecouplerDef
  | HeatShieldDef
  | LandingLegDef
  | ParachuteDef;

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
