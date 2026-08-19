/**
 * `.rkt` project file format.
 *
 * The portable save format described in `docs/rkt_spec/RKT_SPEC.md`: a JSON
 * document holding a project's mission, vehicle, and configuration. It is what
 * a user downloads, shares, and re-opens, and what makes an offline demo
 * possible.
 *
 * ## Reading untrusted files
 *
 * A `.rkt` file arrives from a user's disk or from another user, so
 * {@link parseRkt} treats it as hostile input:
 *
 * - size is capped before parsing,
 * - the parsed value is checked field by field against expected types,
 * - numeric fields are range-checked against physical plausibility,
 * - strings are length-capped,
 * - unknown top-level keys are dropped rather than carried through.
 *
 * Nothing in a `.rkt` file is ever evaluated, and no field is used to construct
 * a path, a URL, or a query.
 *
 * @module integration/rkt
 */

import type { RocketDesign } from '../core/component-types.js';
import type { MissionConfig } from '../core/types.js';
import type { SimSettings } from '../sim/config.js';

/** Format version this build writes. */
export const RKT_VERSION = '1.0';

/** Largest file this parser will consider. Unit: bytes. */
export const RKT_MAX_BYTES = 10 * 1024 * 1024;

/** Longest string accepted in any text field. */
const MAX_STRING_LENGTH = 4_000;

/** A parsed project file. */
export interface RktFile {
  readonly rkt_version: string;
  readonly generator: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly project: {
    readonly name: string;
    readonly description: string;
    readonly author: string;
  };
  readonly mission: MissionConfig;
  readonly design: RocketDesign;
  readonly simulation_settings: Partial<SimSettings>;
  readonly educational_metadata: {
    readonly difficulty: 'beginner' | 'intermediate' | 'advanced';
    readonly concepts_covered: readonly string[];
    readonly related_lessons: readonly string[];
  };
}

/** Options for {@link serializeRkt}. */
export interface SerializeRktOptions {
  readonly projectName?: string;
  readonly description?: string;
  readonly author?: string;
  readonly createdAt?: string;
  readonly updatedAt?: string;
  readonly simulationSettings?: Partial<SimSettings>;
  readonly difficulty?: 'beginner' | 'intermediate' | 'advanced';
  readonly conceptsCovered?: readonly string[];
  readonly relatedLessons?: readonly string[];
}

/**
 * Serialize a project to `.rkt` JSON.
 *
 * @param design - The rocket design.
 * @param mission - The mission configuration.
 * @param options - Project metadata.
 * @returns Pretty-printed JSON, ready to write to a file.
 */
export function serializeRkt(
  design: RocketDesign,
  mission: MissionConfig,
  options: SerializeRktOptions = {},
): string {
  const now = new Date().toISOString();

  const file: RktFile = {
    rkt_version: RKT_VERSION,
    generator: '@lostintospace/simulation-engine 0.1.0',
    created_at: options.createdAt ?? design.createdAt ?? now,
    updated_at: options.updatedAt ?? now,
    project: {
      name: options.projectName ?? design.name,
      description: options.description ?? design.description,
      author: options.author ?? '',
    },
    mission,
    design,
    simulation_settings: options.simulationSettings ?? {},
    educational_metadata: {
      difficulty: options.difficulty ?? 'beginner',
      concepts_covered: options.conceptsCovered ?? [],
      related_lessons: options.relatedLessons ?? [],
    },
  };

  return JSON.stringify(file, null, 2);
}

/** What went wrong while parsing. */
export interface RktParseError {
  /** Which field, in dotted path form. */
  readonly path: string;
  /** What was wrong with it. */
  readonly message: string;
}

/** Result of parsing a `.rkt` file. */
export type RktParseResult =
  | { readonly ok: true; readonly file: RktFile }
  | { readonly ok: false; readonly errors: readonly RktParseError[] };

/** Accumulates errors while walking an untrusted object. */
class Validator {
  readonly errors: RktParseError[] = [];

  /** Record a problem. */
  fail(path: string, message: string): void {
    this.errors.push({ path, message });
  }

  /** Read a string, capped in length. */
  str(value: unknown, path: string, fallback = ''): string {
    if (value === undefined || value === null) return fallback;
    if (typeof value !== 'string') {
      this.fail(path, `expected a string, got ${typeof value}`);
      return fallback;
    }
    if (value.length > MAX_STRING_LENGTH) {
      this.fail(path, `string exceeds ${MAX_STRING_LENGTH} characters`);
      return value.slice(0, MAX_STRING_LENGTH);
    }
    return value;
  }

  /** Read a finite number, optionally range-checked. */
  num(value: unknown, path: string, min = -Infinity, max = Infinity, fallback = 0): number {
    if (value === undefined || value === null) return fallback;
    if (typeof value !== 'number' || !Number.isFinite(value)) {
      this.fail(path, 'expected a finite number');
      return fallback;
    }
    if (value < min || value > max) {
      this.fail(path, `value ${value} is outside the allowed range [${min}, ${max}]`);
      return Math.min(max, Math.max(min, value));
    }
    return value;
  }

  /** Read a plain object. */
  obj(value: unknown, path: string): Record<string, unknown> {
    if (typeof value !== 'object' || value === null || Array.isArray(value)) {
      this.fail(path, 'expected an object');
      return {};
    }
    return value as Record<string, unknown>;
  }

  /** Read an array. */
  arr(value: unknown, path: string): unknown[] {
    if (!Array.isArray(value)) {
      this.fail(path, 'expected an array');
      return [];
    }
    return value;
  }
}

/**
 * Parse and validate a `.rkt` file.
 *
 * Never throws: malformed input comes back as `{ ok: false, errors }` so the UI
 * can tell the user exactly which field is wrong.
 *
 * @param json - Raw file contents.
 * @returns The parsed file, or the list of problems.
 */
export function parseRkt(json: string): RktParseResult {
  // Size first, before handing anything to the JSON parser.
  if (json.length > RKT_MAX_BYTES) {
    return {
      ok: false,
      errors: [
        {
          path: '',
          message: `File is ${json.length} bytes, above the ${RKT_MAX_BYTES} byte limit`,
        },
      ],
    };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch (error) {
    return {
      ok: false,
      errors: [
        { path: '', message: `Not valid JSON: ${(error as Error).message}` },
      ],
    };
  }

  const v = new Validator();
  const root = v.obj(parsed, '');

  const version = v.str(root['rkt_version'], 'rkt_version');
  if (version !== RKT_VERSION) {
    v.fail('rkt_version', `unsupported version "${version}", expected "${RKT_VERSION}"`);
  }

  const projectRaw = v.obj(root['project'], 'project');
  const educational = v.obj(root['educational_metadata'], 'educational_metadata');

  // Every field is read *before* the error gate below. Reading some of them
  // afterwards would let their validation failures — an over-long string, a
  // wrong type — be recorded into a list nothing ever inspects again.
  const generator = v.str(root['generator'], 'generator');
  const createdAt = v.str(root['created_at'], 'created_at');
  const updatedAt = v.str(root['updated_at'], 'updated_at');
  const project = {
    name: v.str(projectRaw['name'], 'project.name', 'Untitled'),
    description: v.str(projectRaw['description'], 'project.description'),
    author: v.str(projectRaw['author'], 'project.author'),
  };
  const difficulty = v.str(
    educational['difficulty'],
    'educational_metadata.difficulty',
    'beginner',
  );
  const mission = parseMission(v, root['mission']);
  const design = parseDesign(v, root['design']);

  if (v.errors.length > 0) {
    return { ok: false, errors: v.errors };
  }

  return {
    ok: true,
    file: {
      rkt_version: version,
      generator,
      created_at: createdAt,
      updated_at: updatedAt,
      project,
      mission,
      design,
      // Settings are re-derived through `createSimConfig`, which fills every
      // field from defaults, so a partial object here is safe.
      simulation_settings: (root['simulation_settings'] ?? {}) as Partial<SimSettings>,
      educational_metadata: {
        difficulty:
          difficulty === 'intermediate' || difficulty === 'advanced'
            ? difficulty
            : 'beginner',
        concepts_covered: v
          .arr(educational['concepts_covered'] ?? [], 'educational_metadata.concepts_covered')
          .filter((x): x is string => typeof x === 'string'),
        related_lessons: v
          .arr(educational['related_lessons'] ?? [], 'educational_metadata.related_lessons')
          .filter((x): x is string => typeof x === 'string'),
      },
    },
  };
}

/** Validate the mission block. */
function parseMission(v: Validator, raw: unknown): MissionConfig {
  const m = v.obj(raw, 'mission');
  const target = v.obj(m['target'], 'mission.target');
  const site = v.obj(m['launchSite'], 'mission.launchSite');
  const environment = v.obj(m['environment'], 'mission.environment');

  const targetType = v.str(target['type'], 'mission.target.type', 'suborbital');
  const allowedTypes = ['suborbital', 'leo', 'meo', 'geo', 'escape'];
  if (!allowedTypes.includes(targetType)) {
    v.fail('mission.target.type', `unknown mission type "${targetType}"`);
  }

  return {
    name: v.str(m['name'], 'mission.name', 'Untitled Mission'),
    objective: v.str(m['objective'], 'mission.objective'),
    target: {
      type: targetType as MissionConfig['target']['type'],
      // A target above geosynchronous altitude is out of scope for this engine.
      targetAltitude_km: v.num(target['targetAltitude_km'], 'mission.target.targetAltitude_km', 0, 400_000, 100),
      inclination_deg: v.num(target['inclination_deg'], 'mission.target.inclination_deg', -180, 180, 0),
    },
    launchSite: {
      name: v.str(site['name'], 'mission.launchSite.name', 'Unnamed Site'),
      latitude_deg: v.num(site['latitude_deg'], 'mission.launchSite.latitude_deg', -90, 90, 0),
      longitude_deg: v.num(site['longitude_deg'], 'mission.launchSite.longitude_deg', -180, 180, 0),
      // Highest land on Earth is under 9 km; anything above that is a bad file.
      altitude_m: v.num(site['altitude_m'], 'mission.launchSite.altitude_m', -500, 9_000, 0),
    },
    environment: {
      temperature_K: v.num(environment['temperature_K'], 'mission.environment.temperature_K', 150, 350, 288.15),
      pressure_Pa: v.num(environment['pressure_Pa'], 'mission.environment.pressure_Pa', 0, 120_000, 101_325),
      windSpeed_ms: v.num(environment['windSpeed_ms'], 'mission.environment.windSpeed_ms', 0, 150, 0),
      windDirection_deg: v.num(environment['windDirection_deg'], 'mission.environment.windDirection_deg', 0, 360, 0),
    },
  };
}

/** Validate the design block. */
function parseDesign(v: Validator, raw: unknown): RocketDesign {
  const d = v.obj(raw, 'design');

  const stages = v.arr(d['stages'] ?? [], 'design.stages').map((entry, i) => {
    const s = v.obj(entry, `design.stages[${i}]`);
    return {
      index: v.num(s['index'], `design.stages[${i}].index`, 0, 20, i),
      name: v.str(s['name'], `design.stages[${i}].name`, `Stage ${i}`),
      separationOrder: v.num(s['separationOrder'], `design.stages[${i}].separationOrder`, 0, 20, i),
      ignitionDelay_s: v.num(s['ignitionDelay_s'], `design.stages[${i}].ignitionDelay_s`, 0, 3_600, 0),
    };
  });

  if (stages.length === 0) {
    v.fail('design.stages', 'a design must have at least one stage');
  }

  const components = v.arr(d['components'] ?? [], 'design.components').map((entry, i) => {
    const c = v.obj(entry, `design.components[${i}]`);
    const overridesRaw = v.obj(c['configOverrides'] ?? {}, `design.components[${i}].configOverrides`);

    // Only finite numbers survive; anything else is discarded rather than
    // carried into the analysis where it would produce NaN.
    const configOverrides: Record<string, number> = {};
    for (const [key, value] of Object.entries(overridesRaw)) {
      if (typeof value === 'number' && Number.isFinite(value)) {
        configOverrides[key] = value;
      }
    }

    return {
      instanceId: v.str(c['instanceId'], `design.components[${i}].instanceId`, `comp_${i}`),
      defId: v.str(c['defId'], `design.components[${i}].defId`),
      stageIndex: v.num(c['stageIndex'], `design.components[${i}].stageIndex`, 0, 20, 0),
      offset_x: v.num(c['offset_x'], `design.components[${i}].offset_x`, -1_000, 1_000, 0),
      offset_y: v.num(c['offset_y'], `design.components[${i}].offset_y`, -1_000, 1_000, 0),
      offset_z: v.num(c['offset_z'], `design.components[${i}].offset_z`, -1_000, 1_000, 0),
      configOverrides,
    };
  });

  const connections = v.arr(d['connections'] ?? [], 'design.connections').map((entry, i) => {
    const c = v.obj(entry, `design.connections[${i}]`);
    const type = v.str(c['type'], `design.connections[${i}].type`, 'structural');
    const allowed = ['structural', 'fuel_line', 'electrical', 'staging'];
    return {
      id: v.str(c['id'], `design.connections[${i}].id`, `conn_${i}`),
      fromInstanceId: v.str(c['fromInstanceId'], `design.connections[${i}].fromInstanceId`),
      fromAttachmentId: v.str(c['fromAttachmentId'], `design.connections[${i}].fromAttachmentId`),
      toInstanceId: v.str(c['toInstanceId'], `design.connections[${i}].toInstanceId`),
      toAttachmentId: v.str(c['toAttachmentId'], `design.connections[${i}].toAttachmentId`),
      type: (allowed.includes(type) ? type : 'structural') as RocketDesign['connections'][number]['type'],
    };
  });

  return {
    id: v.str(d['id'], 'design.id', 'imported'),
    name: v.str(d['name'], 'design.name', 'Imported Rocket'),
    description: v.str(d['description'], 'design.description'),
    stages,
    components,
    connections,
    createdAt: v.str(d['createdAt'], 'design.createdAt'),
    updatedAt: v.str(d['updatedAt'], 'design.updatedAt'),
  };
}

/**
 * Check that every component a file references exists in the local catalogue.
 *
 * A `.rkt` file carries component *ids*, not definitions, so a file built
 * against a newer catalogue can reference parts this build has never heard of.
 * Loading it anyway would silently produce a lighter, weaker rocket than the
 * author designed, so callers should check first and tell the user what is
 * missing.
 *
 * @param file - The parsed file.
 * @param availableIds - Component ids the local registry holds.
 * @returns Ids the file needs that are not available.
 */
export function findMissingComponents(
  file: RktFile,
  availableIds: readonly string[],
): string[] {
  const available = new Set(availableIds);
  const missing = new Set<string>();

  for (const component of file.design.components) {
    if (!available.has(component.defId)) missing.add(component.defId);
  }

  return [...missing].sort();
}
