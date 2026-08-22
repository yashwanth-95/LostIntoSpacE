import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Acquiring, Badge, ErrorPanel, Input, Panel, SectionRule } from '@/components/ui';
import { useDebounce } from '@/hooks/useDebounce';
import { catalog, type ReferenceMission } from '@/services/api';
import { cn } from '@/lib/utils';

/**
 * The mission library.
 *
 * Real flights, from the catalog. Distinct from a *user's* missions, which are
 * their own rocket and their own target and live in the workspace — these
 * happened, and they are here to be compared against.
 *
 * Each carries the engineering numbers worth putting next to your own design,
 * and — where there was one — what went wrong. That last part is the reason the
 * library exists: Apollo 13 and Challenger are more instructive than any
 * mission that went to plan.
 */

const STATUS_TONE: Record<string, 'nominal' | 'cryo' | 'caution' | 'default'> = {
  active: 'nominal',
  extended: 'nominal',
  complete: 'cryo',
  ended: 'cryo',
  planned: 'caution',
  lost: 'caution',
};

export default function Missions() {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);
  const [missions, setMissions] = useState<ReferenceMission[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    catalog
      .missions(debounced.trim() ? { q: debounced.trim() } : {})
      .then((data) => {
        if (!cancelled) setMissions(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'Missions could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const withFailures = useMemo(
    () => missions?.filter((mission) => mission.failures.length > 0) ?? [],
    [missions],
  );

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-6 hairline-b pb-5">
        <div>
          <p className="t-label mb-1">Explore</p>
          <h1 className="font-display text-display-sm leading-none text-ink-50">Missions</h1>
          <p className="mt-3 max-w-[42rem] text-sm leading-relaxed text-ink-400">
            Flights that actually happened, with the vehicle numbers worth putting beside your
            own design.
            {withFailures.length > 0 && (
              <> {withFailures.length} of them went wrong, which is where the lessons are.</>
            )}
          </p>
        </div>

        <div className="w-full max-w-xs">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search missions…"
            aria-label="Search missions"
          />
          {missions && (
            <p className="mt-1.5 font-mono text-micro text-ink-600">
              {missions.length} mission{missions.length === 1 ? '' : 's'}
            </p>
          )}
        </div>
      </header>

      {error && <ErrorPanel message={error} className="mb-6" />}
      {!missions && !error && <Acquiring rows={8} />}

      {missions && (
        <>
          <SectionRule label="The library" />
          <ul className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {missions.map((mission) => (
              <li key={mission.id}>
                <Link to={`/missions/${mission.id}`}>
                  <Panel className="group flex h-full flex-col gap-3 overflow-hidden transition-colors hover:border-signal-flame/40">
                    {mission.image && (
                      <img
                        src={mission.image.url}
                        alt={mission.image.alt}
                        loading="lazy"
                        decoding="async"
                        className="-mx-4 -mt-4 mb-0 aspect-[16/9] w-[calc(100%+2rem)] max-w-none object-cover"
                      />
                    )}

                    <div className="flex items-start justify-between gap-3">
                      <h3 className="font-display text-xl leading-tight text-ink-50">
                        {mission.name}
                      </h3>
                      <Badge variant={STATUS_TONE[mission.status] ?? 'default'}>
                        {mission.status}
                      </Badge>
                    </div>

                    <p className="text-xs leading-relaxed text-ink-300">{mission.objective}</p>

                    <dl className="mt-auto space-y-1 hairline-t pt-2.5 font-mono text-[0.6rem] text-ink-600">
                      <div className="flex justify-between gap-2">
                        <dt>Operator</dt>
                        <dd className="text-ink-300">{mission.operator}</dd>
                      </div>
                      {mission.launch_date && (
                        <div className="flex justify-between gap-2">
                          <dt>Launched</dt>
                          <dd className="text-ink-300">{mission.launch_date}</dd>
                        </div>
                      )}
                      {mission.launch_vehicle && (
                        <div className="flex justify-between gap-2">
                          <dt>Vehicle</dt>
                          <dd className="truncate text-ink-300">{mission.launch_vehicle}</dd>
                        </div>
                      )}
                    </dl>

                    {mission.failures.length > 0 && (
                      <p
                        className={cn(
                          'font-condensed text-micro uppercase tracking-label',
                          'text-signal-oxide-bright',
                        )}
                      >
                        {mission.failures.length} recorded failure
                        {mission.failures.length === 1 ? '' : 's'}
                      </p>
                    )}
                  </Panel>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
