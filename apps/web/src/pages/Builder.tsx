import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import { useRocketBuilder } from '@lostintospace/simulation-engine/adapters/useRocketBuilder';
import { createRocket } from '@lostintospace/simulation-engine/core/rocket-design';
import type { ComponentDef } from '@lostintospace/simulation-engine/core/component-types';

import { Badge, Button, Card } from '@/components/ui';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass } from '@/lib/utils';

/**
 * Rocket Builder.
 *
 * All engineering — mass, delta-v, thrust-to-weight, stability, validation —
 * comes from `useRocketBuilder` in the simulation engine. This page adds no
 * physics of its own; it is a presentation layer over the analysis the engine
 * already computes, which is what keeps the numbers here identical to the ones
 * the flight will use.
 */

const CATEGORY_ORDER = [
  'engine',
  'fuel_tank',
  'oxidizer_tank',
  'body',
  'nose_cone',
  'fin',
  'payload',
  'decoupler',
  'avionics',
  'guidance',
  'parachute',
  'heat_shield',
  'landing_leg',
];

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
  const [pickerCategory, setPickerCategory] = useState<string>('engine');

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

  const available = useMemo(
    () => registry.listByCategory(pickerCategory as never),
    [registry, pickerCategory],
  );

  return (
    <div className="mx-auto max-w-7xl px-6 py-8">
      <header className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">
            Rocket Builder
          </h1>
          <p className="text-sm text-space-400">
            {builder.design.name} · {analysis.stages.length} stage
            {analysis.stages.length === 1 ? '' : 's'} ·{' '}
            {builder.design.components.length} components
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
        <div className="mb-4 glass-panel border-severity-critical/40 p-3">
          <p className="text-xs text-severity-critical">{builder.lastError.message}</p>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-[280px_1fr_300px]">
        {/* Component picker */}
        <aside className="space-y-3">
          <h2 className="font-display text-sm font-semibold text-space-200">Add components</h2>

          <div className="flex flex-wrap gap-1">
            {CATEGORY_ORDER.filter((c) => registry.listByCategory(c as never).length > 0).map(
              (category) => (
                <button
                  key={category}
                  onClick={() => setPickerCategory(category)}
                  className={cn(
                    'px-2 py-0.5 rounded text-2xs border transition-colors focus-ring',
                    pickerCategory === category
                      ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                      : 'bg-space-800/50 text-space-500 border-space-700 hover:text-space-300',
                  )}
                >
                  {category.replace(/_/g, ' ')}
                </button>
              ),
            )}
          </div>

          <ul className="space-y-1.5 max-h-[520px] overflow-y-auto pr-1">
            {available.map((component: ComponentDef) => (
              <li key={component.id}>
                <button
                  onClick={() => builder.addComponent(component.id, activeStage)}
                  disabled={stageCount === 0}
                  className="w-full text-left glass-panel-dense p-2.5 hover:border-accent-cyan/40 transition-colors focus-ring disabled:opacity-40 disabled:pointer-events-none"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs text-space-200 truncate">{component.name}</span>
                    <span className="text-2xs font-mono text-space-500 shrink-0">
                      {component.mass_kg} kg
                    </span>
                  </div>
                </button>
              </li>
            ))}
          </ul>

          {stageCount === 0 && (
            <p className="text-2xs text-severity-warning">Add a stage before adding components.</p>
          )}
        </aside>

        {/* Stages */}
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-display text-sm font-semibold text-space-200">
              Stages{' '}
              <span className="text-2xs font-normal text-space-500">(0 is the bottom stage)</span>
            </h2>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => builder.addStage(`Stage ${stageCount + 1}`)}
            >
              + Add stage
            </Button>
          </div>

          {stageCount === 0 ? (
            <Card>
              <p className="text-xs text-space-400">
                A rocket needs at least one stage. Add one, then add an engine, tanks and a nose
                cone to it.
              </p>
            </Card>
          ) : (
            <ul className="space-y-3">
              {builder.design.stages.map((stage, index) => {
                const stageAnalysis = analysis.stages[index];
                const components = builder.design.components.filter(
                  (c) => c.stageIndex === index,
                );
                return (
                  <li key={stage.index}>
                    <Card
                      className={cn(
                        'space-y-3 cursor-pointer transition-colors',
                        activeStage === index && 'border-accent-cyan/40',
                      )}
                      onClick={() => setActiveStage(index)}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={activeStage === index ? 'cryo' : 'default'}>
                            Stage {index}
                          </Badge>
                          <span className="text-sm text-space-200">{stage.name}</span>
                        </div>
                        <Button
                          size="sm"
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
                        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-2xs">
                          <Metric label="Wet mass" value={formatMass(stageAnalysis.wetMass_kg)} />
                          <Metric
                            label="Thrust"
                            value={`${(stageAnalysis.thrustSeaLevel_N / 1000).toFixed(0)} kN`}
                          />
                          <Metric
                            label="Burn time"
                            value={`${stageAnalysis.burnTime_s.toFixed(0)} s`}
                          />
                          <Metric
                            label="Δv"
                            value={`${stageAnalysis.deltaV_ms.toFixed(0)} m/s`}
                          />
                        </dl>
                      )}

                      {components.length === 0 ? (
                        <p className="text-2xs text-space-500">
                          Empty. Select this stage and add components from the left.
                        </p>
                      ) : (
                        <ul className="flex flex-wrap gap-1.5">
                          {components.map((component) => {
                            const def = registry.get(component.defId);
                            return (
                              <li key={component.instanceId}>
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    builder.removeComponent(component.instanceId);
                                  }}
                                  className="group px-2 py-1 rounded border border-space-700 bg-space-800/50 text-2xs text-space-300 hover:border-severity-fatal/40 hover:text-severity-fatal transition-colors focus-ring"
                                  title="Remove"
                                >
                                  {def?.name ?? component.defId}
                                  <span className="ml-1.5 text-space-600 group-hover:text-severity-fatal">
                                    ×
                                  </span>
                                </button>
                              </li>
                            );
                          })}
                        </ul>
                      )}
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        {/* Engineering readout */}
        <aside className="space-y-4">
          <Card className="space-y-3">
            <h2 className="font-display text-sm font-semibold text-space-200">
              Engineering metrics
            </h2>
            <dl className="space-y-2">
              <BigMetric label="Launch mass" value={formatMass(analysis.totalWetMass_kg)} />
              <BigMetric
                label="Total Δv"
                value={`${analysis.totalDeltaV_ms.toFixed(0)} m/s`}
                hint="Ideal, from Tsiolkovsky. Gravity and drag will take some of it."
              />
              <BigMetric
                label="Liftoff TWR"
                value={analysis.liftoffTWR.toFixed(2)}
                tone={
                  analysis.liftoffTWR < 1
                    ? 'bad'
                    : analysis.liftoffTWR < 1.2
                      ? 'warn'
                      : 'good'
                }
                hint={
                  analysis.liftoffTWR < 1
                    ? 'Below 1: this will not leave the pad.'
                    : 'Real launchers aim for about 1.2 to 1.5.'
                }
              />
              <BigMetric
                label="Stability (wet)"
                value={`${analysis.stabilityWet.stabilityMargin_cal.toFixed(2)} cal`}
                tone={analysis.stabilityWet.stabilityMargin_cal < 1 ? 'warn' : 'good'}
                hint="Calibers of static margin. Around 1–2 is the usual target."
              />
              <BigMetric
                label="Propellant fraction"
                value={`${(analysis.propellantMassFraction * 100).toFixed(0)}%`}
              />
              <BigMetric label="Length" value={`${analysis.totalLength_m.toFixed(1)} m`} />
            </dl>
          </Card>

          <Card className="space-y-2">
            <h2 className="font-display text-sm font-semibold text-space-200">
              Pre-flight validation
            </h2>
            {validation.valid && validation.warnings.length === 0 ? (
              <p className="text-xs text-accent-emerald">
                No problems found. This design is ready to fly.
              </p>
            ) : (
              <ul className="space-y-2">
                {validation.errors.map((issue, i) => (
                  <li key={`e${i}`} className="flex gap-2 text-2xs">
                    <span className="text-severity-fatal shrink-0">●</span>
                    <span className="text-space-300 leading-relaxed">{issue.message}</span>
                  </li>
                ))}
                {validation.warnings.map((issue, i) => (
                  <li key={`w${i}`} className="flex gap-2 text-2xs">
                    <span className="text-severity-warning shrink-0">●</span>
                    <span className="text-space-400 leading-relaxed">{issue.message}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <p className="text-2xs text-space-600 leading-relaxed">
            Not sure what to change?{' '}
            <Link to="/assistant" className="text-accent-cyan hover:underline">
              Ask the assistant
            </Link>{' '}
            or read the{' '}
            <Link to="/learn" className="text-accent-cyan hover:underline">
              propulsion lessons
            </Link>
            .
          </p>
        </aside>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-space-600">{label}</dt>
      <dd className="font-mono text-space-200">{value}</dd>
    </div>
  );
}

function BigMetric({
  label,
  value,
  hint,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: 'neutral' | 'good' | 'warn' | 'bad';
}) {
  const toneClass = {
    neutral: 'text-space-100',
    good: 'text-accent-emerald',
    warn: 'text-severity-warning',
    bad: 'text-severity-fatal',
  }[tone];

  return (
    <div className="border-b border-space-800/60 pb-2 last:border-0">
      <div className="flex items-baseline justify-between gap-2">
        <dt className="text-2xs text-space-500">{label}</dt>
        <dd className={cn('font-mono text-sm', toneClass)}>{value}</dd>
      </div>
      {hint && <p className="text-2xs text-space-600 mt-0.5 leading-relaxed">{hint}</p>}
    </div>
  );
}
