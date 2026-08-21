import { useMemo } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, EmptyState, Panel, SectionRule } from '@/components/ui';
import { useMissionStore } from '@/stores/missionStore';
import { cn } from '@/lib/utils';

/**
 * Two flights, side by side.
 *
 * The point of the whole build–fly–analyse loop is the iteration, and an
 * iteration you cannot measure is a guess. This puts the run you just flew next
 * to the one you kept, and lists every difference with its direction.
 *
 * Rows are ordered by how much they moved, not alphabetically: the first thing
 * you want to know is what your change actually did, and the second is what
 * else it did that you were not expecting.
 */

interface Row {
  label: string;
  a: number;
  b: number;
  unit: string;
  /** Which direction is an improvement. `none` means it is context-dependent. */
  better: 'higher' | 'lower' | 'none';
  precision?: number;
}

export default function Compare() {
  const result = useMissionStore((s) => s.result);
  const design = useMissionStore((s) => s.design);
  const baseline = useMissionStore((s) => s.baseline);
  const setBaseline = useMissionStore((s) => s.setBaseline);
  const clearBaseline = useMissionStore((s) => s.clearBaseline);

  const rows = useMemo<Row[]>(() => {
    if (!result || !baseline) return [];
    const a = baseline.summary;
    const b = result.summary;
    const rows: Row[] = [
      { label: 'Max altitude', a: a.max_altitude_m / 1000, b: b.max_altitude_m / 1000, unit: 'km', better: 'higher', precision: 2 },
      { label: 'Max speed', a: a.max_speed_ms, b: b.max_speed_ms, unit: 'm/s', better: 'higher', precision: 0 },
      { label: 'Peak acceleration', a: a.max_acceleration_g, b: b.max_acceleration_g, unit: 'g', better: 'lower', precision: 2 },
      { label: 'Max-Q', a: a.max_dynamic_pressure_Pa / 1000, b: b.max_dynamic_pressure_Pa / 1000, unit: 'kPa', better: 'lower', precision: 2 },
      { label: 'Max Mach', a: a.max_mach, b: b.max_mach, unit: '', better: 'none', precision: 2 },
      { label: 'Downrange', a: a.max_downrange_m / 1000, b: b.max_downrange_m / 1000, unit: 'km', better: 'none', precision: 2 },
      { label: 'Flight time', a: a.flight_time_s, b: b.flight_time_s, unit: 's', better: 'none', precision: 1 },
      { label: 'Ideal Δv', a: a.delta_v_ideal_ms, b: b.delta_v_ideal_ms, unit: 'm/s', better: 'higher', precision: 0 },
      { label: 'Realised Δv', a: a.delta_v_achieved_ms, b: b.delta_v_achieved_ms, unit: 'm/s', better: 'higher', precision: 0 },
      { label: 'Gravity loss', a: a.gravity_loss_ms, b: b.gravity_loss_ms, unit: 'm/s', better: 'lower', precision: 0 },
      { label: 'Drag loss', a: a.drag_loss_ms, b: b.drag_loss_ms, unit: 'm/s', better: 'lower', precision: 0 },
      { label: 'Propellant used', a: a.propellant_used_kg, b: b.propellant_used_kg, unit: 'kg', better: 'lower', precision: 0 },
      { label: 'Stages separated', a: a.stages_separated, b: b.stages_separated, unit: '', better: 'none', precision: 0 },
      { label: 'Max q·α', a: a.max_q_alpha_Padeg, b: b.max_q_alpha_Padeg, unit: 'Pa·deg', better: 'lower', precision: 0 },
      { label: 'Max angle of attack', a: a.max_angle_of_attack_deg, b: b.max_angle_of_attack_deg, unit: '°', better: 'lower', precision: 2 },
      { label: 'Lateral deviation', a: a.max_lateral_deviation_m, b: b.max_lateral_deviation_m, unit: 'm', better: 'lower', precision: 0 },
      { label: 'Peak wind aloft', a: a.max_wind_speed_ms, b: b.max_wind_speed_ms, unit: 'm/s', better: 'none', precision: 1 },
    ];
    return rows.sort((x, y) => Math.abs(relativeChange(y)) - Math.abs(relativeChange(x)));
  }, [result, baseline]);

  if (!result) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState
          title="Nothing to compare yet"
          description="Fly a mission, keep it as a baseline, change something, and fly again. Every difference is listed here with its direction."
          action={
            <Link to={design ? '/launch' : '/rocket-lab'}>
              <Button>{design ? 'Configure a launch' : 'Build a rocket'}</Button>
            </Link>
          }
        />
      </div>
    );
  }

  if (!baseline) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState
          title="Keep this flight as a baseline"
          description={`"${result.outcome}" · ${(result.summary.max_altitude_m / 1000).toFixed(1)} km apogee. Keep it, change one thing about the design, and fly again — then this page shows exactly what your change did.`}
          action={
            <Button onClick={() => setBaseline(result, design?.name ?? 'Baseline')}>
              Keep as baseline
            </Button>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-4 hairline-b pb-5">
        <div>
          <p className="t-label mb-1">Evaluate · Comparison</p>
          <h1 className="font-display text-display-sm leading-none text-ink-50">
            What changed
          </h1>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={clearBaseline}>
            Clear baseline
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setBaseline(result, design?.name ?? 'Baseline')}
          >
            Make current the baseline
          </Button>
        </div>
      </header>

      {/* Column heads */}
      <div className="mb-2 grid grid-cols-[minmax(0,1fr)_repeat(3,minmax(0,7rem))] gap-3 px-3">
        <span className="t-label">Measure</span>
        <span className="t-label text-right">{baseline.label}</span>
        <span className="t-label text-right">{design?.name ?? 'Current'}</span>
        <span className="t-label text-right">Change</span>
      </div>

      <Panel flush className="divide-y divide-[color:var(--rule-faint)]">
        {rows.map((row) => {
          const delta = row.b - row.a;
          const relative = relativeChange(row);
          const improved =
            row.better === 'none'
              ? null
              : row.better === 'higher'
                ? delta > 0
                : delta < 0;
          const material = Math.abs(relative) >= 0.005;

          return (
            <div
              key={row.label}
              className="grid grid-cols-[minmax(0,1fr)_repeat(3,minmax(0,7rem))] items-baseline gap-3 px-3 py-2"
            >
              <span className="truncate text-xs text-ink-200">{row.label}</span>
              <span className="text-right font-mono text-xs tabular-nums text-ink-400">
                {row.a.toFixed(row.precision ?? 2)}
                {row.unit && <span className="ml-1 text-ink-600">{row.unit}</span>}
              </span>
              <span className="text-right font-mono text-xs tabular-nums text-ink-100">
                {row.b.toFixed(row.precision ?? 2)}
                {row.unit && <span className="ml-1 text-ink-600">{row.unit}</span>}
              </span>
              <span
                className={cn(
                  'text-right font-mono text-xs tabular-nums',
                  !material
                    ? 'text-ink-600'
                    : improved === null
                      ? 'text-ink-300'
                      : improved
                        ? 'text-signal-nominal-bright'
                        : 'text-signal-oxide-bright',
                )}
              >
                {!material ? '—' : `${delta > 0 ? '+' : ''}${(relative * 100).toFixed(1)}%`}
              </span>
            </div>
          );
        })}
      </Panel>

      {/* Outcome and failures side by side */}
      <SectionRule label="Outcome" className="mt-8" />
      <div className="grid gap-4 sm:grid-cols-2">
        {[
          { label: baseline.label, run: baseline },
          { label: design?.name ?? 'Current', run: result },
        ].map(({ label, run }) => (
          <Panel
            key={label}
            tone={run.success ? 'nominal' : 'oxide'}
            className="space-y-2"
          >
            <div className="flex items-center justify-between gap-2">
              <h3 className="font-display text-lg leading-none text-ink-50">{label}</h3>
              <Badge variant={run.success ? 'nominal' : 'oxide'}>{run.outcome}</Badge>
            </div>
            <p className="font-mono text-tiny text-ink-500">{run.termination_reason}</p>
            {run.failures.length === 0 ? (
              <p className="text-xs text-ink-400">No failures recorded.</p>
            ) : (
              <ul className="space-y-1">
                {run.failures.map((failure) => (
                  <li key={failure.id} className="text-xs leading-relaxed text-ink-300">
                    <span className="font-mono text-ink-500">T+{failure.t.toFixed(0)}s</span>{' '}
                    {failure.failure_mode}
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        ))}
      </div>

      <p className="mt-6 max-w-[42rem] text-tiny leading-relaxed text-ink-500">
        A comparison is only meaningful if one thing changed. Both runs record the vehicle, the
        launch site and the exact conditions used, so if the weather moved between them the
        difference you are reading is partly the weather —{' '}
        <Link to="/learn/failure-analysis" className="text-signal-flame hover:underline">
          which is why controls matter
        </Link>
        .
      </p>

      <div className="mt-6 flex flex-wrap gap-2">
        <Link to="/builder">
          <Button>Change something else</Button>
        </Link>
        <Link to="/evaluation">
          <Button variant="outline">Full report on the current run</Button>
        </Link>
      </div>
    </div>
  );
}

/** Fractional change from baseline to current, guarded against a zero baseline. */
function relativeChange(row: Row): number {
  if (row.a === 0) return row.b === 0 ? 0 : 1;
  return (row.b - row.a) / Math.abs(row.a);
}
