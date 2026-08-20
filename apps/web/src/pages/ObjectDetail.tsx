import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Badge, Button, Card, Spinner } from '@/components/ui';
import { DatabaseUnavailable } from '@/components/layout/DatabaseUnavailable';
import { spaceObjects } from '@/services/api';
import type { SpaceObject } from '@/types';

/**
 * One catalogued object.
 *
 * Properties are rendered from whatever the record actually carries rather than
 * from a fixed field list: a comet has no atmosphere and a star has no orbital
 * period, and printing "—" for every inapplicable field is noise. The brief is
 * explicit that irrelevant fields should not be forced onto every object.
 */
export default function ObjectDetail() {
  const { objectId } = useParams();
  const [object, setObject] = useState<SpaceObject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dbDown, setDbDown] = useState(false);

  useEffect(() => {
    if (!objectId) return;
    let cancelled = false;
    setLoading(true);

    spaceObjects
      .get(objectId)
      .then((data) => {
        if (!cancelled) setObject(data);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const message = cause instanceof Error ? cause.message : 'Could not load the object.';
        setDbDown(/database|unavailable|reach|connect/i.test(message));
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [objectId]);

  if (loading) {
    return (
      <div className="flex justify-center py-24">
        <Spinner />
      </div>
    );
  }

  if (dbDown) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-12">
        <DatabaseUnavailable what="This object" />
      </div>
    );
  }

  if (error || !object) {
    return (
      <div className="mx-auto max-w-2xl px-6 py-16 text-center space-y-4">
        <h1 className="font-display text-lg text-space-100">Object not found</h1>
        <p className="text-sm text-space-400">{error ?? 'No object with that identifier.'}</p>
        <Link to="/explore">
          <Button>Back to Explore</Button>
        </Link>
      </div>
    );
  }

  const properties = {
    ...(object.physical_properties ?? {}),
    ...(object.orbital_elements ?? {}),
  } as Record<string, unknown>;

  const rows = Object.entries(properties).filter(
    ([, value]) => value !== null && value !== undefined && value !== '',
  );

  return (
    <div className="mx-auto max-w-4xl px-6 py-8 space-y-5">
      <Link to="/explore" className="text-2xs text-accent-cyan hover:underline">
        ← Explore
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">
            {object.name}
          </h1>
          <Badge>{object.object_type}</Badge>
        </div>
      </header>

      {object.image_url && (
        <img
          src={object.image_url}
          alt={object.name}
          className="w-full max-h-80 object-cover rounded-lg border border-space-800"
        />
      )}

      {object.description && (
        <Card>
          <p className="text-sm text-space-300 leading-relaxed whitespace-pre-line">
            {object.description}
          </p>
        </Card>
      )}

      {rows.length > 0 && (
        <Card>
          <h2 className="font-display text-sm font-semibold text-space-200 mb-3">Properties</h2>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
            {rows.map(([key, value]) => (
              <div
                key={key}
                className="flex justify-between gap-3 border-b border-space-800/60 pb-1"
              >
                <dt className="text-2xs text-space-500">{key.replace(/_/g, ' ')}</dt>
                <dd className="text-2xs font-mono text-space-200 text-right">
                  {typeof value === 'number' ? value.toLocaleString() : String(value)}
                </dd>
              </div>
            ))}
          </dl>
        </Card>
      )}

      <Card>
        <h2 className="font-display text-sm font-semibold text-space-200 mb-1.5">Provenance</h2>
        <p className="text-2xs text-space-400 leading-relaxed">
          {object.source_name
            ? `Sourced from ${object.source_name}.`
            : 'No source recorded for this record.'}{' '}
          Figures are as published by the source at ingestion time and are not re-derived here.
        </p>
      </Card>
    </div>
  );
}
