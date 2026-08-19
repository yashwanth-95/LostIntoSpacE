/**
 * RocketDesign construction.
 *
 * A functional API for assembling rocket designs:
 *   createRocket → addStage → addComponent → connectComponents → …
 *
 * Every operation returns a **new** RocketDesign; nothing is mutated in place.
 *
 * ## Determinism
 *
 * These functions are pure. Instance ids are derived from the ids already
 * present in the design rather than from a module-level counter, so the same
 * sequence of calls always produces the same design — in tests, in a Web
 * Worker, and after a round-trip through P2's database.
 *
 * Timestamps are likewise not touched by the mutators. `updatedAt` is advanced
 * explicitly with {@link touch}, which the persistence layer calls when it
 * actually saves. An in-memory edit is not a save.
 *
 * No database, React, or Three.js dependencies.
 *
 * @module core/rocket-design
 */

import type {
  RocketDesign,
  DesignStage,
  PlacedComponent,
  Connection,
  ConnectionType,
} from './component-types.js';
import type { ComponentRegistry } from './component-registry.js';

// ============================================================
// Error types
// ============================================================

/** Error codes thrown by design operations. */
export type RocketDesignErrorCode =
  | 'DEF_NOT_FOUND'
  | 'INVALID_STAGE_INDEX'
  | 'COMPONENT_NOT_FOUND'
  | 'CONNECTION_NOT_FOUND'
  | 'SELF_CONNECTION'
  | 'DUPLICATE_CONNECTION'
  | 'INVALID_ATTACHMENT';

export class RocketDesignError extends Error {
  constructor(
    message: string,
    readonly code: RocketDesignErrorCode,
  ) {
    super(message);
    this.name = 'RocketDesignError';
  }
}

// ============================================================
// Structural validation result
// ============================================================

export interface DesignValidationResult {
  readonly valid: boolean;
  readonly errors: readonly DesignValidationError[];
  readonly warnings: readonly string[];
}

export interface DesignValidationError {
  readonly code: string;
  readonly message: string;
  readonly componentId?: string;
  readonly stageIndex?: number;
}

// ============================================================
// Deterministic id generation
// ============================================================

/**
 * Next id with the given prefix that does not collide with any in `existing`.
 *
 * Ids look like `comp_1`, `comp_2`, … The next one is `max(n) + 1` over the
 * existing ids, so removing a component never causes a later add to reuse its
 * id — which would silently re-point any connection that outlived it.
 *
 * @param existing - Ids already in use.
 * @param prefix - Id prefix, e.g. `'comp'`.
 * @returns A fresh, unused id.
 */
export function nextId(existing: readonly string[], prefix: string): string {
  const pattern = new RegExp(`^${prefix}_(\\d+)$`);
  let max = 0;
  for (const id of existing) {
    const match = pattern.exec(id);
    if (match) {
      const n = Number.parseInt(match[1]!, 10);
      if (n > max) max = n;
    }
  }
  return `${prefix}_${max + 1}`;
}

// ============================================================
// Factory
// ============================================================

/** Options for {@link createRocket}. */
export interface CreateRocketOptions {
  /** Explicit design id. Defaults to a slug derived from the name. */
  readonly id?: string;
  /** Creation timestamp as an ISO 8601 string. Defaults to now. */
  readonly timestamp?: string;
}

/** Turn a display name into a stable, url-safe id fragment. */
function slugify(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return slug.length > 0 ? slug : 'rocket';
}

/**
 * Create a new empty rocket design.
 *
 * @param name - Display name.
 * @param description - Optional longer description.
 * @param options - Explicit id and/or timestamp, for deterministic tests and
 *   for re-hydrating a design whose id is owned by the backend.
 * @returns An empty design with no stages or components.
 */
export function createRocket(
  name: string,
  description = '',
  options: CreateRocketOptions = {},
): RocketDesign {
  const timestamp = options.timestamp ?? new Date().toISOString();
  return {
    id: options.id ?? slugify(name),
    name,
    description,
    stages: [],
    components: [],
    connections: [],
    createdAt: timestamp,
    updatedAt: timestamp,
  };
}

/**
 * Return a copy of the design with a new `updatedAt` timestamp.
 *
 * The mutators deliberately leave timestamps alone so they stay pure. Call this
 * at the point where the design is actually persisted.
 *
 * @param design - Design to stamp.
 * @param timestamp - ISO 8601 timestamp. Defaults to now.
 * @returns The design with `updatedAt` advanced.
 */
export function touch(design: RocketDesign, timestamp?: string): RocketDesign {
  return { ...design, updatedAt: timestamp ?? new Date().toISOString() };
}

// ============================================================
// Stage operations
// ============================================================

/**
 * Add a stage. Stages are appended at the top (highest index).
 *
 * Stage 0 is the bottom stage — the one that fires first and separates first.
 *
 * @param design - Design to extend.
 * @param name - Stage display name.
 * @param ignitionDelay_s - Delay after the previous stage separates before this
 *   one ignites. Unit: s.
 * @returns A new design with the stage appended.
 */
export function addStage(
  design: RocketDesign,
  name: string,
  ignitionDelay_s = 1.0,
): RocketDesign {
  const newIndex = design.stages.length;
  const stage: DesignStage = {
    index: newIndex,
    name,
    separationOrder: newIndex,
    ignitionDelay_s,
  };
  return { ...design, stages: [...design.stages, stage] };
}

/**
 * Remove a stage together with every component in it.
 *
 * Connections referencing removed components are dropped, and the remaining
 * stages are re-indexed so indices stay contiguous.
 *
 * @param design - Design to modify.
 * @param stageIndex - Index of the stage to remove.
 * @returns A new design without that stage.
 * @throws RocketDesignError if the index is out of range.
 */
export function removeStage(
  design: RocketDesign,
  stageIndex: number,
): RocketDesign {
  if (stageIndex < 0 || stageIndex >= design.stages.length) {
    throw new RocketDesignError(
      `Stage index ${stageIndex} out of range (0–${design.stages.length - 1})`,
      'INVALID_STAGE_INDEX',
    );
  }

  const removedInstanceIds = new Set(
    design.components
      .filter(c => c.stageIndex === stageIndex)
      .map(c => c.instanceId),
  );

  const remainingComponents = design.components
    .filter(c => c.stageIndex !== stageIndex)
    .map(c =>
      c.stageIndex > stageIndex ? { ...c, stageIndex: c.stageIndex - 1 } : c,
    );

  const remainingConnections = design.connections.filter(
    conn =>
      !removedInstanceIds.has(conn.fromInstanceId) &&
      !removedInstanceIds.has(conn.toInstanceId),
  );

  const remainingStages = design.stages
    .filter(s => s.index !== stageIndex)
    .map((s, i) => ({ ...s, index: i, separationOrder: i }));

  return {
    ...design,
    stages: remainingStages,
    components: remainingComponents,
    connections: remainingConnections,
  };
}

/**
 * Change a stage's ignition delay.
 *
 * @param design - Design to modify.
 * @param stageIndex - Stage to update.
 * @param ignitionDelay_s - New delay. Unit: s. Negative values are clamped to 0.
 * @returns A new design with the updated stage.
 * @throws RocketDesignError if the index is out of range.
 */
export function setStageIgnitionDelay(
  design: RocketDesign,
  stageIndex: number,
  ignitionDelay_s: number,
): RocketDesign {
  if (stageIndex < 0 || stageIndex >= design.stages.length) {
    throw new RocketDesignError(
      `Stage index ${stageIndex} out of range (0–${design.stages.length - 1})`,
      'INVALID_STAGE_INDEX',
    );
  }
  return {
    ...design,
    stages: design.stages.map(s =>
      s.index === stageIndex
        ? { ...s, ignitionDelay_s: Math.max(0, ignitionDelay_s) }
        : s,
    ),
  };
}

// ============================================================
// Component operations
// ============================================================

/**
 * Add a component instance to a stage.
 *
 * @param design - Design to extend.
 * @param registry - Used to check that `defId` is a known component.
 * @param defId - Component definition to instantiate.
 * @param stageIndex - Stage to place it in.
 * @param offset - Placement within the stage. `z` is the axial position of the
 *   component's **aft end** measured up from the stage's aft end; `x`/`y` are
 *   radial offsets for surface-mounted parts such as fins. Unit: m.
 * @returns A new design with the component added.
 * @throws RocketDesignError if the definition or the stage does not exist.
 */
export function addComponent(
  design: RocketDesign,
  registry: ComponentRegistry,
  defId: string,
  stageIndex: number,
  offset: { x?: number; y?: number; z?: number } = {},
): RocketDesign {
  if (!registry.has(defId)) {
    throw new RocketDesignError(
      `Component definition "${defId}" not found in registry`,
      'DEF_NOT_FOUND',
    );
  }

  if (stageIndex < 0 || stageIndex >= design.stages.length) {
    throw new RocketDesignError(
      `Stage index ${stageIndex} out of range. Add a stage first.`,
      'INVALID_STAGE_INDEX',
    );
  }

  const component: PlacedComponent = {
    instanceId: nextId(design.components.map(c => c.instanceId), 'comp'),
    defId,
    stageIndex,
    offset_x: offset.x ?? 0,
    offset_y: offset.y ?? 0,
    offset_z: offset.z ?? 0,
    configOverrides: {},
  };

  return { ...design, components: [...design.components, component] };
}

/**
 * Remove a component and every connection that involved it.
 *
 * @param design - Design to modify.
 * @param instanceId - Instance to remove.
 * @returns A new design without that component.
 * @throws RocketDesignError if the instance does not exist.
 */
export function removeComponent(
  design: RocketDesign,
  instanceId: string,
): RocketDesign {
  const exists = design.components.some(c => c.instanceId === instanceId);
  if (!exists) {
    throw new RocketDesignError(
      `Component instance "${instanceId}" not found`,
      'COMPONENT_NOT_FOUND',
    );
  }

  return {
    ...design,
    components: design.components.filter(c => c.instanceId !== instanceId),
    connections: design.connections.filter(
      conn =>
        conn.fromInstanceId !== instanceId && conn.toInstanceId !== instanceId,
    ),
  };
}

/**
 * Apply configuration overrides to a placed component, merging with any already
 * set.
 *
 * Recognised keys are documented in `core/builder.ts` — `mass_kg` for adjustable
 * payloads, `fillFraction` for tanks, `throttle` for engines. Unknown keys are
 * carried along harmlessly so the UI can stash its own annotations.
 *
 * @param design - Design to modify.
 * @param instanceId - Instance to configure.
 * @param overrides - Values to merge in.
 * @returns A new design with the overrides applied.
 * @throws RocketDesignError if the instance does not exist.
 */
export function configureComponent(
  design: RocketDesign,
  instanceId: string,
  overrides: Readonly<Record<string, number>>,
): RocketDesign {
  const idx = design.components.findIndex(c => c.instanceId === instanceId);
  if (idx === -1) {
    throw new RocketDesignError(
      `Component instance "${instanceId}" not found`,
      'COMPONENT_NOT_FOUND',
    );
  }

  const existing = design.components[idx]!;
  const components = [...design.components];
  components[idx] = {
    ...existing,
    configOverrides: { ...existing.configOverrides, ...overrides },
  };

  return { ...design, components };
}

/**
 * Move a placed component to a new offset within its stage.
 *
 * @param design - Design to modify.
 * @param instanceId - Instance to move.
 * @param offset - New offset. Omitted axes keep their current value. Unit: m.
 * @returns A new design with the component moved.
 * @throws RocketDesignError if the instance does not exist.
 */
export function moveComponent(
  design: RocketDesign,
  instanceId: string,
  offset: { x?: number; y?: number; z?: number },
): RocketDesign {
  const idx = design.components.findIndex(c => c.instanceId === instanceId);
  if (idx === -1) {
    throw new RocketDesignError(
      `Component instance "${instanceId}" not found`,
      'COMPONENT_NOT_FOUND',
    );
  }

  const existing = design.components[idx]!;
  const components = [...design.components];
  components[idx] = {
    ...existing,
    offset_x: offset.x ?? existing.offset_x,
    offset_y: offset.y ?? existing.offset_y,
    offset_z: offset.z ?? existing.offset_z,
  };

  return { ...design, components };
}

// ============================================================
// Connection operations
// ============================================================

/**
 * Connect two components through named attachment points.
 *
 * @param design - Design to modify.
 * @param fromInstanceId - Source component instance.
 * @param fromAttachmentId - Attachment point on the source.
 * @param toInstanceId - Target component instance.
 * @param toAttachmentId - Attachment point on the target.
 * @param type - Kind of connection. Defaults to `'structural'`.
 * @param registry - If supplied, attachment point ids and their `accepts` lists
 *   are validated against the component definitions.
 * @returns A new design with the connection added.
 * @throws RocketDesignError on missing components, self-connections, duplicates,
 *   or invalid attachment points.
 */
export function connectComponents(
  design: RocketDesign,
  fromInstanceId: string,
  fromAttachmentId: string,
  toInstanceId: string,
  toAttachmentId: string,
  type: ConnectionType = 'structural',
  registry?: ComponentRegistry,
): RocketDesign {
  const fromComp = design.components.find(c => c.instanceId === fromInstanceId);
  const toComp = design.components.find(c => c.instanceId === toInstanceId);

  if (!fromComp) {
    throw new RocketDesignError(
      `Source component "${fromInstanceId}" not found`,
      'COMPONENT_NOT_FOUND',
    );
  }
  if (!toComp) {
    throw new RocketDesignError(
      `Target component "${toInstanceId}" not found`,
      'COMPONENT_NOT_FOUND',
    );
  }

  if (fromInstanceId === toInstanceId) {
    throw new RocketDesignError(
      'Cannot connect a component to itself',
      'SELF_CONNECTION',
    );
  }

  const duplicate = design.connections.some(
    conn =>
      conn.fromInstanceId === fromInstanceId &&
      conn.fromAttachmentId === fromAttachmentId &&
      conn.toInstanceId === toInstanceId &&
      conn.toAttachmentId === toAttachmentId,
  );
  if (duplicate) {
    throw new RocketDesignError(
      'This connection already exists',
      'DUPLICATE_CONNECTION',
    );
  }

  if (registry) {
    const fromDef = registry.get(fromComp.defId);
    const toDef = registry.get(toComp.defId);

    const fromPoint = fromDef?.attachmentPoints.find(p => p.id === fromAttachmentId);
    if (fromDef && !fromPoint) {
      throw new RocketDesignError(
        `Attachment point "${fromAttachmentId}" not found on "${fromComp.defId}"`,
        'INVALID_ATTACHMENT',
      );
    }

    const toPoint = toDef?.attachmentPoints.find(p => p.id === toAttachmentId);
    if (toDef && !toPoint) {
      throw new RocketDesignError(
        `Attachment point "${toAttachmentId}" not found on "${toComp.defId}"`,
        'INVALID_ATTACHMENT',
      );
    }

    // Compatibility: each attachment point declares which categories it accepts.
    if (fromPoint && toDef && !fromPoint.accepts.includes(toDef.category)) {
      throw new RocketDesignError(
        `Attachment point "${fromAttachmentId}" on "${fromComp.defId}" does not ` +
          `accept a ${toDef.category} (accepts: ${fromPoint.accepts.join(', ')})`,
        'INVALID_ATTACHMENT',
      );
    }
    if (toPoint && fromDef && !toPoint.accepts.includes(fromDef.category)) {
      throw new RocketDesignError(
        `Attachment point "${toAttachmentId}" on "${toComp.defId}" does not ` +
          `accept a ${fromDef.category} (accepts: ${toPoint.accepts.join(', ')})`,
        'INVALID_ATTACHMENT',
      );
    }
  }

  const connection: Connection = {
    id: nextId(design.connections.map(c => c.id), 'conn'),
    fromInstanceId,
    fromAttachmentId,
    toInstanceId,
    toAttachmentId,
    type,
  };

  return { ...design, connections: [...design.connections, connection] };
}

/**
 * Remove a connection by id.
 *
 * @param design - Design to modify.
 * @param connectionId - Connection to remove.
 * @returns A new design without that connection.
 * @throws RocketDesignError if the connection does not exist.
 */
export function disconnectComponents(
  design: RocketDesign,
  connectionId: string,
): RocketDesign {
  const exists = design.connections.some(c => c.id === connectionId);
  if (!exists) {
    throw new RocketDesignError(
      `Connection "${connectionId}" not found`,
      'CONNECTION_NOT_FOUND',
    );
  }

  return {
    ...design,
    connections: design.connections.filter(c => c.id !== connectionId),
  };
}

// ============================================================
// Structural validation
// ============================================================

/**
 * Check a design for **structural** integrity — dangling references, empty
 * stages, unknown component definitions.
 *
 * This is the cheap check the builder UI can run on every edit. It says nothing
 * about whether the rocket can fly; for that, see `validateRocket` in
 * `core/validation.ts`.
 *
 * @param design - Design to check.
 * @param registry - Registry the design's definitions must resolve against.
 * @returns Errors (which block simulation) and warnings (which do not).
 */
export function validateDesign(
  design: RocketDesign,
  registry: ComponentRegistry,
): DesignValidationResult {
  const errors: DesignValidationError[] = [];
  const warnings: string[] = [];

  if (design.stages.length === 0) {
    errors.push({ code: 'NO_STAGES', message: 'Rocket must have at least one stage' });
  }

  if (design.components.length === 0) {
    errors.push({ code: 'NO_COMPONENTS', message: 'Rocket must have at least one component' });
  }

  const instanceIds = new Set<string>();
  for (const comp of design.components) {
    if (instanceIds.has(comp.instanceId)) {
      errors.push({
        code: 'DUPLICATE_INSTANCE_ID',
        message: `Duplicate component instance id "${comp.instanceId}"`,
        componentId: comp.instanceId,
      });
    }
    instanceIds.add(comp.instanceId);

    if (!registry.has(comp.defId)) {
      errors.push({
        code: 'MISSING_DEF',
        message: `Component "${comp.instanceId}" references unknown definition "${comp.defId}"`,
        componentId: comp.instanceId,
      });
    }

    if (comp.stageIndex < 0 || comp.stageIndex >= design.stages.length) {
      errors.push({
        code: 'INVALID_STAGE_REF',
        message: `Component "${comp.instanceId}" references non-existent stage ${comp.stageIndex}`,
        componentId: comp.instanceId,
        stageIndex: comp.stageIndex,
      });
    }
  }

  for (const conn of design.connections) {
    if (!instanceIds.has(conn.fromInstanceId)) {
      errors.push({
        code: 'DANGLING_CONNECTION',
        message: `Connection "${conn.id}" references missing source "${conn.fromInstanceId}"`,
      });
    }
    if (!instanceIds.has(conn.toInstanceId)) {
      errors.push({
        code: 'DANGLING_CONNECTION',
        message: `Connection "${conn.id}" references missing target "${conn.toInstanceId}"`,
      });
    }
  }

  for (const stage of design.stages) {
    if (!design.components.some(c => c.stageIndex === stage.index)) {
      warnings.push(`Stage ${stage.index} ("${stage.name}") has no components`);
    }
  }

  if (design.stages.length > 0) {
    const hasEngine = design.components.some(
      c => c.stageIndex === 0 && registry.get(c.defId)?.category === 'engine',
    );
    if (!hasEngine) {
      warnings.push('First stage has no engine — rocket cannot launch');
    }
  }

  return {
    valid: errors.length === 0,
    errors: Object.freeze(errors),
    warnings: Object.freeze(warnings),
  };
}

// ============================================================
// Query helpers
// ============================================================

/**
 * All components in a stage.
 *
 * @param design - Design to query.
 * @param stageIndex - Stage of interest.
 * @returns The components placed in that stage.
 */
export function getStageComponents(
  design: RocketDesign,
  stageIndex: number,
): readonly PlacedComponent[] {
  return design.components.filter(c => c.stageIndex === stageIndex);
}

/**
 * All connections touching a component.
 *
 * @param design - Design to query.
 * @param instanceId - Component of interest.
 * @returns Connections where the component is either endpoint.
 */
export function getComponentConnections(
  design: RocketDesign,
  instanceId: string,
): readonly Connection[] {
  return design.connections.filter(
    c => c.fromInstanceId === instanceId || c.toInstanceId === instanceId,
  );
}

/**
 * Total **dry** mass of every component in the design.
 *
 * This does not include propellant. For a full mass breakdown including
 * propellant, payload, and per-stage figures, use `analyzeRocket` from
 * `core/builder.ts`.
 *
 * @param design - Design to measure.
 * @param registry - Registry resolving the component definitions.
 * @returns Total dry mass. Unit: kg. Unknown definitions contribute nothing.
 */
export function computeTotalMass(
  design: RocketDesign,
  registry: ComponentRegistry,
): number {
  let total = 0;
  for (const comp of design.components) {
    total += registry.get(comp.defId)?.mass_kg ?? 0;
  }
  return total;
}

/**
 * Dry mass of a single stage.
 *
 * @param design - Design to measure.
 * @param registry - Registry resolving the component definitions.
 * @param stageIndex - Stage of interest.
 * @returns Dry mass of that stage. Unit: kg.
 */
export function computeStageMass(
  design: RocketDesign,
  registry: ComponentRegistry,
  stageIndex: number,
): number {
  let total = 0;
  for (const comp of design.components) {
    if (comp.stageIndex === stageIndex) {
      total += registry.get(comp.defId)?.mass_kg ?? 0;
    }
  }
  return total;
}
