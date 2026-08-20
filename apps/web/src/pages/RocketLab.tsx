import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import type { ComponentDef } from '@lostintospace/simulation-engine/core/component-types';

import { Badge, Button, Card, EmptyState, Input, Modal } from '@/components/ui';
import { PRESETS, buildPreset } from '@/lib/presets';
import { useMissionStore } from '@/stores/missionStore';
import { cn } from '@/lib/utils';

/**
 * Rocket Lab — the component catalogue and the way into the Builder.
 *
 * Every component and every number here comes from the simulation engine's
 * stock registry, which is the same source the builder and the flight
 * simulation read. There is no second catalogue: a spec shown on this page is
 * the spec that will fly.
 */

const CATEGORY_LABELS: Record<string, string> = {
  engine: 'Engines',
  fuel_tank: 'Fuel tanks',
  oxidizer_tank: 'Oxidiser tanks',
  body: 'Structures',
  nose_cone: 'Nose cones',
  fin: 'Fins',
  payload: 'Payload',
  decoupler: 'Separation',
  avionics: 'Avionics',
  guidance: 'Guidance',
  parachute: 'Recovery',
  heat_shield: 'Thermal',
  landing_leg: 'Landing',
};

export default function RocketLab() {
  const navigate = useNavigate();
  const setDesign = useMissionStore((s) => s.setDesign);
  const registry = useMemo(() => createStockRegistry(), []);
  const components = useMemo(() => registry.listAll(), [registry]);

  const [query, setQuery] = useState('');
  const [category, setCategory] = useState<string | null>(null);
  const [selected, setSelected] = useState<ComponentDef | null>(null);

  const categories = useMemo(() => {
    const counts = new Map<string, number>();
    for (const c of components) counts.set(c.category, (counts.get(c.category) ?? 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1]);
  }, [components]);

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return components.filter((c) => {
      if (category && c.category !== category) return false;
      if (!needle) return true;
      return (
        c.name.toLowerCase().includes(needle) ||
        c.description?.toLowerCase().includes(needle) ||
        c.category.toLowerCase().includes(needle)
      );
    });
  }, [components, query, category]);

  const startFrom = (presetId: string) => {
    const design = buildPreset(presetId);
    if (design) {
      setDesign(design, 'preset');
      navigate('/builder');
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-8 space-y-10">
      <header>
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-2">Rocket Lab</h1>
        <p className="text-sm text-space-400 max-w-2xl leading-relaxed">
          {components.length} components, each with the mass, thrust, specific impulse and
          structural limits the simulation actually uses. Pick a starting design, or browse the
          parts first.
        </p>
      </header>

      {/* Starting designs */}
      <section aria-labelledby="presets-heading">
        <h2 id="presets-heading" className="font-display text-sm font-semibold text-space-200 mb-3">
          Start from a design
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          {PRESETS.map((preset) => (
            <Card key={preset.id} className="flex flex-col gap-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="font-display text-sm font-semibold text-space-100">
                  {preset.name}
                </h3>
                <Badge
                  variant={preset.difficulty === 'starter' ? 'nominal' : 'default'}
                  className="shrink-0"
                >
                  {preset.difficulty}
                </Badge>
              </div>
              <p className="text-xs text-space-400 leading-relaxed">{preset.summary}</p>
              <p className="text-2xs text-space-500 leading-relaxed">
                <span className="text-space-400">Teaches:</span> {preset.teaches}
              </p>
              <Button size="sm" className="mt-auto" onClick={() => startFrom(preset.id)}>
                Open in Builder
              </Button>
            </Card>
          ))}
        </div>
      </section>

      {/* Component catalogue */}
      <section aria-labelledby="catalog-heading" className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="catalog-heading" className="font-display text-sm font-semibold text-space-200">
            Component catalogue
          </h2>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search components…"
            aria-label="Search components"
            className="w-full sm:w-64"
          />
        </div>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
          <button
            onClick={() => setCategory(null)}
            className={cn(
              'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
              category === null
                ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
            )}
            aria-pressed={category === null}
          >
            All ({components.length})
          </button>
          {categories.map(([key, count]) => (
            <button
              key={key}
              onClick={() => setCategory(category === key ? null : key)}
              className={cn(
                'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
                category === key
                  ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                  : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
              )}
              aria-pressed={category === key}
            >
              {CATEGORY_LABELS[key] ?? key} ({count})
            </button>
          ))}
        </div>

        {visible.length === 0 ? (
          <EmptyState
            title="No components match"
            description="Try a different search term or clear the category filter."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {visible.map((component) => (
              <li key={component.id}>
                <button
                  onClick={() => setSelected(component)}
                  className="w-full text-left glass-panel p-4 hover:border-accent-cyan/40 transition-colors focus-ring"
                >
                  <div className="flex items-start justify-between gap-2 mb-1.5">
                    <span className="font-medium text-sm text-space-100">{component.name}</span>
                    <Badge className="shrink-0 text-2xs">
                      {CATEGORY_LABELS[component.category] ?? component.category}
                    </Badge>
                  </div>
                  <p className="text-2xs text-space-500 leading-relaxed line-clamp-2 mb-3">
                    {component.description}
                  </p>
                  <dl className="flex flex-wrap gap-x-4 gap-y-1 text-2xs">
                    <div className="flex gap-1">
                      <dt className="text-space-600">Mass</dt>
                      <dd className="text-space-300 font-mono">{component.mass_kg} kg</dd>
                    </div>
                    {'thrustSeaLevel_N' in component && (
                      <div className="flex gap-1">
                        <dt className="text-space-600">Thrust</dt>
                        <dd className="text-accent-cyan font-mono">
                          {((component as never as { thrustSeaLevel_N: number }).thrustSeaLevel_N /
                            1000).toFixed(0)}{' '}
                          kN
                        </dd>
                      </div>
                    )}
                    {'propellantMass_kg' in component && (
                      <div className="flex gap-1">
                        <dt className="text-space-600">Propellant</dt>
                        <dd className="text-space-300 font-mono">
                          {(component as never as { propellantMass_kg: number }).propellantMass_kg} kg
                        </dd>
                      </div>
                    )}
                  </dl>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <ComponentDetail component={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

/** Full specification for one component, straight from its registry entry. */
function ComponentDetail({
  component,
  onClose,
}: {
  component: ComponentDef | null;
  onClose: () => void;
}) {
  if (!component) return null;

  const record = component as unknown as Record<string, unknown>;
  const spec = (label: string, key: string, unit = '', scale = 1) => {
    const value = record[key];
    if (typeof value !== 'number' || !Number.isFinite(value)) return null;
    return { label, value: (value / scale).toLocaleString(undefined, { maximumFractionDigits: 2 }), unit };
  };

  const specs = [
    spec('Mass', 'mass_kg', 'kg'),
    spec('Length', 'length_m', 'm'),
    spec('Diameter', 'diameter_m', 'm'),
    spec('Sea-level thrust', 'thrustSeaLevel_N', 'kN', 1000),
    spec('Vacuum thrust', 'thrustVacuum_N', 'kN', 1000),
    spec('Sea-level Isp', 'isp_seaLevel_s', 's'),
    spec('Vacuum Isp', 'isp_vacuum_s', 's'),
    spec('Propellant', 'propellantMass_kg', 'kg'),
    spec('Drag coefficient', 'dragCoefficient'),
    spec('Cost', 'cost'),
  ].filter(Boolean) as { label: string; value: string; unit: string }[];

  const structural = record.structural as
    | { maxAxialLoad_N: number; maxDynamicPressure_Pa: number }
    | undefined;
  const failureModes = (record.failureModes ?? []) as { id: string; name: string; condition: string }[];

  return (
    <Modal open onClose={onClose} title={component.name}>
      <div className="space-y-5">
        <p className="text-xs text-space-400 leading-relaxed">{component.description}</p>

        <div>
          <h4 className="text-2xs uppercase tracking-wider text-space-500 mb-2">Specifications</h4>
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
            {specs.map((s) => (
              <div key={s.label} className="flex justify-between gap-2 border-b border-space-800/60 pb-1">
                <dt className="text-2xs text-space-500">{s.label}</dt>
                <dd className="text-2xs font-mono text-space-200">
                  {s.value}
                  {s.unit && <span className="text-space-500"> {s.unit}</span>}
                </dd>
              </div>
            ))}
          </dl>
        </div>

        {structural && (
          <div>
            <h4 className="text-2xs uppercase tracking-wider text-space-500 mb-2">
              Structural limits
            </h4>
            <p className="text-2xs text-space-400 leading-relaxed">
              Fails above{' '}
              <span className="font-mono text-space-200">
                {(structural.maxAxialLoad_N / 1000).toFixed(0)} kN
              </span>{' '}
              axial load or{' '}
              <span className="font-mono text-space-200">
                {(structural.maxDynamicPressure_Pa / 1000).toFixed(0)} kPa
              </span>{' '}
              dynamic pressure. The weakest component on a stack sets the whole vehicle's limit.
            </p>
          </div>
        )}

        {failureModes.length > 0 && (
          <div>
            <h4 className="text-2xs uppercase tracking-wider text-space-500 mb-2">
              Known failure modes
            </h4>
            <ul className="space-y-1.5">
              {failureModes.map((mode) => (
                <li key={mode.id} className="text-2xs text-space-400 leading-relaxed">
                  <span className="text-space-200">{mode.name}</span> — {mode.condition}
                </li>
              ))}
            </ul>
          </div>
        )}

        <p className="text-2xs text-space-600 leading-relaxed border-t border-space-800 pt-3">
          Values are engineering-plausible figures chosen for teaching, not the specification of
          any real hardware.
        </p>
      </div>
    </Modal>
  );
}
