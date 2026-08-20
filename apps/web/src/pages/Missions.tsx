import { useEffect, useMemo, useState } from 'react';
import { Badge, Card, EmptyState, ErrorPanel, Input, Spinner } from '@/components/ui';
import { search, type SearchResultItem } from '@/services/api';
import { useDebounce } from '@/hooks/useDebounce';

/**
 * The mission library.
 *
 * Backed by the search API over the bundled knowledge corpus rather than by the
 * `missions` table. That is deliberate: the table holds a *user's own* mission
 * configurations (their rocket, their target), while this page is the reference
 * library of real flights. They are different things that happened to share a
 * word.
 *
 * The practical benefit is that this works with no database and no network —
 * the corpus is bundled, and every record carries its source attribution.
 */
export default function Missions() {
  const [query, setQuery] = useState('');
  const debounced = useDebounce(query, 250);
  const [items, setItems] = useState<SearchResultItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<SearchResultItem | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    // An empty query still needs a corpus-wide listing, so a broad term stands
    // in for "everything" — the search engine has no match-all mode.
    search
      .query({ q: debounced.trim() || 'mission spacecraft launch', entity_type: ['MISSION'], limit: 40 })
      .then((response) => {
        if (!cancelled) setItems(response.results ?? []);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'Missions could not be loaded.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debounced]);

  const topics = useMemo(() => {
    const set = new Set<string>();
    for (const item of items) for (const topic of item.topics ?? []) set.add(topic);
    return [...set].slice(0, 12);
  }, [items]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8 space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">Missions</h1>
          <p className="text-sm text-space-400">
            Real flights, their objectives, outcomes and discoveries — with sources.
          </p>
        </div>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search missions…"
          aria-label="Search missions"
          className="w-full sm:w-72"
        />
      </header>

      {topics.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {topics.map((topic) => (
            <button
              key={topic}
              onClick={() => setQuery(topic)}
              className="px-2 py-0.5 rounded text-2xs border border-space-700 bg-space-800/40 text-space-400 hover:text-space-200 transition-colors focus-ring"
            >
              {topic}
            </button>
          ))}
        </div>
      )}

      {error && <ErrorPanel title="Could not load missions" message={error} />}

      {loading ? (
        <div className="flex justify-center py-16">
          <Spinner />
        </div>
      ) : items.length === 0 ? (
        <EmptyState title="No missions found" description="Try a different search term." />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {items.map((mission) => (
            <li key={mission.id}>
              <button
                onClick={() => setSelected(mission)}
                className="w-full h-full text-left glass-panel p-4 hover:border-accent-cyan/40 transition-colors focus-ring"
              >
                <h2 className="font-display text-sm font-semibold text-space-100 mb-1.5">
                  {mission.title}
                </h2>
                {mission.summary && (
                  <p className="text-2xs text-space-400 leading-relaxed line-clamp-3 mb-2">
                    {mission.summary}
                  </p>
                )}
                <div className="flex flex-wrap gap-1">
                  {(mission.topics ?? []).slice(0, 3).map((topic) => (
                    <Badge key={topic} className="text-2xs">
                      {topic}
                    </Badge>
                  ))}
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}

      {selected && <MissionDetail item={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}

function MissionDetail({ item, onClose }: { item: SearchResultItem; onClose: () => void }) {
  const sources = item.provenance?.sources ?? [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-space-950/80 backdrop-blur-sm p-4 sm:p-8"
      role="dialog"
      aria-modal="true"
      aria-label={item.title}
      onClick={onClose}
    >
      <Card
        className="w-full max-w-2xl my-8 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 className="font-display text-lg font-semibold text-space-100">{item.title}</h2>
          <button
            onClick={onClose}
            className="text-space-500 hover:text-space-200 text-lg leading-none focus-ring rounded"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {item.summary && (
          <p className="text-sm text-space-300 leading-relaxed whitespace-pre-line">
            {item.summary}
          </p>
        )}

        {(item.topics ?? []).length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {item.topics!.map((topic) => (
              <Badge key={topic}>{topic}</Badge>
            ))}
          </div>
        )}

        {sources.length > 0 && (
          <div className="border-t border-space-800 pt-3">
            <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1.5">Sources</h3>
            <ul className="space-y-1">
              {sources.map((source, i) => (
                <li key={i} className="text-2xs text-space-500">
                  {source.source_url ? (
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-accent-cyan hover:underline"
                    >
                      {source.source_name}
                    </a>
                  ) : (
                    source.source_name
                  )}
                  <span className="text-space-600"> · {source.source_type}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </Card>
    </div>
  );
}
