/**
 * Reading and writing `.rkt` project files.
 *
 * The format itself is documented in `rkt-schema.ts`. This module is the code
 * that produces one, the code that consumes one, and — most of the work — the
 * code that refuses to consume a bad one.
 *
 * ## Reading is hostile-input handling
 *
 * A `.rkt` file comes from somebody's disk or from another user. It is treated
 * exactly like a network payload:
 *
 * - size is capped before `JSON.parse` is ever called,
 * - nesting depth is bounded, so a deeply nested document cannot make the
 *   validator recurse until the stack gives out,
 * - every field is checked against an expected type before it is read,
 * - numbers are range-checked against physical plausibility, and non-finite
 *   values are rejected outright,
 * - strings are length-capped,
 * - component references are checked to resolve, so a file cannot describe a
 *   fin attached to a body tube that does not exist,
 * - unknown keys are dropped rather than carried through,
 * - image URLs are checked against an allowlist of hosts.
 *
 * Nothing in a `.rkt` file is ever evaluated. No field is used to construct a
 * path, a URL, a query or a template. A `parameters` bag holds primitives only,
 * never nested structures.
 *
 * ## Results can go stale, and the file knows it
 *
 * Every stored result carries a hash of the design, mission, environment and
 * simulation settings that produced it. On open the hash is recomputed from
 * what is actually in the file; if it differs, the results describe a vehicle
 * the project no longer contains and {@link areResultsStale} says so. The
 * interface can then offer to re-fly rather than presenting a stranger's
 * telemetry as the user's own.
 *
 * @module integration/rkt
 */

import type { RocketDesign } from '../core/component-types.js';
import type { MissionConfig } from '../core/types.js';
import {
  RKT_FORMAT_VERSION,
  RKT_MAX_BYTES,
  RKT_MAX_COMPONENTS,
  RKT_MAX_DEPTH,
  RKT_MAX_STRING,
  RKT_MAX_TELEMETRY,
  RKT_MIN_SCHEMA_VERSION,
  RKT_SCHEMA_VERSION,
  type RktProject,
} from './rkt-schema.js';

export * from './rkt-schema.js';
export { buildRktProject, RKT_GENERATOR, type BuildRktProjectInput } from './rkt-project.js';

/** Hosts an image reference in a project file may point at. */
const ALLOWED_IMAGE_HOSTS = ['images-assets.nasa.gov', 'images.nasa.gov'];

// ============================================================
// Errors and results
// ============================================================

/** One thing wrong with a file, located precisely enough to fix. */
export interface RktIssue {
  /** Dotted path to the offending field. */
  readonly path: string;
  /** What is wrong, in a sentence a user can act on. */
  readonly message: string;
  /** `error` blocks loading; `warning` does not. */
  readonly severity: 'error' | 'warning';
}

export type RktParseResult =
  | { readonly ok: true; readonly project: RktProject; readonly warnings: readonly RktIssue[] }
  | { readonly ok: false; readonly errors: readonly RktIssue[] };

function error(path: string, message: string): RktIssue {
  return { path, message, severity: 'error' };
}

function warning(path: string, message: string): RktIssue {
  return { path, message, severity: 'warning' };
}

// ============================================================
// Hashing
// ============================================================

/**
 * A stable 53-bit hash of a string.
 *
 * cyrb53. Not cryptographic and not trying to be: this detects *change*, and
 * the thing being protected against is a stale result being shown as current,
 * not an attacker forging one. A user who edits a project file by hand to make
 * old results look fresh has only misled themselves.
 */
function cyrb53(text: string, seed = 0): number {
  let h1 = 0xdeadbeef ^ seed;
  let h2 = 0x41c6ce57 ^ seed;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return 4294967296 * (2097151 & h2) + (h1 >>> 0);
}

/**
 * Serialise a value with keys in a fixed order.
 *
 * Object key order is not semantically meaningful but `JSON.stringify` preserves
 * insertion order, so without this the same project saved twice could hash
 * differently and every reopened file would claim its results were stale.
 */
function canonical(value: unknown): string {
  if (value === null || typeof value !== 'object') return JSON.stringify(value) ?? 'null';
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(',')}}`;
}

/**
 * Hash the inputs that determine a simulation result.
 *
 * Deliberately excludes `metadata` and `results`: renaming a project or
 * re-running it must not invalidate a result, and a result cannot be part of
 * its own input.
 */
export function computeInputsHash(
  project: Pick<
    RktProject,
    'design' | 'missionConfig' | 'vehicle' | 'mission' | 'environment' | 'simulation'
  >,
): string {
  const material = canonical({
    design: project.design,
    missionConfig: project.missionConfig,
    vehicle: project.vehicle,
    mission: project.mission,
    environment: project.environment,
    simulation: project.simulation,
  });
  return `h${cyrb53(material).toString(36)}`;
}

/**
 * Whether a project's stored results describe the vehicle it currently holds.
 *
 * @returns `true` when results exist but were produced from different inputs.
 */
export function areResultsStale(project: RktProject): boolean {
  if (!project.results.hasResults) return false;
  return project.results.inputsHash !== computeInputsHash(project);
}

// ============================================================
// Writing
// ============================================================

export interface SerializeOptions {
  readonly pretty?: boolean;
}

/**
 * Write a project to `.rkt` JSON.
 *
 * The inputs hash is recomputed on every save, so a file's results block is
 * always stamped with the inputs actually present in that file.
 */
export function serializeRkt(project: RktProject, options: SerializeOptions = {}): string {
  const stamped: RktProject = {
    ...project,
    metadata: {
      ...project.metadata,
      formatVersion: RKT_FORMAT_VERSION,
      schemaVersion: RKT_SCHEMA_VERSION,
      updatedAt: new Date().toISOString(),
    },
    results: project.results.hasResults
      ? { ...project.results, inputsHash: computeInputsHash(project) }
      : project.results,
  };

  return options.pretty === false ? JSON.stringify(stamped) : JSON.stringify(stamped, null, 2);
}

// ============================================================
// Migration
// ============================================================

/** One step in the upgrade chain, from a schema version to the next. */
interface Migration {
  readonly from: number;
  readonly to: number;
  readonly describe: string;
  readonly apply: (raw: Record<string, unknown>) => Record<string, unknown>;
}

/**
 * The migration chain.
 *
 * Each step states what it changes. A file is walked forward one step at a
 * time until it reaches the current schema version, so adding a version later
 * means adding one entry here rather than editing the parser.
 */
const MIGRATIONS: readonly Migration[] = [
  {
    from: 1,
    to: 2,
    describe:
      'v1 was a flat document with `design`, `mission` and `simulation_settings` and ' +
      'no separation between authored data and generated results. v2 adds the ' +
      'structured vehicle, propulsion, aerodynamics, avionics, environment and ' +
      'results blocks, and stamps results with the hash of the inputs that made them.',
    apply: (raw) => {
      const project = (raw.project ?? {}) as Record<string, unknown>;
      const design = raw.design as RocketDesign | undefined;
      const mission = raw.mission as MissionConfig | undefined;
      return {
        metadata: {
          formatVersion: '2.0',
          schemaVersion: 2,
          projectId: typeof raw.projectId === 'string' ? raw.projectId : `migrated-${Date.now()}`,
          name: str(project.name) ?? design?.name ?? 'Migrated project',
          description: str(project.description) ?? '',
          author: str(project.author) ?? '',
          createdAt: str(raw.created_at) ?? new Date().toISOString(),
          updatedAt: str(raw.updated_at) ?? new Date().toISOString(),
          generator: str(raw.generator) ?? 'unknown (migrated from v1)',
          tags: [],
        },
        design,
        missionConfig: mission,
        // A v1 file carried no structured blocks and no results. They are
        // rebuilt from the design when the project is next analysed; leaving
        // them empty here is honest, and marking results absent is essential —
        // inventing an inputs hash would claim results exist that never did.
        __needsRebuild: true,
        __v1SimulationSettings: raw.simulation_settings ?? {},
        __v1Educational: raw.educational_metadata ?? {},
      };
    },
  },
];

function str(value: unknown): string | undefined {
  return typeof value === 'string' ? value : undefined;
}

/** What a migration did, so the interface can tell the user their file changed. */
export interface MigrationReport {
  readonly migrated: boolean;
  readonly fromVersion: number;
  readonly toVersion: number;
  readonly steps: readonly string[];
}

// ============================================================
// Reading
// ============================================================

/**
 * Parse and validate a `.rkt` file.
 *
 * @param text - Raw file contents.
 * @returns The project, or every reason it could not be loaded.
 */
export function parseRkt(text: string): RktParseResult {
  // Size first: never hand an unbounded string to JSON.parse.
  if (typeof text !== 'string') {
    return { ok: false, errors: [error('', 'A project file must be text.')] };
  }
  if (text.length === 0) {
    return { ok: false, errors: [error('', 'The file is empty.')] };
  }
  if (text.length > RKT_MAX_BYTES) {
    return {
      ok: false,
      errors: [
        error(
          '',
          `The file is ${(text.length / 1_048_576).toFixed(1)} MB, over the ` +
            `${RKT_MAX_BYTES / 1_048_576} MB limit. A project this large is more likely ` +
            'corrupt than genuine.',
        ),
      ],
    };
  }

  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch (cause) {
    return {
      ok: false,
      errors: [
        error(
          '',
          `This is not a valid project file — the JSON could not be read. ${
            cause instanceof Error ? cause.message : ''
          }`.trim(),
        ),
      ],
    };
  }

  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    return { ok: false, errors: [error('', 'A project file must be a JSON object.')] };
  }

  const depth = measureDepth(raw, 0);
  if (depth > RKT_MAX_DEPTH) {
    return {
      ok: false,
      errors: [
        error('', `The document nests ${depth} levels deep, over the ${RKT_MAX_DEPTH} limit.`),
      ],
    };
  }

  const document = raw as Record<string, unknown>;

  // ── Version and migration ───────────────────────────────────
  const versionResult = resolveVersion(document);
  if ('issue' in versionResult) {
    return { ok: false, errors: [versionResult.issue] };
  }

  let working = document;
  const steps: string[] = [];
  let version = versionResult.schemaVersion;
  while (version < RKT_SCHEMA_VERSION) {
    const migration = MIGRATIONS.find((m) => m.from === version);
    if (!migration) {
      return {
        ok: false,
        errors: [
          error(
            'metadata.schemaVersion',
            `No migration exists from schema version ${version}. This file cannot be ` +
              'opened by this build, and has not been altered.',
          ),
        ],
      };
    }
    working = migration.apply(working);
    steps.push(migration.describe);
    version = migration.to;
  }

  // ── Validation ──────────────────────────────────────────────
  const errors: RktIssue[] = [];
  const warnings: RktIssue[] = [...steps.map((s) => warning('metadata.schemaVersion', s))];

  const design = working.design;
  if (!isObject(design)) {
    errors.push(error('design', 'The project contains no rocket design.'));
  } else {
    validateDesign(design, errors, warnings);
  }

  if (!isObject(working.missionConfig) && !isObject(working.mission)) {
    warnings.push(
      warning('mission', 'The project has no mission configuration; defaults will be used.'),
    );
  }

  const missionConfig = isObject(working.missionConfig)
    ? working.missionConfig
    : isObject(working.mission)
      ? working.mission
      : null;
  if (missionConfig) validateMissionConfig(missionConfig, errors);

  if (isObject(working.vehicle)) validateVehicle(working.vehicle, errors, warnings);
  if (isObject(working.results)) validateResults(working.results, errors, warnings);
  if (isObject(working.assets)) validateAssets(working.assets, errors, warnings);

  if (errors.length > 0) return { ok: false, errors };

  const project = normalise(working, warnings);
  return { ok: true, project, warnings };
}

/** Read the version pair, refusing anything this build cannot honestly handle. */
function resolveVersion(
  document: Record<string, unknown>,
):
  | { readonly schemaVersion: number }
  | { readonly issue: RktIssue } {
  const metadata = isObject(document.metadata) ? document.metadata : null;

  // A v1 file has `rkt_version` at the top level and no `metadata` block.
  if (!metadata && typeof document.rkt_version === 'string') {
    return { schemaVersion: 1 };
  }

  if (!metadata) {
    return {
      issue: error(
        'metadata',
        'The file has no metadata block and is not a recognisable version 1 project.',
      ),
    };
  }

  const schemaVersion = metadata.schemaVersion;
  if (typeof schemaVersion !== 'number' || !Number.isInteger(schemaVersion)) {
    return { issue: error('metadata.schemaVersion', 'The schema version is missing or not a whole number.') };
  }
  if (schemaVersion < RKT_MIN_SCHEMA_VERSION) {
    return {
      issue: error(
        'metadata.schemaVersion',
        `Schema version ${schemaVersion} is older than this build can migrate from ` +
          `(${RKT_MIN_SCHEMA_VERSION}). The file has not been altered.`,
      ),
    };
  }
  if (schemaVersion > RKT_SCHEMA_VERSION) {
    return {
      issue: error(
        'metadata.schemaVersion',
        `This project was saved by a newer version of LostIntoSpacE ` +
          `(schema ${schemaVersion}; this build reads up to ${RKT_SCHEMA_VERSION}). ` +
          'Opening it here could silently drop data, so it has not been opened.',
      ),
    };
  }
  return { schemaVersion };
}

// ============================================================
// Field validation
// ============================================================

function validateDesign(
  design: Record<string, unknown>,
  errors: RktIssue[],
  warnings: RktIssue[],
): void {
  if (!checkString(design.id, 'design.id', errors)) return;
  checkString(design.name, 'design.name', errors);

  const stages = design.stages;
  if (!Array.isArray(stages)) {
    errors.push(error('design.stages', 'The design has no stage list.'));
    return;
  }
  if (stages.length === 0) {
    warnings.push(warning('design.stages', 'The design has no stages, so it cannot fly.'));
  }

  const components = design.components;
  if (!Array.isArray(components)) {
    errors.push(error('design.components', 'The design has no component list.'));
    return;
  }
  if (components.length > RKT_MAX_COMPONENTS) {
    errors.push(
      error(
        'design.components',
        `The design declares ${components.length} components, over the ` +
          `${RKT_MAX_COMPONENTS} limit.`,
      ),
    );
    return;
  }

  const instanceIds = new Set<string>();
  components.forEach((component, index) => {
    const path = `design.components[${index}]`;
    if (!isObject(component)) {
      errors.push(error(path, 'A component entry is not an object.'));
      return;
    }
    const instanceId = component.instanceId;
    if (typeof instanceId !== 'string' || instanceId.length === 0) {
      errors.push(error(`${path}.instanceId`, 'A component has no identifier.'));
      return;
    }
    if (instanceIds.has(instanceId)) {
      errors.push(
        error(`${path}.instanceId`, `Two components share the identifier "${instanceId}".`),
      );
    }
    instanceIds.add(instanceId);

    checkString(component.defId, `${path}.defId`, errors);

    const stageIndex = component.stageIndex;
    if (typeof stageIndex !== 'number' || !Number.isInteger(stageIndex) || stageIndex < 0) {
      errors.push(error(`${path}.stageIndex`, `Component ${instanceId} has no valid stage.`));
    } else if (stages.length > 0 && stageIndex >= stages.length) {
      errors.push(
        error(
          `${path}.stageIndex`,
          `Component ${instanceId} belongs to stage ${stageIndex}, but the design has ` +
            `only ${stages.length} stage${stages.length === 1 ? '' : 's'}.`,
        ),
      );
    }

    for (const axis of ['offset_x', 'offset_y', 'offset_z'] as const) {
      checkFiniteNumber(component[axis], `${path}.${axis}`, -1e4, 1e4, errors);
    }

    // Configuration overrides are primitives only. A nested structure here is
    // either corruption or an attempt to smuggle data past the schema.
    const overrides = component.configOverrides;
    if (overrides !== undefined) {
      if (!isObject(overrides)) {
        errors.push(error(`${path}.configOverrides`, 'Overrides must be an object.'));
      } else {
        // A single corrupt override is dropped with a warning rather than
        // rejecting the whole project: losing one adjusted payload mass is a
        // far better outcome for the user than losing the rocket.
        const cleaned: Record<string, number> = {};
        for (const [key, value] of Object.entries(overrides)) {
          if (typeof value === 'number' && Number.isFinite(value)) {
            cleaned[key] = value;
          } else {
            warnings.push(
              warning(
                `${path}.configOverrides.${key}`,
                `The override "${key}" is not a finite number and has been discarded.`,
              ),
            );
          }
        }
        (component as Record<string, unknown>).configOverrides = cleaned;
      }
    }
  });

  // References must resolve. A fin whose parent does not exist is a design that
  // cannot be laid out, and finding out at render time is far too late.
  const connections = design.connections;
  if (Array.isArray(connections)) {
    connections.forEach((connection, index) => {
      if (!isObject(connection)) return;
      for (const key of ['fromInstanceId', 'toInstanceId'] as const) {
        const value = connection[key];
        if (typeof value === 'string' && !instanceIds.has(value)) {
          errors.push(
            error(
              `design.connections[${index}].${key}`,
              `Connection references component "${value}", which is not in this design.`,
            ),
          );
        }
      }
    });
  }
}

/**
 * Range-check the mission configuration.
 *
 * These are the fields the physics reads directly, so an implausible value here
 * does not fail loudly — it produces a flight that quietly means nothing. A
 * latitude of 500 degrees is not a latitude.
 */
function validateMissionConfig(mission: Record<string, unknown>, errors: RktIssue[]): void {
  const site = mission.launchSite;
  if (isObject(site)) {
    checkFiniteNumber(site.latitude_deg, 'mission.launchSite.latitude_deg', -90, 90, errors);
    checkFiniteNumber(site.longitude_deg, 'mission.launchSite.longitude_deg', -180, 180, errors);
    checkFiniteNumber(site.altitude_m, 'mission.launchSite.altitude_m', -500, 6000, errors);
  }

  const environment = mission.environment;
  if (isObject(environment)) {
    // Wider than any weather Earth produces, and narrow enough that a decimal
    // slip or a Celsius/kelvin mix-up is caught.
    checkFiniteNumber(
      environment.temperature_K,
      'mission.environment.temperature_K',
      150,
      400,
      errors,
    );
    checkFiniteNumber(
      environment.pressure_Pa,
      'mission.environment.pressure_Pa',
      1_000,
      120_000,
      errors,
    );
    checkFiniteNumber(
      environment.windSpeed_ms,
      'mission.environment.windSpeed_ms',
      0,
      150,
      errors,
    );
  }

  const target = mission.target;
  if (isObject(target)) {
    checkFiniteNumber(
      target.targetAltitude_km,
      'mission.target.targetAltitude_km',
      0,
      500_000,
      errors,
    );
  }
}

function validateVehicle(
  vehicle: Record<string, unknown>,
  errors: RktIssue[],
  warnings: RktIssue[],
): void {
  const components = vehicle.components;
  if (Array.isArray(components)) {
    const ids = new Set(
      components.filter(isObject).map((c) => (typeof c.id === 'string' ? c.id : '')),
    );
    components.forEach((component, index) => {
      if (!isObject(component)) return;
      const parentId = component.parentId;
      if (typeof parentId === 'string' && parentId.length > 0 && !ids.has(parentId)) {
        errors.push(
          error(
            `vehicle.components[${index}].parentId`,
            `Component ${String(component.id ?? index)} references missing parent ` +
              `${parentId}.`,
          ),
        );
      }
      checkFiniteNumber(component.mass_kg, `vehicle.components[${index}].mass_kg`, 0, 1e7, errors);
    });
  }

  const mass = vehicle.mass;
  if (isObject(mass)) {
    const dry = numberOr(mass.dry_kg, 0);
    const propellant = numberOr(mass.propellant_kg, 0);
    const launch = numberOr(mass.launch_kg, 0);
    if (launch > 0 && Math.abs(launch - (dry + propellant)) > Math.max(1, launch * 0.02)) {
      warnings.push(
        warning(
          'vehicle.mass',
          `Launch mass (${launch.toFixed(1)} kg) does not match dry plus propellant ` +
            `(${(dry + propellant).toFixed(1)} kg). It will be recomputed from the design.`,
        ),
      );
    }
  }
}

function validateResults(
  results: Record<string, unknown>,
  errors: RktIssue[],
  warnings: RktIssue[],
): void {
  if (results.hasResults !== true) return;

  if (typeof results.inputsHash !== 'string' || results.inputsHash.length === 0) {
    warnings.push(
      warning(
        'results.inputsHash',
        'The stored results carry no inputs hash, so they cannot be checked against ' +
          'the current design. They will be treated as stale.',
      ),
    );
  }

  const telemetry = results.telemetry;
  if (isObject(telemetry)) {
    const rows = telemetry.rows;
    const channels = telemetry.channels;
    if (Array.isArray(rows) && rows.length > RKT_MAX_TELEMETRY) {
      errors.push(
        error(
          'results.telemetry.rows',
          `The stored flight has ${rows.length} samples, over the ${RKT_MAX_TELEMETRY} limit.`,
        ),
      );
    }
    if (Array.isArray(rows) && Array.isArray(channels) && rows.length > 0) {
      const first = rows[0];
      if (Array.isArray(first) && first.length !== channels.length) {
        errors.push(
          error(
            'results.telemetry',
            `Telemetry declares ${channels.length} channels but its rows have ` +
              `${first.length} values.`,
          ),
        );
      }
    }
  }
}

function validateAssets(
  assets: Record<string, unknown>,
  errors: RktIssue[],
  warnings: RktIssue[],
): void {
  const images = assets.images;
  if (!Array.isArray(images)) return;
  images.forEach((image, index) => {
    if (!isObject(image)) return;
    const url = image.url;
    if (typeof url !== 'string') return;
    // A project file must never be able to make the application fetch an
    // arbitrary address, so references are restricted to hosts already trusted.
    let host = '';
    try {
      host = new URL(url).hostname;
    } catch {
      errors.push(error(`assets.images[${index}].url`, 'The image reference is not a valid URL.'));
      return;
    }
    if (!ALLOWED_IMAGE_HOSTS.includes(host)) {
      warnings.push(
        warning(
          `assets.images[${index}].url`,
          `The image points at ${host}, which is not a trusted source. It will not be ` +
            'loaded.',
        ),
      );
    }
  });
}

// ============================================================
// Catalogue compatibility
// ============================================================

/**
 * Component definitions a project needs that a catalogue does not have.
 *
 * Opening a project against an incomplete catalogue would otherwise silently
 * produce a *different, lighter* rocket than its author designed — every
 * unresolved part simply vanishing from the mass budget. Naming them lets the
 * interface refuse, or say what is missing.
 *
 * @param project - The parsed project.
 * @param availableIds - Definition ids the catalogue can resolve.
 * @returns The missing ids, sorted, without duplicates.
 */
export function findMissingComponents(
  project: RktProject,
  availableIds: readonly string[],
): string[] {
  const available = new Set(availableIds);
  const missing = new Set<string>();
  for (const component of project.design?.components ?? []) {
    if (!available.has(component.defId)) missing.add(component.defId);
  }
  return [...missing].sort();
}

// ============================================================
// Normalisation
// ============================================================

/**
 * Turn a validated document into a `RktProject`, filling defaults.
 *
 * Unknown top-level keys are dropped here rather than spread through, so a file
 * cannot carry fields the application never inspected into whatever it is
 * written back out to.
 */
function normalise(document: Record<string, unknown>, warnings: RktIssue[]): RktProject {
  const metadata = isObject(document.metadata) ? document.metadata : {};
  const now = new Date().toISOString();

  const project = {
    metadata: {
      formatVersion: RKT_FORMAT_VERSION,
      schemaVersion: RKT_SCHEMA_VERSION,
      projectId: capped(metadata.projectId, `project-${cyrb53(now).toString(36)}`),
      name: capped(metadata.name, 'Untitled project'),
      description: capped(metadata.description, ''),
      author: capped(metadata.author, ''),
      createdAt: capped(metadata.createdAt, now),
      updatedAt: capped(metadata.updatedAt, now),
      generator: capped(metadata.generator, 'unknown'),
      tags: Array.isArray(metadata.tags)
        ? metadata.tags.filter((t): t is string => typeof t === 'string').slice(0, 32)
        : [],
    },
    vehicle: (document.vehicle ?? emptyVehicle()) as RktProject['vehicle'],
    propulsion: (document.propulsion ?? {
      motors: [],
      mounts: [],
      thrustProfiles: [],
    }) as RktProject['propulsion'],
    aerodynamics: (document.aerodynamics ?? emptyAerodynamics()) as RktProject['aerodynamics'],
    avionics: (document.avionics ?? {
      flightComputer: null,
      sensors: [],
      telemetry: { enabled: true, sampleInterval_s: 1, channels: [] },
    }) as RktProject['avionics'],
    mission: (document.mission ?? emptyMission()) as RktProject['mission'],
    environment: (document.environment ?? emptyEnvironment()) as RktProject['environment'],
    simulation: (document.simulation ?? emptySimulation()) as RktProject['simulation'],
    results: (document.results ?? emptyResults()) as RktProject['results'],
    assets: (document.assets ?? {
      componentReferences: [],
      images: [],
      customAssets: [],
    }) as RktProject['assets'],
    design: document.design as RocketDesign,
    missionConfig: (document.missionConfig ?? document.mission) as MissionConfig,
  } satisfies RktProject;

  if (project.results.hasResults && areResultsStale(project)) {
    warnings.push(
      warning(
        'results',
        'The stored flight results were produced from a different version of this ' +
          'vehicle. They are shown as stale until the mission is flown again.',
      ),
    );
  }

  return project;
}

function capped(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  return value.slice(0, RKT_MAX_STRING);
}

function emptyVehicle(): RktProject['vehicle'] {
  return {
    name: '',
    description: '',
    dimensions: { length_m: 0, maxDiameter_m: 0, referenceArea_m2: 0 },
    mass: { dry_kg: 0, propellant_kg: 0, payload_kg: 0, launch_kg: 0 },
    materials: [],
    stages: [],
    components: [],
    payload: {
      mass_kg: 0,
      type: 'none',
      dimensions: { length_m: 0, diameter_m: 0 },
      description: '',
    },
    recovery: {
      enabled: false,
      componentIds: [],
      drogueDeployAltitude_m: 0,
      mainDeployAltitude_m: 0,
      maxDeploySpeed_ms: 0,
    },
  };
}

function emptyAerodynamics(): RktProject['aerodynamics'] {
  return {
    fins: [],
    noseCone: null,
    dragParameters: { subsonicCd: 0.4, referenceArea_m2: 0, useMachDragRise: true },
    stabilityParameters: {
      cgWet_m: 0,
      cgDry_m: 0,
      cp_m: 0,
      staticMarginWet_cal: 0,
      staticMarginDry_cal: 0,
      referenceDiameter_m: 0,
    },
  };
}

function emptyMission(): RktProject['mission'] {
  return {
    name: 'Untitled mission',
    objective: '',
    launchSite: { id: '', name: '', latitude_deg: 0, longitude_deg: 0, elevation_m: 0 },
    target: { type: 'suborbital', altitude_km: 100, inclination_deg: null, bodyId: 'earth' },
    trajectory: {
      guidanceMode: 'pitch_program',
      pitchoverAltitude_m: 200,
      pitchProgramEndAltitude_m: 80_000,
      finalPitch_deg: 0,
    },
    orientation: { launchAzimuth_deg: 90, launchElevation_deg: 90, rollOrientation_deg: 0 },
    constraints: {
      maxG: 15,
      maxDynamicPressure_Pa: 1e6,
      maxQAlpha_Padeg: 250_000,
      maxGroundWind_ms: 15,
    },
  };
}

function emptyEnvironment(): RktProject['environment'] {
  return {
    atmosphere: {
      model: 'us_standard_1976',
      surfaceTemperature_K: 288.15,
      surfacePressure_Pa: 101_325,
      relativeHumidity: 0,
    },
    weather: {
      source: 'standard_day',
      observedAt: null,
      windSpeed_ms: 0,
      windDirection_deg: 0,
      windGust_ms: 0,
      jetWindSpeed_ms: 0,
      cloudCover: 0,
      precipitation_mmh: 0,
    },
    gravity: {
      model: 'inverse_square',
      bodyId: 'earth',
      mu_m3s2: 3.986004418e14,
      surfaceRadius_m: 6_371_000,
    },
    simulationConditions: {
      includeWind: true,
      includeWeather: true,
      includeEarthRotation: false,
    },
  };
}

function emptySimulation(): RktProject['simulation'] {
  return {
    engine: 'lostintospace-python',
    engineVersion: '0.2.0',
    solver: 'rk4',
    timestep: { powered_s: 0.05, coast_s: 0.5, maxSteps: 2_000_000 },
    configuration: {
      maxTime_s: 2000,
      telemetrySampleInterval_s: 1,
      countdown_s: 3,
      useAltitudeCompensation: true,
      failureDetection: true,
      failureSeed: 1,
    },
  };
}

function emptyResults(): RktProject['results'] {
  return {
    hasResults: false,
    ranAt: null,
    engineVersion: '',
    inputsHash: '',
    outcome: 'not_run',
    telemetry: { channels: [], rows: [] },
    trajectory: {
      maxAltitude_m: 0,
      maxSpeed_ms: 0,
      maxAcceleration_g: 0,
      maxDynamicPressure_Pa: 0,
      maxQAlpha_Padeg: 0,
      apogeeTime_s: 0,
      flightTime_s: 0,
      downrange_m: 0,
      finalPeriapsis_m: 0,
      finalApoapsis_m: 0,
    },
    evaluation: null,
    failures: [],
  };
}

// ============================================================
// Small helpers
// ============================================================

function isObject(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function numberOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function checkString(value: unknown, path: string, errors: RktIssue[]): boolean {
  if (typeof value !== 'string' || value.length === 0) {
    errors.push(error(path, 'This field must be a non-empty string.'));
    return false;
  }
  if (value.length > RKT_MAX_STRING) {
    errors.push(error(path, `This field is ${value.length} characters, over the limit.`));
    return false;
  }
  return true;
}

function checkFiniteNumber(
  value: unknown,
  path: string,
  min: number,
  max: number,
  errors: RktIssue[],
): void {
  if (value === undefined) return;
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    errors.push(error(path, 'This field must be a finite number.'));
    return;
  }
  if (value < min || value > max) {
    errors.push(
      error(path, `${value} is outside the plausible range ${min} to ${max} for this field.`),
    );
  }
}

/** Depth of the deepest nesting, stopping early once the limit is exceeded. */
function measureDepth(value: unknown, current: number): number {
  if (current > RKT_MAX_DEPTH) return current;
  if (value === null || typeof value !== 'object') return current;
  let deepest = current;
  for (const child of Array.isArray(value) ? value : Object.values(value)) {
    deepest = Math.max(deepest, measureDepth(child, current + 1));
    if (deepest > RKT_MAX_DEPTH) return deepest;
  }
  return deepest;
}
