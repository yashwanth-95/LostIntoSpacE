import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { BodyDisc } from '@/components/features/explore/BodyDisc';
import {
  Acquiring,
  Badge,
  Button,
  ErrorPanel,
  Panel,
  Readout,
  SectionRule,
} from '@/components/ui';
import { catalog, type CatalogObject, type CatalogProperty } from '@/services/api';

/**
 * One object, in full.
 *
 * The photograph leads where there is one, because at this size a real image of
 * Jupiter's cloud bands carries information the drawn disc cannot. Where there
 * is none — Bennu and Ryugu — the drawn body leads instead, and the page does
 * not pretend otherwise.
 *
 * Properties are grouped as the catalog groups them: physical, orbital,
 * atmospheric. Each carries its own unit and, where the comparison is more
 * useful than the absolute, a ratio against Earth. Every panel ends in the
 * source the numbers came from, because a measured value with no provenance is
 * just a number someone typed.
 */
export default function ObjectDetail() {
  const { objectId } = useParams<{ objectId: string }>();
  const [object, setObject] = useState<CatalogObject | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!objectId) return;
    let cancelled = false;
    setObject(null);
    setError(null);
    catalog
      .object(objectId)
      .then((data) => {
        if (!cancelled) setObject(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'This object could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [objectId]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel title="Object not found" message={error} />
        <Link to="/explore" className="mt-4 inline-block">
          <Button variant="outline">Back to the catalog</Button>
        </Link>
      </div>
    );
  }

  if (!object) {
    return (
      <div className="mx-auto max-w-4xl px-6 py-16">
        <Acquiring rows={8} />
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-[1400px] px-6 py-8">
      <Link
        to="/explore"
        className="mb-6 inline-block font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200"
      >
        ← The catalog
      </Link>

      {/* ── Head ──────────────────────────────────────────────── */}
      <header className="mb-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-center">
        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Badge>{object.classification}</Badge>
            {object.designation && (
              <span className="font-mono text-micro text-ink-500">{object.designation}</span>
            )}
          </div>

          <h1 className="font-display text-display-md leading-[0.95] text-ink-50">
            {object.name}
          </h1>
          <p className="mt-4 max-w-[40rem] font-editorial text-lg leading-relaxed text-ink-300">
            {object.tagline}
          </p>
        </div>

        <div className="flex justify-center lg:justify-end">
          <BodyDisc appearance={object.appearance} size={200} title={`${object.name}, drawn from its measured colour and albedo`} />
        </div>
      </header>

      {object.image && (
        <figure className="mb-10">
          <img
            src={object.image.url}
            alt={object.image.alt}
            loading="lazy"
            decoding="async"
            className="max-h-[30rem] w-full object-cover"
          />
          <figcaption className="mt-2 flex flex-wrap gap-x-3 font-mono text-[0.6rem] text-ink-600">
            <span className="text-ink-400">{object.image.title}</span>
            <span>{object.image.credit}</span>
            {object.image.instrument && <span>{object.image.instrument}</span>}
            {object.image.date && <span>{object.image.date}</span>}
          </figcaption>
        </figure>
      )}

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-10">
          <section>
            <SectionRule label="Overview" />
            <p className="max-w-[40rem] font-editorial text-[0.98rem] leading-[1.7] text-ink-200">
              {object.overview}
            </p>
          </section>

          <PropertyTable label="Physical" properties={object.physical} />
          <PropertyTable label="Orbital" properties={object.orbital} />
          <PropertyTable label="Atmosphere" properties={object.atmosphere} />

          {object.facts.length > 0 && (
            <section>
              <SectionRule label="Worth knowing" />
              <ul className="space-y-3">
                {object.facts.map((fact, index) => (
                  <li key={index} className="rail max-w-[40rem]">
                    <p className="text-sm leading-relaxed text-ink-200">{fact}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {object.gallery.length > 0 && (
            <section>
              <SectionRule label="Gallery" />
              <ul className="grid gap-4 sm:grid-cols-2">
                {object.gallery.map((image) => (
                  <li key={image.url}>
                    <figure>
                      <img
                        src={image.url}
                        alt={image.alt}
                        loading="lazy"
                        decoding="async"
                        className="aspect-[4/3] w-full object-cover"
                      />
                      <figcaption className="mt-1.5 font-mono text-[0.6rem] leading-relaxed text-ink-600">
                        <span className="text-ink-400">{image.title}</span> · {image.credit}
                      </figcaption>
                    </figure>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>

        {/* ── Rail ──────────────────────────────────────────── */}
        <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <Panel className="space-y-2">
            <h2 className="t-label">At a glance</h2>
            <dl className="space-y-1.5">
              <Readout
                inline
                label="Mean radius"
                value={object.appearance.radius_km.toLocaleString('en', {
                  maximumFractionDigits: 1,
                })}
                unit="km"
              />
              <Readout
                inline
                label="Geometric albedo"
                value={object.appearance.albedo.toFixed(3)}
                hint={undefined}
              />
              {object.appearance.axial_tilt_deg !== 0 && (
                <Readout
                  inline
                  label="Axial tilt"
                  value={object.appearance.axial_tilt_deg.toFixed(2)}
                  unit="°"
                />
              )}
              <Readout inline label="Surface" value={object.appearance.texture.replace(/_/g, ' ')} />
            </dl>
          </Panel>

          {object.concept_slugs.length > 0 && (
            <div>
              <SectionRule label="The science" />
              <ul className="space-y-1">
                {object.concept_slugs.map((slug) => (
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

          {object.mission_ids.length > 0 && (
            <div>
              <SectionRule label="Missions here" />
              <ul className="space-y-1">
                {object.mission_ids.map((id) => (
                  <li key={id}>
                    <Link
                      to={`/missions/${id}`}
                      className="block py-1 text-sm text-ink-300 transition-colors hover:text-ink-50"
                    >
                      {id.replace(/-/g, ' ')} →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {object.related_ids.length > 0 && (
            <div>
              <SectionRule label="Next" />
              <ul className="space-y-1">
                {object.related_ids.map((id) => (
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

          {object.sources.length > 0 && (
            <Panel tone="sunken" className="space-y-1.5">
              <h2 className="t-label">Where these numbers come from</h2>
              {object.sources.map((source, index) => (
                <p key={index} className="text-tiny leading-relaxed text-ink-500">
                  {source.source_url ? (
                    <a
                      href={source.source_url}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-ink-300 underline decoration-ink-700 underline-offset-2 hover:text-ink-100"
                    >
                      {source.source_name}
                    </a>
                  ) : (
                    source.source_name
                  )}
                  {source.attribution ? ` — ${source.attribution}` : ''}
                </p>
              ))}
            </Panel>
          )}
        </aside>
      </div>
    </article>
  );
}

/** One group of measured properties, with units and Earth ratios. */
function PropertyTable({ label, properties }: { label: string; properties: CatalogProperty[] }) {
  if (properties.length === 0) return null;

  return (
    <section>
      <SectionRule label={label} />
      <dl className="max-w-[44rem] divide-y divide-[color:var(--rule-faint)]">
        {properties.map((property, index) => (
          <div key={index} className="grid grid-cols-[minmax(0,1fr)_auto] gap-4 py-2.5">
            <div className="min-w-0">
              <dt className="text-sm text-ink-200">{property.label}</dt>
              {property.note && (
                <p className="mt-0.5 text-tiny leading-relaxed text-ink-500">{property.note}</p>
              )}
            </div>
            <dd className="text-right">
              <span className="font-mono text-sm tabular-nums text-ink-50">
                {property.display ?? format(property.value)}
                {property.unit && !property.display && (
                  <span className="ml-1 text-ink-500">{property.unit}</span>
                )}
              </span>
              {property.earth_ratio !== null && property.earth_ratio !== undefined && (
                <p className="mt-0.5 font-mono text-[0.6rem] text-ink-600">
                  {formatRatio(property.earth_ratio)} × Earth
                </p>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function format(value?: number | null): string {
  if (value === null || value === undefined) return '—';
  const magnitude = Math.abs(value);
  if (magnitude >= 1e6 || (magnitude > 0 && magnitude < 0.001)) return value.toExponential(3);
  if (magnitude >= 1000) return value.toLocaleString('en', { maximumFractionDigits: 1 });
  if (magnitude >= 10) return value.toFixed(2);
  return value.toFixed(3);
}

function formatRatio(ratio: number): string {
  if (ratio >= 1000) return ratio.toLocaleString('en', { maximumFractionDigits: 0 });
  if (ratio >= 1) return ratio.toFixed(2);
  return ratio.toFixed(4);
}
