import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { Badge, Card, EmptyState, ErrorPanel, Input, Spinner } from '@/components/ui';
import { search, type SearchResponse } from '@/services/api';
import { useDebounce } from '@/hooks/useDebounce';
import { cn } from '@/lib/utils';

/**
 * Platform-wide search.
 *
 * One query, ranked across every kind of entity the corpus holds — missions,
 * concepts, objects — rather than a separate search box per section. Results
 * carry their source, and the engine's own explanation of how it read the query
 * is shown, because a ranked list with no visible reasoning is hard to trust.
 *
 * The query lives in the URL so a search can be linked and reloaded.
 */
export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const initial = params.get('q') ?? '';

  const [query, setQuery] = useState(initial);
  const debounced = useDebounce(query, 300);
  const [entityType, setEntityType] = useState<string | null>(params.get('type'));

  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const next = new URLSearchParams();
    if (debounced.trim()) next.set('q', debounced.trim());
    if (entityType) next.set('type', entityType);
    setParams(next, { replace: true });
  }, [debounced, entityType, setParams]);

  useEffect(() => {
    const text = debounced.trim();
    if (!text) {
      setResponse(null);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    search
      .query({ q: text, entity_type: entityType ? [entityType] : undefined, limit: 30 })
      .then((result) => {
        if (!cancelled) setResponse(result);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The search failed.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [debounced, entityType]);

  const types = ['MISSION', 'CONCEPT'];

  return (
    <div className="mx-auto max-w-4xl px-6 py-8 space-y-5">
      <header>
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">Search</h1>
        <p className="text-sm text-space-400">
          Missions, engineering concepts and catalogued knowledge, ranked together.
        </p>
      </header>

      <Input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Ask about anything — “why do rockets have stages”, “Apollo 13”, “max-Q”…"
        aria-label="Search query"
        autoFocus
        className="w-full"
      />

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by type">
        <button
          onClick={() => setEntityType(null)}
          aria-pressed={entityType === null}
          className={cn(
            'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
            entityType === null
              ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
              : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
          )}
        >
          Everything
        </button>
        {types.map((type) => (
          <button
            key={type}
            onClick={() => setEntityType(entityType === type ? null : type)}
            aria-pressed={entityType === type}
            className={cn(
              'px-2.5 py-1 rounded-md text-2xs border transition-colors focus-ring',
              entityType === type
                ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                : 'bg-space-800/50 text-space-400 border-space-700 hover:text-space-200',
            )}
          >
            {type.toLowerCase()}s
          </button>
        ))}
      </div>

      {error && <ErrorPanel title="Search failed" message={error} />}

      {loading && (
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      )}

      {!loading && !query.trim() && (
        <EmptyState
          title="Start typing"
          description="Search runs across missions, concepts and the knowledge corpus at once."
        />
      )}

      {!loading && response && (
        <>
          <div className="flex flex-wrap items-center gap-3 text-2xs text-space-500">
            <span>
              {response.results.length} result{response.results.length === 1 ? '' : 's'}
            </span>
            {typeof response.took_ms === 'number' && <span>· {response.took_ms.toFixed(0)} ms</span>}
            {response.explanation && (
              <span className="text-space-600">· {response.explanation}</span>
            )}
          </div>

          {response.results.length === 0 ? (
            <EmptyState
              title="Nothing matched"
              description="The corpus has nothing relevant. Try different words rather than more of them."
            />
          ) : (
            <ul className="space-y-3">
              {response.results.map((item) => (
                <li key={item.id}>
                  <Card className="space-y-2">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="font-display text-sm font-semibold text-space-100">
                        {item.title}
                      </h2>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <Badge className="text-2xs">{item.entity_type}</Badge>
                        <span
                          className="text-2xs font-mono text-space-600"
                          title="Relevance score"
                        >
                          {item.score.toFixed(2)}
                        </span>
                      </div>
                    </div>

                    {item.summary && (
                      <p className="text-2xs text-space-400 leading-relaxed line-clamp-3">
                        {item.summary}
                      </p>
                    )}

                    {item.provenance?.sources?.length ? (
                      <p className="text-2xs text-space-600">
                        Source: {item.provenance.sources.map((s) => s.source_name).join(', ')}
                      </p>
                    ) : null}
                  </Card>
                </li>
              ))}
            </ul>
          )}

          {response.suggestions && response.suggestions.length > 0 && (
            <div className="border-t border-space-800 pt-4">
              <p className="text-2xs text-space-500 mb-2">Try also</p>
              <div className="flex flex-wrap gap-1.5">
                {response.suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => setQuery(suggestion)}
                    className="px-2 py-0.5 rounded text-2xs border border-space-700 bg-space-800/40 text-space-400 hover:text-space-200 transition-colors focus-ring"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
