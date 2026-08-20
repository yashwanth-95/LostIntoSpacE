import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Badge, Card, EmptyState, Input, Spinner } from '@/components/ui';
import { DatabaseUnavailable } from '@/components/layout/DatabaseUnavailable';
import { Starfield } from '@/components/features/explore/Starfield';
import { spaceObjects } from '@/services/api';
import { useDebounce } from '@/hooks/useDebounce';
import type { SpaceObject } from '@/types';
import { cn } from '@/lib/utils';

/**
 * Explore Space — visual browsing of catalogued objects.
 *
 * Backed by `/space-objects`, which reads the PostgreSQL catalogue that P4's
 * ingestion writes. When the database is not configured this shows the setup
 * panel rather than an empty grid, because "no results" and "not connected" are
 * different problems and only one of them is the user's fault.
 */
export default function Explore() {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);
  const [category, setCategory] = useState<string | null>(null);

  const [items, setItems] = useState<SpaceObject[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [dbDown, setDbDown] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    spaceObjects
      .categories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    spaceObjects
      .list({ q: debounced.trim() || undefined, category: category ?? undefined, per_page: 48 })
      .then(({ items: rows, total: count }) => {
        if (cancelled) return;
        setItems(rows);
        setTotal(count);
        setDbDown(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const message = cause instanceof Error ? cause.message : 'Objects could not be loaded.';
        // A 503 from readiness, or a driver error, both mean "no database".
        setDbDown(/database|unavailable|reach|connect/i.test(message));
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debounced, category]);

  return (
    <div>
      <div className="relative border-b border-space-800/60 overflow-hidden">
        <Starfield className="absolute inset-0" density={140} />
        <div className="relative mx-auto max-w-6xl px-6 py-12">
          <h1 className="font-display text-2xl font-semibold text-space-100 mb-2">
            Explore Space
          </h1>
          <p className="text-sm text-space-400 max-w-2xl mb-6">
            Planets, moons, asteroids, comets, spacecraft and stations — with the source of every
            figure attached.
          </p>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search objects…"
            aria-label="Search space objects"
            className="w-full max-w-md"
          />
        </div>
      </div>

      <div className="mx-auto max-w-6xl px-6 py-6 space-y-5">
        {categories.length > 0 && (
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by category">
            <FilterChip active={category === null} onClick={() => setCategory(null)}>
              All
            </FilterChip>
            {categories.map((name) => (
              <FilterChip
                key={name}
                active={category === name}
                onClick={() => setCategory(category === name ? null : name)}
              >
                {name}
              </FilterChip>
            ))}
          </div>
        )}

        {dbDown ? (
          <DatabaseUnavailable what="The space-object catalogue" />
        ) : loading ? (
          <div className="flex justify-center py-16">
            <Spinner />
          </div>
        ) : error ? (
          <Card className="border-severity-critical/30">
            <p className="text-xs text-severity-critical">{error}</p>
          </Card>
        ) : items.length === 0 ? (
          <EmptyState
            title="No objects found"
            description="Try a different search term, or clear the category filter."
          />
        ) : (
          <>
            <p className="text-2xs text-space-500">
              {total} object{total === 1 ? '' : 's'}
            </p>
            <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {items.map((object) => (
                <li key={object.id}>
                  <Link
                    to={`/explore/${object.id}`}
                    className="block h-full glass-panel overflow-hidden hover:border-accent-cyan/40 transition-colors focus-ring"
                  >
                    {object.image_url && (
                      <img
                        src={object.image_url}
                        alt=""
                        loading="lazy"
                        className="w-full h-32 object-cover"
                      />
                    )}
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-2 mb-1.5">
                        <h2 className="font-display text-sm font-semibold text-space-100">
                          {object.name}
                        </h2>
                        <Badge className="shrink-0 text-2xs">{object.object_type}</Badge>
                      </div>
                      {object.description && (
                        <p className="text-2xs text-space-400 leading-relaxed line-clamp-3">
                          {object.description}
                        </p>
                      )}
                      {object.source_name && (
                        <p className="mt-2 text-2xs text-space-600">
                          Source: {object.source_name}
                        </p>
                      )}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
        active
          ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
          : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
      )}
    >
      {children}
    </button>
  );
}
