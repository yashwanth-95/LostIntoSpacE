import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import { useRocketBuilder } from '@lostintospace/simulation-engine/adapters/useRocketBuilder';
import { createRocket } from '@lostintospace/simulation-engine/core/rocket-design';
import type {
  ComponentCategory,
  ComponentDef,
  EngineDef,
  FinDef,
  NoseConeDef,
} from '@lostintospace/simulation-engine/core/component-types';

import { RocketProfile } from '@/components/features/build/RocketProfile';
import { ThrustCurve } from '@/components/features/build/ThrustCurve';
import {
  Badge,
  Button,
  Gauge,
  Input,
  Panel,
  Readout,
  SectionRule,
  StatusDot,
} from '@/components/ui';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass } from '@/lib/utils';

/**
 * The rocket builder.
 *
 * Three regions, in the order an engineer works: parts on the left, the vehicle
 * in the middle, consequences on the right. Every number in the right-hand
 * column comes from `useRocketBuilder`, which is the same analysis handed to
 * the flight simulation — this page computes no physics of its own, so what it
 * shows and what gets flown cannot diverge.
 *
 * The drawing is the point. Before this rebuild the page was three columns of
 * lists and you could assemble an entire vehicle without ever seeing it. The
 * middle column is now a scale elevation that regenerates on every edit, with
 * the centre of gravity and centre of pressure marked and the static margin
 * drawn as the distance between them — the one relationship that a margin
 * printed as a number completely fails to convey.
 */

/** Categories grouped the way a build actually proceeds. */
const GROUPS: readonly { label: string; categories: readonly ComponentCategory[] }[] = [
  { label: 'Airframe', categories: ['nose_cone', 'fairing', 'body', 'coupler', 'interstage'] },
  { label: 'Propulsion', categories: ['engine', 'motor_mount', 'fuel_tank', 'oxidizer_tank'] },
  { label: 'Aero', categories: ['fin'] },
  { label: 'Structure', categories: ['bulkhead', 'centering_ring'] },
  { label: 'Avionics', categories: ['avionics', 'guidance', 'sensor', 'battery'] },
  { label: 'Mission', categories: ['payload', 'decoupler'] },
  { label: 'Recovery', categories: ['parachute', 'heat_shield', 'landing_leg'] },
];

const CATEGORY_LABEL: Partial<Record<ComponentCategory, string>> = {
  nose_cone: 'Nose cones',
  fairing: 'Fairings',
  body: 'Body tubes',
  coupler: 'Couplers',
  interstage: 'Interstages',
  engine: 'Motors and engines',
  motor_mount: 'Motor mounts',
  fuel_tank: 'Fuel tanks',
  oxidizer_tank: 'Oxidiser tanks',
  fin: 'Fin sets',
  bulkhead: 'Bulkheads',
  centering_ring: 'Centering rings',
  avionics: 'Flight computers',
  guidance: 'Guidance',
  sensor: 'Sensors',
  battery: 'Batteries',
  payload: 'Payloads',
  decoupler: 'Separators',
  parachute: 'Parachutes',
  heat_shield: 'Heat shields',
  landing_leg: 'Landing legs',
};

export default function Builder() {
  const navigate = useNavigate();
  const storedDesign = useMissionStore((s) => s.design);
  const setStoredDesign = useMissionStore((s) => s.setDesign);

  const registry = useMemo(() => createStockRegistry(), []);
  const initialDesign = useMemo(
    () => storedDesign ?? createRocket('My Rocket', 'A new design'),
    // Only on mount: `useRocketBuilder` owns the design from then on, and
    // re-seeding it on every store change would discard the user's edits.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const builder = useRocketBuilder({ initialDesign, registry });
  const [activeStage, setActiveStage] = useState(0);
  const [activeGroup, setActiveGroup] = useState<string>(GROUPS[0]!.label);
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<string | null>(null);
  const [cutaway, setCutaway] = useState(false);

  // Mirror the design into the store so Launch and Mission Control see it.
  useEffect(() => {
    setStoredDesign(builder.design, storedDesign ? 'loaded' : 'blank');
    // `setStoredDesign` clears the previous result, which is correct: a changed
    // rocket invalidates the flight that was run with the old one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [builder.design]);

  const { analysis, validation } = builder;
  const stageCount = builder.design.stages.length;
  const canFly = validation.valid && stageCount > 0;

  const group = GROUPS.find((g) => g.label === activeGroup) ?? GROUPS[0]!;
  const available = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const items: { category: ComponentCategory; components: ComponentDef[] }[] = [];
    for (const category of group.categories) {
      const components = registry
        .listByCategory(category as never)
        .filter(
          (c: ComponentDef) =>
            !needle ||
            c.name.toLowerCase().includes(needle) ||
            c.description.toLowerCase().includes(needle),
        );
      if (components.length > 0) items.push({ category, components });
    }
    return items;
  }, [registry, group, query]);

  const selectedComponent = selected
    ? builder.design.components.find((c) => c.instanceId === selected)
    : undefined;
  const selectedDef = selectedComponent ? registry.get(selectedComponent.defId) : undefined;

  const margin = analysis.stabilityWet.stabilityMargin_cal;
  const twr = analysis.liftoffTWR;

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-6">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-4 hairline-b pb-4">
        <div>
          <p className="t-label mb-1">Build · Vehicle assembly</p>
          <h1 className="font-display text-3xl leading-none text-ink-50">
            {builder.design.name}
          </h1>
          <p className="mt-1.5 font-mono text-tiny text-ink-500">
            {analysis.stages.length} stage{analysis.stages.length === 1 ? '' : 's'} ·{' '}
            {builder.design.components.length} components ·{' '}
            {analysis.totalLength_m.toFixed(2)} m · {formatMass(analysis.totalWetMass_kg)} on
            the pad
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" onClick={builder.undo} disabled={!builder.canUndo}>
            Undo
          </Button>
          <Button size="sm" variant="ghost" onClick={builder.redo} disabled={!builder.canRedo}>
            Redo
          </Button>
          <Button
            size="sm"
            onClick={() => navigate('/launch')}
            disabled={!canFly}
            title={canFly ? undefined : 'Fix the validation errors first'}
          >
            Configure launch →
          </Button>
        </div>
      </header>

      {builder.lastError && (
        <Panel tone="oxide" className="mb-4 py-2.5">
          <p className="text-xs text-signal-oxide-bright">{builder.lastError.message}</p>
        </Panel>
      )}

      <div className="grid gap-5 xl:grid-cols-[300px_minmax(0,1fr)_320px]">
        {/* ── Parts bin ─────────────────────────────────────── */}
        <aside className="space-y-3">
          <SectionRule
            label="Parts"
            aside={<span className="font-mono text-micro text-ink-600">{registry.size}</span>}
          />

          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search parts…"
            aria-label="Search components"
          />

          <div className="flex flex-wrap gap-1">
            {GROUPS.map((g) => (
              <button
                key={g.label}
                onClick={() => setActiveGroup(g.label)}
                className={cn(
                  'rounded-instrument border px-2 py-0.5 font-condensed text-micro uppercase tracking-label',
                  'transition-colors duration-quick ease-instrument focus-ring',
                  activeGroup === g.label
                    ? 'border-signal-flame/40 bg-signal-flame/10 text-signal-flame-bright'
                    : 'border-ink-700 bg-ink-850 text-ink-500 hover:text-ink-200',
                )}
              >
                {g.label}
              </button>
            ))}
          </div>

          <div className="max-h-[62vh] space-y-4 overflow-y-auto pr-1">
            {available.map(({ category, components }) => (
              <div key={category}>
                <h3 className="t-label mb-1.5">{CATEGORY_LABEL[category] ?? category}</h3>
                <ul className="space-y-1">
                  {components.map((component) => (
                    <li key={component.id}>
                      <PartButton
                        component={component}
                        disabled={stageCount === 0}
                        onAdd={() => builder.addComponent(component.id, activeStage)}
                      />
                    </li>
                  ))}
                </ul>
              </div>
            ))}
            {available.length === 0 && (
              <p className="py-6 text-center text-xs text-ink-500">
                Nothing in this group matches “{query}”.
              </p>
            )}
          </div>

          {stageCount === 0 && (
            <p className="text-tiny leading-relaxed text-signal-caution">
              Add a stage before adding components — every part has to belong to one.
            </p>
          )}
        </aside>

        {/* ── The vehicle ───────────────────────────────────── */}
        <section className="space-y-4">
          <SectionRule
            label="Side elevation"
            aside={
              <button
                onClick={() => setCutaway((c) => !c)}
                className={cn(
                  'rounded-instrument border px-2 py-0.5 font-condensed text-micro uppercase tracking-label',
                  'transition-colors duration-quick focus-ring',
                  cutaway
                    ? 'border-signal-cryo/40 bg-signal-cryo/10 text-signal-cryo-bright'
                    : 'border-ink-700 text-ink-500 hover:text-ink-200',
                )}
              >
                Cutaway
              </button>
            }
          />

          <RocketProfile
            layout={analysis.layout}
            cg_m={analysis.stabilityWet.cg_m}
            cp_m={analysis.stabilityWet.cp_m}
            referenceDiameter_m={analysis.stabilityWet.referenceDiameter_m}
            selectedInstanceId={selected}
            onSelect={setSelected}
            cutaway={cutaway}
            className="min-h-[320px]"
          />

          {selectedComponent && selectedDef && (
            <Panel className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-display text-lg leading-tight text-ink-50">
                    {selectedDef.name}
                  </h3>
                  <p className="mt-1 max-w-prose text-xs leading-relaxed text-ink-400">
                    {selectedDef.description}
                  </p>
                </div>
                <Button
                  size="xs"
                  variant="danger"
                  onClick={() => {
                    builder.removeComponent(selectedComponent.instanceId);
                    setSelected(null);
                  }}
                >
                  Remove
                </Button>
              </div>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
                <Readout inline label="Mass" value={selectedDef.mass_kg.toFixed(2)} unit="kg" />
                <Readout inline label="Length" value={selectedDef.length_m.toFixed(3)} unit="m" />
                <Readout
                  inline
                  label="Diameter"
                  value={selectedDef.outerDiameter_m.toFixed(3)}
                  unit="m"
                />
                <Readout inline label="Stage" value={selectedComponent.stageIndex} />
              </dl>

              <ComponentSpecifics def={selectedDef} />
            </Panel>
          )}

          <SectionRule
            label="Stages"
            aside={
              <Button
                size="xs"
                variant="outline"
                onClick={() => builder.addStage(`Stage ${stageCount + 1}`)}
              >
                + Add stage
              </Button>
            }
          />

          {stageCount === 0 ? (
            <Panel>
              <p className="text-xs leading-relaxed text-ink-400">
                A rocket needs at least one stage. Add one, then give it an engine, a body
                tube and a nose cone — that is the minimum that flies.
              </p>
            </Panel>
          ) : (
            <ul className="space-y-2">
              {builder.design.stages.map((stage, index) => {
                const stageAnalysis = analysis.stages[index];
                const components = builder.design.components.filter(
                  (c) => c.stageIndex === index,
                );
                return (
                  <li key={stage.index}>
                    <Panel
                      flush
                      className={cn(
                        'cursor-pointer p-3 transition-colors duration-quick',
                        activeStage === index && 'border-signal-flame/40',
                      )}
                      onClick={() => setActiveStage(index)}
                    >
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={activeStage === index ? 'flame' : 'default'}>
                            Stage {index}
                          </Badge>
                          <span className="text-sm text-ink-200">{stage.name}</span>
                          {index === 0 && (
                            <span className="font-mono text-micro text-ink-600">fires first</span>
                          )}
                        </div>
                        <Button
                          size="xs"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            builder.removeStage(index);
                            setActiveStage(0);
                          }}
                        >
                          Remove
                        </Button>
                      </div>

                      {stageAnalysis && (
                        <dl className="mb-2 grid grid-cols-2 gap-x-5 gap-y-1 sm:grid-cols-4">
                          <Readout
                            inline
                            size="sm"
                            label="Wet mass"
                            value={formatMass(stageAnalysis.wetMass_kg)}
                          />
                          <Readout
                            inline
                            size="sm"
                            label="Thrust"
                            value={(stageAnalysis.thrustSeaLevel_N / 1000).toFixed(0)}
                            unit="kN"
                          />
                          <Readout
                            inline
                            size="sm"
                            label="Burn"
                            value={stageAnalysis.burnTime_s.toFixed(0)}
                            unit="s"
                          />
                          <Readout
                            inline
                            size="sm"
                            label="Δv"
                            value={stageAnalysis.deltaV_ms.toFixed(0)}
                            unit="m/s"
                          />
                        </dl>
                      )}

                      {components.length === 0 ? (
                        <p className="text-tiny text-ink-500">
                          Empty. Select this stage, then add parts from the left.
                        </p>
                      ) : (
                        <ul className="flex flex-wrap gap-1">
                          {components.map((component) => {
                            const def = registry.get(component.defId);
                            return (
                              <li key={component.instanceId}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setSelected(component.instanceId);
                                  }}
                                  className={cn(
                                    'rounded-instrument border px-1.5 py-0.5 text-micro transition-colors focus-ring',
                                    selected === component.instanceId
                                      ? 'border-ink-300 bg-ink-800 text-ink-50'
                                      : 'border-ink-700 bg-ink-850 text-ink-300 hover:border-ink-500',
                                  )}
                                >
                                  {def?.name ?? component.defId}
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </Panel>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* ── Engineering readout ───────────────────────────── */}
        <aside className="space-y-4">
          <SectionRule label="Engineering" />

          <Panel className="space-y-4">
            <Readout size="xl" label="Launch mass" value={formatMass(analysis.totalWetMass_kg)} />

            <div className="space-y-3 hairline-t pt-3">
              <MetricRow
                label="Liftoff thrust-to-weight"
                value={twr.toFixed(2)}
                tone={twr < 1 ? 'critical' : twr < 1.2 ? 'caution' : 'nominal'}
                gauge={{ value: twr, min: 0, max: 3, goodMin: 1.2, goodMax: 1.6 }}
                note={
                  twr < 1
                    ? 'Below 1.0 — this will not leave the pad.'
                    : twr < 1.2
                      ? 'It will fly, but slowly, and gravity losses will eat the budget.'
                      : twr > 2
                        ? 'Very high. Expect max-Q low in the atmosphere and heavy loads.'
                        : 'In the band real launchers use.'
                }
              />

              <MetricRow
                label="Static margin, fuelled"
                value={margin.toFixed(2)}
                unit="cal"
                tone={margin < 1 ? 'critical' : margin > 2.5 ? 'caution' : 'nominal'}
                gauge={{ value: margin, min: -1, max: 4, goodMin: 1, goodMax: 2 }}
                note={
                  margin < 0
                    ? 'Centre of pressure is ahead of centre of gravity. It will tumble.'
                    : margin < 1
                      ? 'Marginal. A gust will upset it.'
                      : margin > 2.5
                        ? 'Over-stable — it will weathercock hard into any crosswind.'
                        : 'Inside the 1–2 caliber target.'
                }
              />

              <MetricRow
                label="Static margin, empty"
                value={analysis.stabilityDry.stabilityMargin_cal.toFixed(2)}
                unit="cal"
                tone={analysis.stabilityDry.stabilityMargin_cal < 1 ? 'caution' : 'nominal'}
                note="Propellant burns off from ahead of the engine, so the margin shrinks in flight. This is usually the harder case."
              />
            </div>

            <dl className="space-y-2 hairline-t pt-3">
              <Readout
                inline
                label="Total Δv (ideal)"
                value={analysis.totalDeltaV_ms.toFixed(0)}
                unit="m/s"
              />
              <Readout
                inline
                label="Propellant fraction"
                value={(analysis.propellantMassFraction * 100).toFixed(0)}
                unit="%"
              />
              <Readout inline label="Payload" value={formatMass(analysis.payloadMass_kg)} />
              <Readout
                inline
                label="Reference area"
                value={analysis.referenceArea_m2.toFixed(3)}
                unit="m²"
              />
              <Readout inline label="Drag coefficient" value={analysis.dragCoefficient.toFixed(3)} />
              <Readout
                inline
                label="Centre of gravity"
                value={analysis.stabilityWet.cg_m.toFixed(2)}
                unit="m"
              />
              <Readout
                inline
                label="Centre of pressure"
                value={analysis.stabilityWet.cp_m.toFixed(2)}
                unit="m"
              />
            </dl>

            <p className="hairline-t pt-3 text-tiny leading-relaxed text-ink-500">
              Δv is the ideal figure from Tsiolkovsky. Gravity and drag losses take
              1.5–2 km/s of it on the way up, and the flight will show you how much.
            </p>
          </Panel>

          <MotorCurves registry={registry} design={builder.design} activeStage={activeStage} />

          <Panel
            tone={
              validation.errors.length > 0
                ? 'oxide'
                : validation.warnings.length > 0
                  ? 'caution'
                  : 'nominal'
            }
            className="space-y-2"
          >
            <div className="flex items-center gap-2">
              <StatusDot
                tone={
                  validation.errors.length > 0
                    ? 'critical'
                    : validation.warnings.length > 0
                      ? 'caution'
                      : 'nominal'
                }
              />
              <h2 className="t-label">Pre-flight validation</h2>
            </div>

            {validation.valid && validation.warnings.length === 0 ? (
              <p className="text-xs text-signal-nominal-bright">
                No problems found. This design is ready to fly.
              </p>
            ) : (
              <ul className="space-y-2">
                {validation.errors.map((issue, i) => (
                  <li key={`e${i}`} className="flex gap-2 text-tiny">
                    <StatusDot tone="critical" className="mt-1.5 shrink-0" />
                    <span className="leading-relaxed text-ink-200">{issue.message}</span>
                  </li>
                ))}
                {validation.warnings.map((issue, i) => (
                  <li key={`w${i}`} className="flex gap-2 text-tiny">
                    <StatusDot tone="caution" className="mt-1.5 shrink-0" />
                    <span className="leading-relaxed text-ink-400">{issue.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          <p className="text-tiny leading-relaxed text-ink-600">
            Not sure what to change?{' '}
            <Link to="/assistant" className="text-signal-flame hover:underline">
              Ask the assistant
            </Link>{' '}
            — it can see this exact design — or read{' '}
            <Link to="/learn/stability-margin" className="text-signal-flame hover:underline">
              why stability works this way
            </Link>
            .
          </p>
        </aside>
      </div>
    </div>
  );
}

/** One part in the picker, showing the number that distinguishes it from its siblings. */
function PartButton({
  component,
  disabled,
  onAdd,
}: {
  component: ComponentDef;
  disabled: boolean;
  onAdd: () => void;
}) {
  return (
    <button
      onClick={onAdd}
      disabled={disabled}
      title={component.description}
      className={cn(
        'w-full rounded-instrument border border-ink-800 bg-ink-900 px-2.5 py-2 text-left',
        'transition-colors duration-quick ease-instrument focus-ring',
        'hover:border-signal-flame/40 hover:bg-ink-850',
        'disabled:pointer-events-none disabled:opacity-40',
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-xs text-ink-200">{component.name}</span>
        <span className="shrink-0 font-mono text-micro text-ink-500">
          {component.mass_kg < 1
            ? `${(component.mass_kg * 1000).toFixed(0)} g`
            : `${component.mass_kg.toFixed(0)} kg`}
        </span>
      </div>
      <p className="mt-0.5 truncate font-mono text-[0.6rem] text-ink-600">
        {partSummary(component)}
      </p>
    </button>
  );
}

/** The one line that says what makes this part different from the next one. */
function partSummary(component: ComponentDef): string {
  switch (component.category) {
    case 'nose_cone':
    case 'fairing': {
      const def = component as NoseConeDef;
      const shape = (def.shape ?? '').replace(/_/g, ' ');
      return `${shape} · fineness ${def.finenessRatio?.toFixed(1) ?? '—'} · Cd ${def.dragCoefficient?.toFixed(2) ?? '—'}`;
    }
    case 'fin': {
      const def = component as FinDef;
      const shape = (def.shape ?? 'trapezoidal').replace(/_/g, ' ');
      return `${def.finCount}× ${shape} · span ${def.span_m.toFixed(2)} m`;
    }
    case 'engine': {
      const def = component as EngineDef;
      if (def.motorClass && def.totalImpulse_Ns) {
        return `class ${def.motorClass} · ${Math.round(def.totalImpulse_Ns)} N·s · ${def.burnTime_s?.toFixed(1)} s`;
      }
      return `${(def.thrustSeaLevel_N / 1000).toFixed(0)} kN · Isp ${def.isp_seaLevel_s} s`;
    }
    default:
      return `${component.length_m.toFixed(2)} m × ⌀${component.outerDiameter_m.toFixed(2)} m`;
  }
}

/** Category-specific detail for the inspector. */
function ComponentSpecifics({ def }: { def: ComponentDef }) {
  if (def.category === 'engine') {
    const engine = def as EngineDef;
    return (
      <div className="space-y-3 hairline-t pt-3">
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
          <Readout
            inline
            size="sm"
            label="Thrust (SL)"
            value={(engine.thrustSeaLevel_N / 1000).toFixed(1)}
            unit="kN"
          />
          <Readout
            inline
            size="sm"
            label="Thrust (vac)"
            value={(engine.thrust_N / 1000).toFixed(1)}
            unit="kN"
          />
          <Readout inline size="sm" label="Isp (SL)" value={engine.isp_seaLevel_s} unit="s" />
          <Readout inline size="sm" label="Isp (vac)" value={engine.isp_vacuum_s} unit="s" />
          {engine.totalImpulse_Ns !== undefined && (
            <Readout
              inline
              size="sm"
              label="Total impulse"
              value={Math.round(engine.totalImpulse_Ns)}
              unit="N·s"
            />
          )}
          {engine.burnTime_s !== undefined && (
            <Readout inline size="sm" label="Burn time" value={engine.burnTime_s} unit="s" />
          )}
          {engine.integralPropellant_kg > 0 && (
            <Readout
              inline
              size="sm"
              label="Propellant"
              value={engine.integralPropellant_kg.toFixed(3)}
              unit="kg"
            />
          )}
          <Readout
            inline
            size="sm"
            label="Restartable"
            value={engine.maxIgnitions > 1 ? `${engine.maxIgnitions}×` : 'no'}
            tone={engine.maxIgnitions > 1 ? 'nominal' : 'quiet'}
          />
        </dl>
        {engine.thrustCurve && engine.thrustCurve.length > 1 && (
          <ThrustCurve curve={engine.thrustCurve} className="h-28" />
        )}
        {engine.propellantType === 'solid' && (
          <p className="text-tiny leading-relaxed text-signal-caution">
            A solid motor cannot be throttled or shut down. Once lit, it burns to completion.
          </p>
        )}
      </div>
    );
  }

  if (def.category === 'nose_cone' || def.category === 'fairing') {
    const nose = def as NoseConeDef;
    return (
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 hairline-t pt-3 sm:grid-cols-4">
        <Readout inline size="sm" label="Profile" value={(nose.shape ?? '').replace(/_/g, ' ')} />
        <Readout inline size="sm" label="Fineness" value={nose.finenessRatio.toFixed(2)} />
        <Readout inline size="sm" label="Cd" value={nose.dragCoefficient.toFixed(3)} />
        {nose.material && <Readout inline size="sm" label="Material" value={nose.material} />}
      </dl>
    );
  }

  if (def.category === 'fin') {
    const fin = def as FinDef;
    return (
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 hairline-t pt-3 sm:grid-cols-4">
        <Readout inline size="sm" label="Count" value={fin.finCount} />
        <Readout
          inline
          size="sm"
          label="Planform"
          value={(fin.shape ?? 'trapezoidal').replace(/_/g, ' ')}
        />
        <Readout inline size="sm" label="Root chord" value={fin.rootChord_m.toFixed(3)} unit="m" />
        <Readout inline size="sm" label="Tip chord" value={fin.tipChord_m.toFixed(3)} unit="m" />
        <Readout inline size="sm" label="Span" value={fin.span_m.toFixed(3)} unit="m" />
        <Readout
          inline
          size="sm"
          label="Sweep"
          value={((fin.sweepAngle_rad * 180) / Math.PI).toFixed(0)}
          unit="°"
        />
      </dl>
    );
  }

  return null;
}

/** Thrust curves for whatever motors the active stage carries. */
function MotorCurves({
  registry,
  design,
  activeStage,
}: {
  registry: ReturnType<typeof createStockRegistry>;
  design: { components: readonly { defId: string; stageIndex: number; instanceId: string }[] };
  activeStage: number;
}) {
  const motors = design.components
    .filter((c) => c.stageIndex === activeStage)
    .map((c) => registry.get(c.defId))
    .filter(
      (d): d is EngineDef => !!d && d.category === 'engine' && (d.thrustCurve?.length ?? 0) > 1,
    );

  if (motors.length === 0) return null;

  return (
    <Panel className="space-y-3">
      <h2 className="t-label">Thrust curve · stage {activeStage}</h2>
      {motors.map((motor) => (
        <div key={motor.id} className="space-y-1">
          <div className="flex items-baseline justify-between">
            <span className="text-xs text-ink-200">{motor.designation ?? motor.name}</span>
            <span className="font-mono text-micro text-ink-500">
              {Math.round(motor.totalImpulse_Ns ?? 0)} N·s
            </span>
          </div>
          <ThrustCurve curve={motor.thrustCurve ?? []} className="h-24" />
        </div>
      ))}
      <p className="text-tiny leading-relaxed text-ink-500">
        Thrust is not constant. The grain's burning surface changes as it is consumed, and
        the shape of that change is a design choice.
      </p>
    </Panel>
  );
}

/** A metric with its acceptable band and a plain-language reading. */
function MetricRow({
  label,
  value,
  unit,
  tone,
  gauge,
  note,
}: {
  label: string;
  value: string;
  unit?: string;
  tone: 'nominal' | 'caution' | 'critical';
  gauge?: { value: number; min: number; max: number; goodMin: number; goodMax: number };
  note?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Readout inline label={label} value={value} unit={unit} tone={tone} />
      {gauge && (
        <Gauge
          value={gauge.value}
          min={gauge.min}
          max={gauge.max}
          goodMin={gauge.goodMin}
          goodMax={gauge.goodMax}
          tone={tone}
        />
      )}
      {note && <p className="text-tiny leading-relaxed text-ink-500">{note}</p>}
    </div>
  );
}
