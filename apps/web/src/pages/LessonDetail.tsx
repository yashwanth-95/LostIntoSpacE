import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router-dom';
import { Badge, Button, Card, Spinner } from '@/components/ui';
import { search, type SearchResultItem } from '@/services/api';

/**
 * One learning concept.
 *
 * The list page passes the concept through router state, so navigating from
 * Learn renders immediately with no second request. A direct link or a reload
 * has no such state and re-fetches by searching for the id — the corpus has no
 * get-by-id endpoint, and adding one for a bundled corpus of this size would be
 * more machinery than the problem deserves.
 */
export default function LessonDetail() {
  const { identifier } = useParams();
  const location = useLocation();
  const passed = (location.state as { concept?: SearchResultItem } | null)?.concept ?? null;

  const [concept, setConcept] = useState<SearchResultItem | null>(passed);
  const [loading, setLoading] = useState(!passed);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (passed || !identifier) return;
    let cancelled = false;
    setLoading(true);

    const term = decodeURIComponent(identifier).replace(/^concept:/, '').replace(/-/g, ' ');
    search
      .query({ q: term, entity_type: ['CONCEPT'], limit: 5 })
      .then((response) => {
        if (cancelled) return;
        const match =
          response.results.find((r) => r.id === decodeURIComponent(identifier)) ??
          response.results[0] ??
          null;
        setConcept(match);
        if (!match) setError('That concept could not be found.');
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The concept could not be loaded.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [identifier, passed]);

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  if (error || !concept) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 text-center space-y-4">
        <h1 className="font-display text-lg text-space-100">Concept not found</h1>
        <p className="text-sm text-space-400">{error}</p>
        <Link to="/learn">
          <Button>Back to Learn</Button>
        </Link>
      </div>
    );
  }

  const sources = concept.provenance?.sources ?? [];

  return (
    <article className="mx-auto max-w-3xl px-6 py-8 space-y-5">
      <Link to="/learn" className="text-2xs text-accent-cyan hover:underline">
        ← Learn
      </Link>

      <header>
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-2">
          {concept.title}
        </h1>
        <div className="flex flex-wrap gap-1.5">
          {(concept.topics ?? []).map((topic) => (
            <Badge key={topic}>{topic}</Badge>
          ))}
        </div>
      </header>

      {concept.summary && (
        <Card>
          <p className="text-sm text-space-300 leading-relaxed whitespace-pre-line">
            {concept.summary}
          </p>
        </Card>
      )}

      <Card className="space-y-2">
        <h2 className="font-display text-sm font-semibold text-space-200">Put it into practice</h2>
        <p className="text-2xs text-space-400 leading-relaxed">
          Reading about a concept and changing a rocket because of it are different kinds of
          understanding. Open the Builder and see what this changes.
        </p>
        <div className="flex flex-wrap gap-2 pt-1">
          <Link to="/rocket-lab">
            <Button size="sm">Open Rocket Lab</Button>
          </Link>
          <Link to="/assistant">
            <Button size="sm" variant="secondary">
              Ask about this
            </Button>
          </Link>
        </div>
      </Card>

      {sources.length > 0 && (
        <Card>
          <h2 className="font-display text-sm font-semibold text-space-200 mb-1.5">Sources</h2>
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
        </Card>
      )}
    </article>
  );
}
