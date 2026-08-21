import { Link } from 'react-router-dom';

import {
  Badge,
  Button,
  EmptyState,
  Gauge,
  Panel,
  Readout,
  SectionRule,
  StatusDot,
} from '@/components/ui';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass } from '@/lib/utils';

/**
 * The mission report.
 *
 * Nine scored categories, the failures the flight produced, and the changes
 * that would recover the most points — all computed on the server from the
 * undecimated telemetry, so the scores see the peaks the returned series may
 * not contain.
 *
 * The layout puts the working next to the verdict deliberately. A score of 56
 * on aerodynamics means nothing on its own; "drag loss is 5,699 m/s against a
 * target of no more than 400, and that cost 35 points" means something you can
 * act on. Every criterion here shows its measurement, its acceptable band, and
 * the points it cost.
 */

const TONE_FOR_SCORE = (score: number) =>
  score >= 80 ? 'nominal' : score >= 55 ? 'caution' : 'critical';

export default function Evaluation() {
  const design = useMissionStore((s) => s.design);
  const result = useMissionStore((s) => s.result);
  const meta = useMissionStore((s) => s.resultMeta);
  const mission = useMissionStore((s) => s.mission);

  const evaluation = (meta as { evaluation?: EvaluationPayload } | null)?.evaluation ?? null;

  if (!result || !evaluation) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState
          title="No flight to evaluate"
          description="Fly a mission and its report appears here — scored across nine categories, with the measurement behind every number."
          action={
            <Link to={design ? '/launch' : '/rocket-lab'}>
              <Button>{design ? 'Configure a launch' : 'Build a rocket'}</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const summary = result.summary;
  const overallTone = TONE_FOR_SCORE(evaluation.overall_score);

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6">
      <header className="mb-5 flex flex-wrap items-end justify-between gap-6 hairline-b pb-4">
        <div>
          <p className="t-label mb-1">Evaluate · Mission report</p>
          <h1 className="font-display text-3xl leading-none text-ink-50">{mission.name}</h1>
          <p className="mt-1.5 font-mono text-tiny text-ink-500">
            {design?.name ?? 'Unknown vehicle'} · {mission.launchSite.name} ·{' '}
            {result.outcome} · {summary.flight_time_s.toFixed(0)} s of flight
          </p>
        </div>

        <div className="flex items-end gap-6">
          <div className="text-right">
            <p className="t-label mb-1">Overall</p>
            <p
              className={cn(
                'font-mono text-5xl leading-none tabular-nums',
                overallTone === 'nominal'
                  ? 'text-signal-nominal-bright'
                  : overallTone === 'caution'
                    ? 'text-signal-caution-bright'
                    : 'text-signal-oxide-bright',
              )}
            >
              {evaluation.overall_score}
              <span className="ml-1 text-lg text-ink-600">/100</span>
            </p>
          </div>
          <Badge variant={result.success ? 'nominal' : 'oxide'}>
            {result.success ? 'Mission accomplished' : 'Mission failed'}
          </Badge>
        </div>
      </header>

      {/* ── Flight profile at a glance ─────────────────────────── */}
      <SectionRule label="Flight profile" className="mt-6" />
      <div className="mb-8 grid grid-cols-2 gap-x-8 gap-y-4 sm:grid-cols-4 lg:grid-cols-7">
        <Readout
          size="lg"
          label="Max altitude"
          value={(summary.max_altitude_m / 1000).toFixed(1)}
          unit="km"
        />
        <Readout size="lg" label="Max speed" value={summary.max_speed_ms.toFixed(0)} unit="m/s" />
        <Readout
          size="lg"
          label="Peak g"
          value={summary.max_acceleration_g.toFixed(1)}
          unit="g"
          tone={summary.max_acceleration_g > 6 ? 'caution' : 'neutral'}
        />
        <Readout
          size="lg"
          label="Max-Q"
          value={(summary.max_dynamic_pressure_Pa / 1000).toFixed(1)}
          unit="kPa"
        />
        <Readout size="lg" label="Max Mach" value={summary.max_mach.toFixed(2)} />
        <Readout
          size="lg"
          label="Downrange"
          value={(summary.max_downrange_m / 1000).toFixed(1)}
          unit="km"
        />
        <Readout
          size="lg"
          label="Propellant used"
          value={formatMass(summary.propellant_used_kg)}
        />
      </div>

      {/* ── Where the Δv went ──────────────────────────────────── */}
      <SectionRule label="Where the Δv went" />
      <Panel className="mb-8 space-y-3">
        <DeltaVBar
          ideal={summary.delta_v_ideal_ms}
          achieved={summary.delta_v_achieved_ms}
          gravity={summary.gravity_loss_ms}
          drag={summary.drag_loss_ms}
        />
        <p className="text-tiny leading-relaxed text-ink-500">
          The propellant contained {summary.delta_v_ideal_ms.toFixed(0)} m/s of ideal Δv.
          Gravity took {summary.gravity_loss_ms.toFixed(0)} and drag took{' '}
          {summary.drag_loss_ms.toFixed(0)}, leaving {summary.delta_v_achieved_ms.toFixed(0)} m/s
          of peak speed. That gap is the difference between the rocket equation and a real
          ascent.
        </p>
      </Panel>

      {/* ── Scores ─────────────────────────────────────────────── */}
      <SectionRule label="Scored categories" />
      <div className="mb-8 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {evaluation.categories.map((category) => (
          <CategoryCard key={category.id} category={category} />
        ))}
      </div>

      {/* ── Failures ───────────────────────────────────────────── */}
      {result.failures.length > 0 && (
        <>
          <SectionRule label="Failure analysis" />
          <div className="mb-8 space-y-3">
            {result.failures.map((failure) => (
              <Panel key={failure.id} tone="oxide" className="space-y-3">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <div className="mb-1 flex items-center gap-2">
                      <Badge variant={failure.severity as 'fatal' | 'critical' | 'warning'}>
                        {failure.severity}
                      </Badge>
                      <Badge variant="outline">{failure.subsystem}</Badge>
                      <span className="font-mono text-micro text-ink-500">
                        T+{failure.t.toFixed(1)} s
                      </span>
                    </div>
                    <h3 className="font-display text-xl leading-tight text-ink-50">
                      {failure.failure_mode}
                    </h3>
                  </div>

                  {/* The evidence: what was measured, against what limit. */}
                  <div className="flex items-baseline gap-4 font-mono text-sm tabular-nums">
                    <span className="text-signal-oxide-bright">
                      {formatMeasured(failure.measured_value)} {failure.unit}
                    </span>
                    <span className="text-ink-600">vs</span>
                    <span className="text-ink-300">
                      {formatMeasured(failure.threshold_value)} {failure.unit}
                    </span>
                  </div>
                </div>

                <p className="max-w-prose text-sm leading-relaxed text-ink-200">
                  {failure.educational_explanation}
                </p>

                {failure.contributing_factors.length > 0 && (
                  <div className="hairline-t pt-3">
                    <p className="t-label mb-1.5">Contributing factors</p>
                    <ul className="space-y-1">
                      {failure.contributing_factors.map((factor, i) => (
                        <li key={i} className="flex gap-2 text-tiny leading-relaxed text-ink-400">
                          <span className="text-ink-600">·</span>
                          {factor}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="hairline-t pt-3">
                  <p className="t-label mb-1.5">Recommended fix</p>
                  <p className="text-sm leading-relaxed text-signal-nominal-bright">
                    {failure.recommended_fix}
                  </p>
                </div>

                {failure.related_lessons.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 hairline-t pt-3">
                    <span className="t-label">Read more</span>
                    {failure.related_lessons.map((slug) => (
                      <Link
                        key={slug}
                        to={`/learn/${slug}`}
                        className="font-condensed text-micro uppercase tracking-instrument text-signal-flame hover:text-signal-flame-bright"
                      >
                        {slug.replace(/-/g, ' ')} →
                      </Link>
                    ))}
                  </div>
                )}
              </Panel>
            ))}
          </div>
        </>
      )}

      {/* ── What to change ─────────────────────────────────────── */}
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <SectionRule label="What cost the most" />
          <Panel flush className="divide-y divide-[color:var(--rule-faint)]">
            {evaluation.weaknesses.length === 0 ? (
              <p className="p-4 text-xs text-ink-400">
                Nothing lost significant points. This is a well-made design.
              </p>
            ) : (
              evaluation.weaknesses.map((weakness, i) => (
                <p key={i} className="px-4 py-2.5 text-xs leading-relaxed text-ink-300">
                  {weakness}
                </p>
              ))
            )}
          </Panel>

          {evaluation.strengths.length > 0 && (
            <>
              <SectionRule label="What worked" className="mt-6" />
              <Panel flush className="divide-y divide-[color:var(--rule-faint)]">
                {evaluation.strengths.map((strength, i) => (
                  <p key={i} className="px-4 py-2.5 text-xs leading-relaxed text-ink-300">
                    {strength}
                  </p>
                ))}
              </Panel>
            </>
          )}
        </div>

        <div>
          <SectionRule
            label="Change this next"
            aside={<span className="font-mono text-micro text-ink-600">most recovery first</span>}
          />
          <ol className="space-y-2">
            {evaluation.recommendations.map((recommendation, i) => (
              <li key={i}>
                <Panel className="flex gap-3">
                  <span className="shrink-0 font-mono text-sm text-signal-flame">
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <p className="text-sm leading-relaxed text-ink-200">{recommendation}</p>
                </Panel>
              </li>
            ))}
          </ol>

          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/builder">
              <Button>Change the design</Button>
            </Link>
            <Link to="/launch">
              <Button variant="outline">Fly it again</Button>
            </Link>
            <Link to="/compare">
              <Button variant="ghost">Compare two designs</Button>
            </Link>
          </div>

          <SectionRule label="What this report cannot see" className="mt-8" />
          <ul className="space-y-2">
            {evaluation.limitations.map((limitation, i) => (
              <li key={i} className="flex gap-2 text-tiny leading-relaxed text-ink-500">
                <span className="text-ink-700">·</span>
                {limitation}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

/** One scored category, with every criterion that produced it. */
function CategoryCard({ category }: { category: EvaluationCategory }) {
  if (category.not_applicable) {
    return (
      <Panel className="space-y-2 opacity-60">
        <div className="flex items-baseline justify-between">
          <h3 className="font-display text-lg leading-none text-ink-200">{category.label}</h3>
          <span className="font-mono text-sm text-ink-600">n/a</span>
        </div>
        <p className="text-tiny leading-relaxed text-ink-500">{category.summary}</p>
      </Panel>
    );
  }

  const tone = TONE_FOR_SCORE(category.score);

  return (
    <Panel
      tone={tone === 'nominal' ? 'nominal' : tone === 'caution' ? 'caution' : 'oxide'}
      className="space-y-3"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-lg leading-none text-ink-50">{category.label}</h3>
        <span
          className={cn(
            'font-mono text-2xl leading-none tabular-nums',
            tone === 'nominal'
              ? 'text-signal-nominal-bright'
              : tone === 'caution'
                ? 'text-signal-caution-bright'
                : 'text-signal-oxide-bright',
          )}
        >
          {category.score}
          <span className="ml-0.5 text-xs text-ink-600">/100</span>
        </span>
      </div>

      <Gauge value={category.score} min={0} max={100} goodMin={80} goodMax={100} tone={tone} />

      <p className="text-tiny leading-relaxed text-ink-400">{category.summary}</p>

      <ul className="space-y-2 hairline-t pt-3">
        {category.criteria.map((criterion) => (
          <li key={criterion.id} className="space-y-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <StatusDot tone={criterion.passed ? 'nominal' : 'caution'} />
                <span className="truncate text-tiny text-ink-300">{criterion.label}</span>
              </span>
              <span className="shrink-0 font-mono text-[0.65rem] tabular-nums text-ink-200">
                {formatMeasured(criterion.measured)}
                {criterion.unit ? ` ${criterion.unit}` : ''}
              </span>
            </div>
            {!criterion.passed && (
              <p className="pl-3 text-[0.65rem] leading-relaxed text-ink-500">
                Target {describeBand(criterion)}. Cost{' '}
                {(criterion.weight - criterion.earned).toFixed(0)} of {criterion.weight} points.
                {criterion.recommendation ? ` ${criterion.recommendation}` : ''}
              </p>
            )}
          </li>
        ))}
      </ul>
    </Panel>
  );
}

/**
 * Where the Δv went, as a stacked bar.
 *
 * The single most instructive picture in the report: the ideal figure from the
 * rocket equation, and then how much of it gravity and drag took before
 * anything useful happened.
 */
function DeltaVBar({
  ideal,
  achieved,
  gravity,
  drag,
}: {
  ideal: number;
  achieved: number;
  gravity: number;
  drag: number;
}) {
  const total = Math.max(ideal, achieved + gravity + drag, 1);
  const segments = [
    { label: 'Realised', value: achieved, colour: 'bg-signal-nominal' },
    { label: 'Gravity loss', value: gravity, colour: 'bg-signal-flame' },
    { label: 'Drag loss', value: drag, colour: 'bg-signal-oxide' },
  ];

  return (
    <div className="space-y-2">
      <div className="flex h-6 w-full overflow-hidden rounded-instrument bg-ink-850">
        {segments.map((segment) => (
          <div
            key={segment.label}
            className={cn(segment.colour, 'transition-[width] duration-settle')}
            style={{ width: `${(segment.value / total) * 100}%` }}
            title={`${segment.label}: ${segment.value.toFixed(0)} m/s`}
          />
        ))}
      </div>
      <div className="flex flex-wrap gap-x-6 gap-y-1">
        {segments.map((segment) => (
          <span key={segment.label} className="flex items-center gap-1.5">
            <span className={cn('h-2 w-2', segment.colour)} aria-hidden="true" />
            <span className="t-label">{segment.label}</span>
            <span className="font-mono text-tiny tabular-nums text-ink-200">
              {segment.value.toFixed(0)} m/s
            </span>
          </span>
        ))}
        <span className="ml-auto flex items-center gap-1.5">
          <span className="t-label">Ideal</span>
          <span className="font-mono text-tiny tabular-nums text-ink-300">
            {ideal.toFixed(0)} m/s
          </span>
        </span>
      </div>
    </div>
  );
}

/** Format a measured value without dropping the digits that matter. */
function formatMeasured(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e6) return value.toExponential(2);
  if (magnitude >= 1000) return value.toLocaleString('en', { maximumFractionDigits: 0 });
  if (magnitude >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function describeBand(criterion: EvaluationCriterion): string {
  if (criterion.good_min !== null && criterion.good_max !== null) {
    return `${criterion.good_min}–${criterion.good_max} ${criterion.unit}`.trim();
  }
  if (criterion.good_min !== null) return `at least ${criterion.good_min} ${criterion.unit}`.trim();
  if (criterion.good_max !== null) {
    return `no more than ${criterion.good_max} ${criterion.unit}`.trim();
  }
  return 'any value';
}

// ── Shapes returned by the API, mirrored here ─────────────────

export interface EvaluationCriterion {
  id: string;
  label: string;
  measured: number;
  unit: string;
  good_min: number | null;
  good_max: number | null;
  weight: number;
  earned: number;
  passed: boolean;
  note: string;
  recommendation: string | null;
}

export interface EvaluationCategory {
  id: string;
  label: string;
  score: number;
  summary: string;
  not_applicable: boolean;
  criteria: EvaluationCriterion[];
}

export interface EvaluationPayload {
  overall_score: number;
  categories: EvaluationCategory[];
  strengths: string[];
  weaknesses: string[];
  recommendations: string[];
  limitations: string[];
}
