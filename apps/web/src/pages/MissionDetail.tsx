import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  Acquiring,
  Badge,
  Button,
  ErrorPanel,
  Panel,
  Readout,
  SectionRule,
} from '@/components/ui';
import { catalog, type ReferenceMission } from '@/services/api';

/**
 * One real mission.
 *
 * A timeline down the left, the engineering numbers on the right, and the
 * failures given equal billing with the discoveries — because a mission library
 * that only records successes teaches the wrong thing about spaceflight.
 */
export default function MissionDetail() {
  const { missionId } = useParams<{ missionId: string }>();
  const [mission, setMission] = useState<ReferenceMission | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!missionId) return;
    let cancelled = false;
    setMission(null);
    catalog
      .mission(missionId)
      .then((data) => {
        if (!cancelled) setMission(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'This mission could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [missionId]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel title="Mission not found" message={error} />
        <Link to="/missions" className="mt-4 inline-block">
          <Button variant="outline">Back to the mission library</Button>
        </Link>
      </div>
    );
  }

  if (!mission) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Acquiring rows={6} />
      </div>
    );
  }

  const statusTone =
    mission.status === 'active' ? 'nominal' : mission.status === 'failed' ? 'oxide' : 'outline';

  return (
    <article className="mx-auto max-w-[1400px] px-6 py-8">
      <Link
        to="/missions"
        className="mb-6 inline-block font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200"
      >
        ← Mission library
      </Link>

      {/* ── Head ────────────────────────────────────────────── */}
      <header className="mb-8 grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge variant={statusTone}>{mission.status}</Badge>
            <Badge variant="outline">{mission.mission_type}</Badge>
            <span className="font-mono text-micro text-ink-600">{mission.operator}</span>
          </div>

          <h1 className="font-display text-display-md leading-[0.98] text-ink-50">
            {mission.name}
          </h1>

          <p className="mt-4 max-w-[38rem] font-editorial text-lg leading-relaxed text-ink-300">
            {mission.objective}
          </p>

          <dl className="mt-6 grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
            <Readout label="Launched" value={mission.launch_date ?? '—'} />
            {mission.end_date && <Readout label="Ended" value={mission.end_date} />}
            <Readout label="Vehicle" value={mission.launch_vehicle ?? '—'} />
            <Readout label="Site" value={mission.launch_site_id?.replace(/-/g, ' ') ?? '—'} />
          </dl>
        </div>

        {mission.image && (
          <figure>
            <img
              src={mission.image.url}
              alt={mission.image.alt}
              loading="lazy"
              decoding="async"
              className="w-full object-cover"
            />
            <figcaption className="mt-1.5 font-mono text-[0.6rem] leading-relaxed text-ink-600">
              {mission.image.title} · {mission.image.credit}
            </figcaption>
          </figure>
        )}
      </header>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-8">
          <section>
            <SectionRule label="Overview" />
            <div className="max-w-[40rem] space-y-3">
              {mission.overview.split('\n\n').map((paragraph, i) => (
                <p key={i} className="font-editorial text-[0.98rem] leading-[1.7] text-ink-200">
                  {paragraph}
                </p>
              ))}
            </div>
          </section>

          {mission.timeline.length > 0 && (
            <section>
              <SectionRule label="Timeline" />
              <ol className="relative space-y-0">
                {/* One vertical rule, with events hung off it. */}
                <span
                  className="absolute bottom-2 left-[5.5rem] top-2 w-px bg-[color:var(--rule)]"
                  aria-hidden="true"
                />
                {mission.timeline.map((event, index) => (
                  <li key={index} className="relative flex gap-4 py-3">
                    <time className="w-20 shrink-0 pt-0.5 text-right font-mono text-tiny tabular-nums text-ink-500">
                      {event.date}
                    </time>
                    <span
                      className={
                        'relative z-objects mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ' +
                        (event.significant ? 'bg-signal-flame' : 'bg-ink-600')
                      }
                      aria-hidden="true"
                    />
                    <div className="min-w-0 flex-1">
                      <h3
                        className={
                          event.significant
                            ? 'font-display text-lg leading-tight text-ink-50'
                            : 'text-sm text-ink-200'
                        }
                      >
                        {event.title}
                      </h3>
                      {event.detail && (
                        <p className="mt-0.5 text-xs leading-relaxed text-ink-400">
                          {event.detail}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {mission.discoveries.length > 0 && (
            <section>
              <SectionRule label="What it found" />
              <ul className="max-w-[40rem] space-y-2.5">
                {mission.discoveries.map((discovery, i) => (
                  <li key={i} className="flex gap-3 text-sm leading-relaxed text-ink-200">
                    <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-signal-nominal" />
                    {discovery}
                  </li>
                ))}
              </ul>
            </section>
          )}

          {mission.failures.length > 0 && (
            <section>
              <SectionRule label="What went wrong" />
              <Panel tone="oxide">
                <ul className="space-y-2.5">
                  {mission.failures.map((failure, i) => (
                    <li key={i} className="flex gap-3 text-sm leading-relaxed text-ink-200">
                      <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-signal-oxide" />
                      {failure}
                    </li>
                  ))}
                </ul>
              </Panel>
            </section>
          )}
        </div>

        <aside className="space-y-5 lg:sticky lg:top-20 lg:self-start">
          {mission.vehicle_facts.length > 0 && (
            <Panel className="space-y-2.5">
              <h2 className="t-label">The vehicle</h2>
              <dl className="space-y-2">
                {mission.vehicle_facts.map((fact) => (
                  <Readout
                    key={fact.label}
                    inline
                    label={fact.label}
                    value={
                      fact.display ??
                      (fact.value !== null && fact.value !== undefined
                        ? formatValue(fact.value, fact.precision)
                        : '—')
                    }
                    unit={fact.unit ?? undefined}
                  />
                ))}
              </dl>
              <p className="text-tiny leading-relaxed text-ink-600 hairline-t pt-2">
                Worth holding next to your own design in the builder.
              </p>
            </Panel>
          )}

          {mission.crew.length > 0 && (
            <Panel className="space-y-1.5">
              <h2 className="t-label">Crew</h2>
              {mission.crew.map((member) => (
                <p key={member} className="text-sm text-ink-200">
                  {member}
                </p>
              ))}
            </Panel>
          )}

          {mission.destination_ids.length > 0 && (
            <div>
              <SectionRule label="Where it went" />
              <ul className="space-y-1">
                {mission.destination_ids.map((id) => (
                  <li key={id}>
                    <Link
                      to={`/explore/${id}`}
                      className="block py-1 text-sm text-ink-300 transition-colors hover:text-ink-50"
                    >
                      {id.replace(/-/g, ' ')} →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {mission.concept_slugs.length > 0 && (
            <div>
              <SectionRule label="The science" />
              <ul className="space-y-1">
                {mission.concept_slugs.map((slug) => (
                  <li key={slug}>
                    <Link
                      to={`/learn/${slug}`}
                      className="block py-1 text-sm text-signal-flame transition-colors hover:text-signal-flame-bright"
                    >
                      {slug.replace(/-/g, ' ')} →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

        </aside>
      </div>
    </article>
  );
}

function formatValue(value: number, precision?: number | null): string {
  if (precision !== null && precision !== undefined) return value.toFixed(precision);
  if (Math.abs(value) >= 1e6) return value.toExponential(2);
  if (Math.abs(value) >= 1000) return value.toLocaleString('en', { maximumFractionDigits: 0 });
  if (Number.isInteger(value)) return String(value);
  return value.toFixed(2);
}
