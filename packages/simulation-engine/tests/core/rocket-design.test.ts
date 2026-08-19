import { describe, it, expect } from 'vitest';
import {
  createRocket,
  touch,
  nextId,
  addStage,
  removeStage,
  setStageIgnitionDelay,
  addComponent,
  removeComponent,
  configureComponent,
  moveComponent,
  connectComponents,
  disconnectComponents,
  validateDesign,
  getStageComponents,
  getComponentConnections,
  computeTotalMass,
  computeStageMass,
  RocketDesignError,
} from '../../src/core/rocket-design.js';
import { stockRegistry, FIXED_TIMESTAMP } from './reference-designs.js';

const registry = stockRegistry();

/** A design with one stage and a body tube in it. */
function seed() {
  let design = createRocket('Test Rocket', 'A rocket for testing', {
    id: 'test',
    timestamp: FIXED_TIMESTAMP,
  });
  design = addStage(design, 'First Stage', 0);
  design = addComponent(design, registry, 'body_s_short', 0, { z: 0 });
  return design;
}

describe('createRocket', () => {
  it('starts empty', () => {
    const design = createRocket('Rocket', '', { timestamp: FIXED_TIMESTAMP });
    expect(design.stages).toEqual([]);
    expect(design.components).toEqual([]);
    expect(design.connections).toEqual([]);
  });

  it('derives a slug id from the name when none is given', () => {
    expect(createRocket('My First Rocket!', '', { timestamp: FIXED_TIMESTAMP }).id)
      .toBe('my-first-rocket');
  });

  it('falls back to a usable id for a name with no alphanumerics', () => {
    expect(createRocket('!!!', '', { timestamp: FIXED_TIMESTAMP }).id).toBe('rocket');
  });

  it('is deterministic when given an explicit id and timestamp', () => {
    const a = createRocket('R', 'd', { id: 'fixed', timestamp: FIXED_TIMESTAMP });
    const b = createRocket('R', 'd', { id: 'fixed', timestamp: FIXED_TIMESTAMP });
    expect(a).toEqual(b);
  });
});

describe('nextId', () => {
  it('starts at 1', () => {
    expect(nextId([], 'comp')).toBe('comp_1');
  });

  it('continues past the highest existing id', () => {
    expect(nextId(['comp_1', 'comp_2', 'comp_7'], 'comp')).toBe('comp_8');
  });

  it('does not reuse the id of a removed component', () => {
    // comp_2 is gone, but the next id must still be comp_4 — reusing comp_2
    // would silently re-point any connection that outlived it.
    expect(nextId(['comp_1', 'comp_3'], 'comp')).toBe('comp_4');
  });

  it('ignores ids with a different prefix', () => {
    expect(nextId(['conn_9', 'comp_2'], 'comp')).toBe('comp_3');
  });
});

describe('immutability', () => {
  it('leaves the original design untouched on every operation', () => {
    const original = seed();
    const snapshot = JSON.stringify(original);

    addStage(original, 'Second', 1);
    addComponent(original, registry, 'engine_s_solid', 0);
    removeComponent(original, original.components[0]!.instanceId);
    configureComponent(original, original.components[0]!.instanceId, { mass_kg: 5 });
    moveComponent(original, original.components[0]!.instanceId, { z: 9 });

    expect(JSON.stringify(original)).toBe(snapshot);
  });

  it('does not advance timestamps on edits', () => {
    const design = seed();
    const edited = addStage(design, 'Second', 1);
    // Timestamps advance only through `touch`, at the point of an actual save.
    expect(edited.updatedAt).toBe(design.updatedAt);
  });
});

describe('touch', () => {
  it('advances updatedAt and leaves createdAt alone', () => {
    const design = seed();
    const stamped = touch(design, '2027-06-01T00:00:00.000Z');
    expect(stamped.updatedAt).toBe('2027-06-01T00:00:00.000Z');
    expect(stamped.createdAt).toBe(design.createdAt);
  });
});

describe('stage operations', () => {
  it('appends stages in order', () => {
    let design = seed();
    design = addStage(design, 'Second Stage', 2);

    expect(design.stages.map(s => s.index)).toEqual([0, 1]);
    expect(design.stages[1]!.name).toBe('Second Stage');
    expect(design.stages[1]!.ignitionDelay_s).toBe(2);
  });

  it('removes a stage with its components and reindexes the rest', () => {
    let design = seed();
    design = addStage(design, 'Second', 1);
    design = addComponent(design, registry, 'engine_s_solid', 1, { z: 0 });
    design = addStage(design, 'Third', 1);
    design = addComponent(design, registry, 'nose_s_ogive', 2, { z: 0 });

    design = removeStage(design, 1);

    expect(design.stages.map(s => s.index)).toEqual([0, 1]);
    // The third stage's component moved down to index 1 with its stage.
    expect(design.components.map(c => c.defId).sort()).toEqual([
      'body_s_short',
      'nose_s_ogive',
    ]);
    expect(design.components.find(c => c.defId === 'nose_s_ogive')!.stageIndex).toBe(1);
  });

  it('drops connections into a removed stage', () => {
    let design = seed();
    design = addStage(design, 'Second', 1);
    design = addComponent(design, registry, 'body_s_short', 1, { z: 0 });

    const [a, b] = design.components;
    design = connectComponents(design, a!.instanceId, 'top', b!.instanceId, 'bottom');
    expect(design.connections).toHaveLength(1);

    design = removeStage(design, 1);
    expect(design.connections).toHaveLength(0);
  });

  it('rejects an out-of-range stage index', () => {
    expect(() => removeStage(seed(), 5)).toThrow(RocketDesignError);
    expect(() => setStageIgnitionDelay(seed(), -1, 1)).toThrow(RocketDesignError);
  });

  it('clamps a negative ignition delay to zero', () => {
    const design = setStageIgnitionDelay(seed(), 0, -5);
    expect(design.stages[0]!.ignitionDelay_s).toBe(0);
  });
});

describe('component operations', () => {
  it('rejects an unknown component definition', () => {
    expect(() => addComponent(seed(), registry, 'no_such_part', 0)).toThrow(
      RocketDesignError,
    );
  });

  it('rejects placement into a stage that does not exist', () => {
    expect(() => addComponent(seed(), registry, 'body_s_short', 3)).toThrow(
      RocketDesignError,
    );
  });

  it('removes a component and every connection that touched it', () => {
    let design = seed();
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 1 });

    const [body, nose] = design.components;
    design = connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base');
    expect(design.connections).toHaveLength(1);

    design = removeComponent(design, nose!.instanceId);
    expect(design.components).toHaveLength(1);
    expect(design.connections).toHaveLength(0);
  });

  it('merges configuration overrides rather than replacing them', () => {
    let design = seed();
    const id = design.components[0]!.instanceId;

    design = configureComponent(design, id, { fillFraction: 0.5 });
    design = configureComponent(design, id, { throttle: 0.8 });

    expect(design.components[0]!.configOverrides).toEqual({
      fillFraction: 0.5,
      throttle: 0.8,
    });
  });

  it('moves a component, keeping unspecified axes', () => {
    let design = seed();
    const id = design.components[0]!.instanceId;

    design = moveComponent(design, id, { x: 1, z: 5 });
    design = moveComponent(design, id, { z: 9 });

    const moved = design.components[0]!;
    expect(moved.offset_x).toBe(1);
    expect(moved.offset_z).toBe(9);
  });

  it('rejects operations on a component that does not exist', () => {
    const design = seed();
    expect(() => removeComponent(design, 'ghost')).toThrow(RocketDesignError);
    expect(() => configureComponent(design, 'ghost', {})).toThrow(RocketDesignError);
    expect(() => moveComponent(design, 'ghost', { z: 1 })).toThrow(RocketDesignError);
  });
});

describe('connection operations', () => {
  function twoParts() {
    let design = seed();
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 1 });
    return design;
  }

  it('connects two components through named attachment points', () => {
    let design = twoParts();
    const [body, nose] = design.components;

    design = connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base');

    expect(design.connections).toHaveLength(1);
    expect(design.connections[0]!.type).toBe('structural');
  });

  it('rejects a self-connection', () => {
    const design = twoParts();
    const id = design.components[0]!.instanceId;
    expect(() => connectComponents(design, id, 'top', id, 'bottom')).toThrow(
      RocketDesignError,
    );
  });

  it('rejects a duplicate connection', () => {
    let design = twoParts();
    const [body, nose] = design.components;
    design = connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base');

    expect(() =>
      connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base'),
    ).toThrow(RocketDesignError);
  });

  it('rejects an attachment point that does not exist', () => {
    const design = twoParts();
    const [body, nose] = design.components;
    expect(() =>
      connectComponents(
        design,
        body!.instanceId,
        'nowhere',
        nose!.instanceId,
        'base',
        'structural',
        registry,
      ),
    ).toThrow(RocketDesignError);
  });

  it('rejects a category the attachment point does not accept', () => {
    let design = seed();
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    const [body, engine] = design.components;

    // A body tube's top accepts nose cones and tanks, not engines.
    expect(() =>
      connectComponents(
        design,
        body!.instanceId,
        'top',
        engine!.instanceId,
        'mount',
        'structural',
        registry,
      ),
    ).toThrow(/does not.*accept/i);
  });

  it('disconnects by id', () => {
    let design = twoParts();
    const [body, nose] = design.components;
    design = connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base');

    design = disconnectComponents(design, design.connections[0]!.id);
    expect(design.connections).toHaveLength(0);
  });

  it('rejects disconnecting something that is not connected', () => {
    expect(() => disconnectComponents(twoParts(), 'conn_99')).toThrow(RocketDesignError);
  });
});

describe('validateDesign — structural checks', () => {
  it('accepts a well-formed design', () => {
    let design = seed();
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    const result = validateDesign(design, registry);
    expect(result.valid).toBe(true);
    expect(result.errors).toEqual([]);
  });

  it('rejects a design with no stages', () => {
    const result = validateDesign(
      createRocket('empty', '', { timestamp: FIXED_TIMESTAMP }),
      registry,
    );
    expect(result.valid).toBe(false);
    expect(result.errors.map(e => e.code)).toContain('NO_STAGES');
    expect(result.errors.map(e => e.code)).toContain('NO_COMPONENTS');
  });

  it('reports a component pointing at a missing definition', () => {
    const design = seed();
    const broken = {
      ...design,
      components: [{ ...design.components[0]!, defId: 'vanished' }],
    };
    const result = validateDesign(broken, registry);
    expect(result.errors.map(e => e.code)).toContain('MISSING_DEF');
  });

  it('reports a component pointing at a missing stage', () => {
    const design = seed();
    const broken = {
      ...design,
      components: [{ ...design.components[0]!, stageIndex: 9 }],
    };
    expect(validateDesign(broken, registry).errors.map(e => e.code)).toContain(
      'INVALID_STAGE_REF',
    );
  });

  it('reports a dangling connection', () => {
    const design = seed();
    const broken = {
      ...design,
      connections: [
        {
          id: 'conn_1',
          fromInstanceId: 'ghost',
          fromAttachmentId: 'top',
          toInstanceId: design.components[0]!.instanceId,
          toAttachmentId: 'bottom',
          type: 'structural' as const,
        },
      ],
    };
    expect(validateDesign(broken, registry).errors.map(e => e.code)).toContain(
      'DANGLING_CONNECTION',
    );
  });

  it('reports a duplicate instance id', () => {
    const design = seed();
    const broken = {
      ...design,
      components: [design.components[0]!, design.components[0]!],
    };
    expect(validateDesign(broken, registry).errors.map(e => e.code)).toContain(
      'DUPLICATE_INSTANCE_ID',
    );
  });

  it('warns about an empty stage without failing the design', () => {
    let design = seed();
    design = addComponent(design, registry, 'engine_s_solid', 0, { z: 0 });
    design = addStage(design, 'Empty Stage', 1);

    const result = validateDesign(design, registry);
    expect(result.valid).toBe(true);
    expect(result.warnings.join(' ')).toMatch(/no components/);
  });

  it('warns when the first stage has no engine', () => {
    expect(validateDesign(seed(), registry).warnings.join(' ')).toMatch(/no engine/);
  });
});

describe('query helpers', () => {
  it('finds the components in a stage', () => {
    let design = seed();
    design = addStage(design, 'Second', 1);
    design = addComponent(design, registry, 'engine_s_solid', 1, { z: 0 });

    expect(getStageComponents(design, 0)).toHaveLength(1);
    expect(getStageComponents(design, 1)).toHaveLength(1);
    expect(getStageComponents(design, 5)).toHaveLength(0);
  });

  it('finds the connections touching a component from either end', () => {
    let design = seed();
    design = addComponent(design, registry, 'nose_s_ogive', 0, { z: 1 });
    const [body, nose] = design.components;
    design = connectComponents(design, body!.instanceId, 'top', nose!.instanceId, 'base');

    expect(getComponentConnections(design, body!.instanceId)).toHaveLength(1);
    expect(getComponentConnections(design, nose!.instanceId)).toHaveLength(1);
  });

  it('sums dry mass over the whole design and per stage', () => {
    let design = seed();
    design = addStage(design, 'Second', 1);
    design = addComponent(design, registry, 'nose_s_ogive', 1, { z: 0 });

    // Body tube 12 kg + ogive nose 8 kg.
    expect(computeTotalMass(design, registry)).toBe(20);
    expect(computeStageMass(design, registry, 0)).toBe(12);
    expect(computeStageMass(design, registry, 1)).toBe(8);
  });

  it('treats an unknown definition as massless rather than throwing', () => {
    const design = seed();
    const broken = {
      ...design,
      components: [{ ...design.components[0]!, defId: 'vanished' }],
    };
    expect(computeTotalMass(broken, registry)).toBe(0);
  });
});
