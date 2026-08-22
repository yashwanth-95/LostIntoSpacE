import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Acquiring, Badge, ErrorPanel, Input, Panel, SectionRule } from '@/components/ui';
import { useDebounce } from '@/hooks/useDebounce';
import { catalog, type ScienceTopic } from '@/services/api';
import { cn } from '@/lib/utils';

/**
 * The science library.
 *
 * Twenty-six topics across five strands, backed by the catalog. The previous
 * version was four hardcoded search queries against a corpus, which meant the
 * "curriculum" was whatever full-text search happened to return that day and
 * nothing could state a prerequisite.
 *
 * Strands are presented in reading order, and within a strand topics are in the
 * order they were authored to be read — foundation before intermediate before
 * advanced, with prerequisites always earlier than the topics that need them.
 */
export default function Learn() {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);
  const [level, setLevel] = useState<string | null>(null);
  const [topics, setTopics] = useState<ScienceTopic[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    catalog
      .science({
        ...(debounced.trim() ? { q: debounced.trim() } : {}),
        ...(level ? { level } : {}),
      })
      .then((data) => {
        if (!cancelled) setTopics(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The library could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [debounced, level]);

  const strands = useMemo(() => {
    if (!topics) return [];
    const seen: string[] = [];
    for (const topic of topics) if (!seen.includes(topic.strand)) seen.push(topic.strand);
    return seen.map((strand) => ({
      strand,
      items: topics.filter((topic) => topic.strand === strand),
    }));
  }, [topics]);

  const interactiveCount = topics?.filter((t) => t.interactive).length ?? 0;

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-8">
      <header className="mb-6 flex flex-wrap items-end justify-between gap-6 hairline-b pb-5">
        <div>
          <p className="t-label mb-1">Understand</p>
          <h1 className="font-display text-display-sm leading-none text-ink-50">
            The science
          </h1>
          <p className="mt-3 max-w-[42rem] text-sm leading-relaxed text-ink-400">
            From what an orbit actually is to why a windy day at 11 km ends a launch.
            {interactiveCount > 0 && (
              <>
                {' '}
                {interactiveCount} of these carry a figure you can drive — the maths comes from
                the same physics package that flies your missions, so the lesson and the
                simulator cannot disagree.
              </>
            )}
          </p>
        </div>

        <div className="w-full max-w-xs">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the library…"
            aria-label="Search science topics"
          />
          <div className="mt-2 flex flex-wrap gap-1">
            {[null, 'foundation', 'intermediate', 'advanced'].map((option) => (
              <button
                key={option ?? 'all'}
                onClick={() => setLevel(option)}
                className={cn(
                  'rounded-instrument border px-2 py-0.5 font-condensed text-micro uppercase tracking-label',
                  'transition-colors duration-quick focus-ring',
                  level === option
                    ? 'border-signal-flame/40 bg-signal-flame/10 text-signal-flame-bright'
                    : 'border-ink-700 bg-ink-850 text-ink-500 hover:text-ink-200',
                )}
              >
                {option ?? 'All'}
              </button>
            ))}
          </div>
        </div>
      </header>

      {error && <ErrorPanel message={error} className="mb-6" />}
      {!topics && !error && <Acquiring rows={8} />}

      <div className="space-y-10">
        {strands.map(({ strand, items }) => (
          <section key={strand}>
            <SectionRule
              label={strand}
              aside={<span className="font-mono text-micro text-ink-600">{items.length}</span>}
            />
            <ol className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
              {items.map((topic) => (
                <li key={topic.slug}>
                  <Link to={`/learn/${topic.slug}`}>
                    <Panel className="group h-full space-y-2.5 transition-colors hover:border-signal-flame/40">
                      <div className="flex items-start justify-between gap-3">
                        <h3 className="font-display text-lg leading-tight text-ink-50">
                          {topic.title}
                        </h3>
                        <Badge
                          variant={
                            topic.level === 'foundation'
                              ? 'nominal'
                              : topic.level === 'intermediate'
                                ? 'cryo'
                                : 'xenon'
                          }
                        >
                          {topic.level}
                        </Badge>
                      </div>

                      <p className="text-xs leading-relaxed text-ink-300">{topic.summary}</p>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 hairline-t pt-2.5 font-mono text-[0.6rem] text-ink-600">
                        <span>{topic.estimated_minutes} min</span>
                        {topic.interactive && (
                          <span className="text-signal-flame">interactive figure</span>
                        )}
                        {topic.experiment_ids.length > 0 && (
                          <span>
                            {topic.experiment_ids.length} experiment
                            {topic.experiment_ids.length === 1 ? '' : 's'}
                          </span>
                        )}
                        {topic.prerequisites.length > 0 && (
                          <span>needs {topic.prerequisites.join(', ').replace(/-/g, ' ')}</span>
                        )}
                      </div>
                    </Panel>
                  </Link>
                </li>
              ))}
            </ol>
          </section>
        ))}
      </div>
    </div>
  );
}
