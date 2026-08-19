/**
 * Component Definition Registry.
 *
 * An in-memory catalog of component definitions (templates).
 * Components are registered once and looked up by ID or category.
 *
 * - No database dependency
 * - No React/Three.js dependency
 * - Immutable read access via frozen arrays
 * - Validates definitions on registration
 *
 * @module core/component-registry
 */

import type {
  ComponentDef,
  ComponentCategory,
} from './component-types.js';
import { COMPONENT_CATEGORIES } from './component-types.js';

// ============================================================
// Validation
// ============================================================

export interface ValidationError {
  readonly field: string;
  readonly message: string;
}

/**
 * Validate a component definition.
 * Returns an empty array if valid, or a list of errors.
 */
export function validateComponentDef(def: ComponentDef): ValidationError[] {
  const errors: ValidationError[] = [];

  if (!def.id || typeof def.id !== 'string' || def.id.trim().length === 0) {
    errors.push({ field: 'id', message: 'id must be a non-empty string' });
  }

  if (!def.name || typeof def.name !== 'string' || def.name.trim().length === 0) {
    errors.push({ field: 'name', message: 'name must be a non-empty string' });
  }

  if (!COMPONENT_CATEGORIES.includes(def.category)) {
    errors.push({ field: 'category', message: `unknown category: ${def.category}` });
  }

  if (typeof def.mass_kg !== 'number' || def.mass_kg < 0) {
    errors.push({ field: 'mass_kg', message: 'mass_kg must be a non-negative number' });
  }

  if (typeof def.outerDiameter_m !== 'number' || def.outerDiameter_m <= 0) {
    errors.push({ field: 'outerDiameter_m', message: 'outerDiameter_m must be positive' });
  }

  if (typeof def.length_m !== 'number' || def.length_m <= 0) {
    errors.push({ field: 'length_m', message: 'length_m must be positive' });
  }

  if (!def.structural) {
    errors.push({ field: 'structural', message: 'structural properties are required' });
  }

  if (!def.thermal) {
    errors.push({ field: 'thermal', message: 'thermal properties are required' });
  }

  if (!def.visual) {
    errors.push({ field: 'visual', message: 'visual asset reference is required' });
  }

  return errors;
}

// ============================================================
// Registry
// ============================================================

export class ComponentRegistry {
  private readonly _defs = new Map<string, ComponentDef>();

  /**
   * Register a component definition.
   *
   * @throws Error if the ID is already registered.
   * @throws Error if the definition fails validation.
   */
  register(def: ComponentDef): void {
    if (this._defs.has(def.id)) {
      throw new Error(`Duplicate component ID: "${def.id}"`);
    }

    const errors = validateComponentDef(def);
    if (errors.length > 0) {
      const messages = errors.map(e => `${e.field}: ${e.message}`).join('; ');
      throw new Error(`Invalid component definition "${def.id}": ${messages}`);
    }

    this._defs.set(def.id, def);
  }

  /**
   * Register multiple definitions at once.
   * All-or-nothing: if any fails, none are registered.
   */
  registerAll(defs: readonly ComponentDef[]): void {
    // Validate all first
    for (const def of defs) {
      if (this._defs.has(def.id)) {
        throw new Error(`Duplicate component ID: "${def.id}"`);
      }
      const errors = validateComponentDef(def);
      if (errors.length > 0) {
        const messages = errors.map(e => `${e.field}: ${e.message}`).join('; ');
        throw new Error(`Invalid component definition "${def.id}": ${messages}`);
      }
    }

    // Check for duplicates within the batch
    const ids = new Set<string>();
    for (const def of defs) {
      if (ids.has(def.id)) {
        throw new Error(`Duplicate component ID in batch: "${def.id}"`);
      }
      ids.add(def.id);
    }

    // All valid — register
    for (const def of defs) {
      this._defs.set(def.id, def);
    }
  }

  /**
   * Get a component definition by ID.
   * Returns undefined if not found.
   */
  get(id: string): ComponentDef | undefined {
    return this._defs.get(id);
  }

  /**
   * Get a component definition by ID, throwing if not found.
   */
  getOrThrow(id: string): ComponentDef {
    const def = this._defs.get(id);
    if (!def) {
      throw new Error(`Component not found: "${id}"`);
    }
    return def;
  }

  /** Check whether a definition with this ID exists. */
  has(id: string): boolean {
    return this._defs.has(id);
  }

  /**
   * Get all definitions for a given category.
   * Returns a frozen array for immutable read access.
   */
  listByCategory(category: ComponentCategory): readonly ComponentDef[] {
    const result: ComponentDef[] = [];
    for (const def of this._defs.values()) {
      if (def.category === category) {
        result.push(def);
      }
    }
    return Object.freeze(result);
  }

  /**
   * Get all registered definitions.
   * Returns a frozen array for immutable read access.
   */
  listAll(): readonly ComponentDef[] {
    return Object.freeze([...this._defs.values()]);
  }

  /**
   * Get all registered component IDs.
   */
  listIds(): readonly string[] {
    return Object.freeze([...this._defs.keys()]);
  }

  /** Total number of registered definitions. */
  get size(): number {
    return this._defs.size;
  }

  /** Remove a definition by ID. Returns true if it existed. */
  unregister(id: string): boolean {
    return this._defs.delete(id);
  }

  /** Remove all registered definitions. */
  clear(): void {
    this._defs.clear();
  }
}
