import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, EmptyState, ErrorPanel, Input, Spinner } from '@/components/ui';
import { search, type SearchResultItem } from '@/services/api';
import { useDebounce } from '@/hooks/useDebounce';
import { cn } from '@/lib/utils';

/**
 * Learning paths and concepts.
 *
 * Content comes from the bundled knowledge corpus through the search API, so
 * the lessons are available with no database and no network. Progress tracking
 * is the part that needs an account and a database, and it is marked as such
 * rather than faked.
 *
 * The paths below are curated orderings over that corpus: a list of search
 * terms that walks someone from "what is thrust" to "why did my second stage
 * not circularise". Ordering is editorial; the content is not duplicated.
 */

interface Path {
  id: string;
  title: string;
  description: string;
  level: 'beginner' | 'intermediate' | 'advanced';
  query: string;
}

const PATHS: readonly Path[] = [
  {
    id: 'propulsion',
    title: 'Propulsion',
    description: 'How engines make thrust, what specific impulse buys you, and why staging exists.',
    level: 'beginner',
    query: 'thrust specific impulse propulsion engine staging',
  },
  {
    id: 'orbits',
    title: 'Orbital mechanics',
    description: 'Why orbit is a sideways problem, delta-v budgets, and transfer manoeuvres.',
    level: 'intermediate',
    query: 'orbit orbital mechanics delta-v transfer inclination',
  },
  {
    id: 'aero',
    title: 'Atmosphere and aerodynamics',
    description: 'Drag, dynamic pressure, max-Q, and why vehicles throttle down on the way up.',
    level: 'intermediate',
    query: 'atmosphere drag dynamic pressure max-q aerodynamics',
  },
  {
    id: 'missions',
    title: 'Mission design',
    description: 'Turning an objective into a launch window, a trajectory and a vehicle.',
    level: 'advanced',
    query: 'mission design trajectory launch window payload',
  },
] as const;

export default function Learn() {
  const [activePath, setActivePath] = useState<Path>(PATHS[0]);
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);

  const [items, setItems] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const effectiveQuery = useMemo(
    () => (debounced.trim() ? debounced.trim() : activePath.query),
    [debounced, activePath],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    search
      .query({ q: effectiveQuery, entity_type: ['CONCEPT'], limit: 30 })
      .then((response) => {
        if (!cancelled) setItems(response.results ?? []);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'Lessons could not be loaded.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [effectiveQuery]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 space-y-6">
      <header>
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">Learn</h1>
        <p className="text-sm text-space-400 max-w-2xl">
          The engineering you need to build something that flies. Everything here connects to the
          Rocket Lab — read about specific impulse, then go and change an engine.
        </p>
      </header>

      <section aria-labelledby="paths-heading" className="space-y-3">
        <h2 id="paths-heading" className="font-display text-sm font-semibold text-space-200">
          Learning paths
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {PATHS.map((path) => (
            <button
              key={path.id}
              onClick={() => {
                setActivePath(path);
                setQuery('');
              }}
              className={cn(
                'text-left p-4 rounded-lg border transition-colors focus-ring',
                activePath.id === path.id && !debounced.trim()
                  ? 'bg-accent-cyan/10 border-accent-cyan/40'
                  : 'glass-panel hover:border-space-600',
              )}
              aria-pressed={activePath.id === path.id}
            >
              <div className="flex items-start justify-between gap-2 mb-1.5">
                <h3 className="font-display text-sm font-semibold text-space-100">
                  {path.title}
                </h3>
                <Badge
                  variant={path.level === 'beginner' ? 'nominal' : 'default'}
                  className="shrink-0 text-2xs"
                >
                  {path.level}
                </Badge>
              </div>
              <p className="text-2xs text-space-400 leading-relaxed">{path.description}</p>
            </button>
          ))}
        </div>
      </section>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-space-800 pt-5">
        <h2 className="font-display text-sm font-semibold text-space-200">
          {debounced.trim() ? `Results for “${debounced.trim()}”` : `${activePath.title} concepts`}
        </h2>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search all concepts…"
          aria-label="Search concepts"
          className="w-full sm:w-72"
        />
      </div>

      {error && <ErrorPanel title="Could not load lessons" message={error} />}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <EmptyState title="Nothing found" description="Try a different search term." />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((concept) => (
            <li key={concept.id}>
              <Link
                to={`/learn/${encodeURIComponent(concept.id)}`}
                state={{ concept }}
                className="block h-full glass-panel p-4 hover:border-accent-cyan/40 transition-colors focus-ring"
              >
                <h3 className="font-display text-sm font-semibold text-space-100 mb-1.5">
                  {concept.title}
                </h3>
                {concept.summary && (
                  <p className="text-2xs text-space-400 leading-relaxed line-clamp-3">
                    {concept.summary}
                  </p>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}

      <p className="text-2xs text-space-600 border-t border-space-800 pt-4">
        Progress tracking and quiz attempts are saved to your account. See{' '}
        <Link to="/workspace" className="text-accent-cyan hover:underline">
          your workspace
        </Link>
        .
      </p>
    </div>
  );
}
