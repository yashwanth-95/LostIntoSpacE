import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Acquiring, Badge, ErrorPanel, Panel, SectionRule } from '@/components/ui';
import { catalog, type Experiment } from '@/services/api';
import { cn } from '@/lib/utils';

/**
 * The experiment library.
 *
 * An experiment here is not a code snippet. It states a question, fixes
 * everything except one variable, sweeps that variable across real values, and
 * says what it expects to happen — then explains why the expectation is usually
 * wrong. That structure is the point: it is the difference between a
 * demonstration and an experiment.
 */
export default function Experiments() {
  const [experiments, setExperiments] = useState<Experiment[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<string | null>(null);

  useEffect(() => {
    catalog
      .experiments()
      .then(setExperiments)
      .catch((cause: unknown) =>
        setError(cause instanceof Error ? cause.message : 'Experiments could not be loaded.'),
      );
  }, []);

  const categories = useMemo(() => {
    if (!experiments) return [];
    const map = new Map<string, Experiment[]>();
    for (const experiment of experiments) {
      if (level && experiment.level !== level) continue;
      const list = map.get(experiment.category) ?? [];
      list.push(experiment);
      map.set(experiment.category, list);
    }
    return [...map.entries()];
  }, [experiments, level]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel message={error} />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <header className="mb-6 hairline-b pb-5">
        <p className="t-label mb-1">Understand · Experiments</p>
        <h1 className="font-display text-display-sm leading-none text-ink-50">
          Change one thing
        </h1>
        <p className="mt-3 max-w-[40rem] text-sm leading-relaxed text-ink-400">
          Every experiment holds everything constant except one variable, sweeps it across
          real values, and compares what happened against what you expected. Reading that fin
          size affects stability is a fact; watching the static margin cross one caliber is an
          understanding.
        </p>
      </header>

      <div className="mb-6 flex flex-wrap gap-1">
        {[null, 'foundation', 'intermediate', 'advanced'].map((option) => (
          <button
            key={option ?? 'all'}
            onClick={() => setLevel(option)}
            className={cn(
              'rounded-instrument border px-2.5 py-1 font-condensed text-micro uppercase tracking-label',
              'transition-colors duration-quick focus-ring',
              level === option
                ? 'border-signal-flame/40 bg-signal-flame/10 text-signal-flame-bright'
                : 'border-ink-700 bg-ink-850 text-ink-500 hover:text-ink-200',
            )}
          >
            {option ?? 'All levels'}
          </button>
        ))}
      </div>

      {!experiments ? (
        <Acquiring rows={8} />
      ) : (
        <div className="space-y-10">
          {categories.map(([category, items]) => (
            <section key={category}>
              <SectionRule
                label={category}
                aside={<span className="font-mono text-micro text-ink-600">{items.length}</span>}
              />
              <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
                {items.map((experiment) => (
                  <Link key={experiment.id} to={`/experiments/${experiment.id}`}>
                    <Panel className="group h-full space-y-2.5 transition-colors hover:border-signal-flame/40">
                      <div className="flex items-start justify-between gap-2">
                        <h3 className="font-display text-lg leading-tight text-ink-50">
                          {experiment.title}
                        </h3>
                        <Badge
                          variant={
                            experiment.level === 'foundation'
                              ? 'nominal'
                              : experiment.level === 'intermediate'
                                ? 'cryo'
                                : 'xenon'
                          }
                        >
                          {experiment.level}
                        </Badge>
                      </div>

                      <p className="text-xs leading-relaxed text-ink-300">
                        {experiment.question}
                      </p>

                      <dl className="space-y-1 hairline-t pt-2.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <dt className="t-label">Variable</dt>
                          <dd className="truncate font-mono text-tiny text-ink-200">
                            {experiment.variable_label}
                          </dd>
                        </div>
                        <div className="flex items-baseline justify-between gap-2">
                          <dt className="t-label">Runs</dt>
                          <dd className="font-mono text-tiny text-ink-200">
                            {experiment.sweep.length || experiment.estimated_runs}
                          </dd>
                        </div>
                        <div className="flex items-baseline justify-between gap-2">
                          <dt className="t-label">Controls</dt>
                          <dd className="font-mono text-tiny text-ink-200">
                            {experiment.controls.length} held
                          </dd>
                        </div>
                      </dl>
                    </Panel>
                  </Link>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
