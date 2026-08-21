import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { InteractiveFigure } from '@/components/features/science/InteractiveFigure';
import {
  Acquiring,
  Badge,
  Button,
  EmptyState,
  ErrorPanel,
  Panel,
  SectionRule,
} from '@/components/ui';
import { catalog, type ScienceTopic as Topic } from '@/services/api';

/**
 * One science topic.
 *
 * Editorial column for the reading, an interactive figure for the part that
 * cannot be read, and a rail carrying what this topic connects to — the objects
 * that illustrate it, the experiments that test it, the failures it explains.
 *
 * The measure is roughly 68 characters, because these passages are meant to be
 * read rather than skimmed, and a line that runs the full width of a 1600-pixel
 * window is not read by anybody.
 */
export default function ScienceTopic() {
  const { slug } = useParams<{ slug: string }>();
  const [topic, setTopic] = useState<Topic | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) return;
    let cancelled = false;
    setTopic(null);
    setError(null);
    catalog
      .topic(slug)
      .then((data) => {
        if (!cancelled) setTopic(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'This topic could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [slug]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel title="Topic not found" message={error} />
        <Link to="/learn" className="mt-4 inline-block">
          <Button variant="outline">Back to the science library</Button>
        </Link>
      </div>
    );
  }

  if (!topic) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Acquiring rows={6} />
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-[1400px] px-6 py-8">
      <Link
        to="/learn"
        className="mb-6 inline-block font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200"
      >
        ← {topic.strand}
      </Link>

      <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          {/* ── Head ────────────────────────────────────────── */}
          <header className="mb-8">
            <div className="mb-3 flex flex-wrap items-center gap-2">
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
              <span className="font-mono text-micro text-ink-600">
                {topic.estimated_minutes} min read
              </span>
            </div>

            <h1 className="font-display text-display-sm leading-[1.05] text-ink-50">
              {topic.title}
            </h1>
            <p className="mt-4 max-w-[38rem] font-editorial text-lg leading-relaxed text-ink-300">
              {topic.summary}
            </p>
          </header>

          {topic.image && (
            <figure className="mb-8">
              <img
                src={topic.image.url}
                alt={topic.image.alt}
                loading="lazy"
                decoding="async"
                className="w-full max-h-[22rem] object-cover"
              />
              <figcaption className="mt-1.5 font-mono text-[0.6rem] text-ink-600">
                {topic.image.title} · {topic.image.credit}
                {topic.image.instrument ? ` · ${topic.image.instrument}` : ''}
              </figcaption>
            </figure>
          )}

          {/* ── Body ────────────────────────────────────────── */}
          <div className="max-w-[38rem] space-y-8">
            {topic.sections.map((section, index) => (
              <section key={index}>
                <h2 className="mb-3 font-display text-2xl leading-tight text-ink-50">
                  {section.heading}
                </h2>

                {section.body.split('\n\n').map((paragraph, p) => (
                  <p
                    key={p}
                    className="mb-3 font-editorial text-[0.98rem] leading-[1.7] text-ink-200"
                  >
                    {renderInline(paragraph)}
                  </p>
                ))}

                {section.equation && (
                  <div className="my-4 plane-sunken px-4 py-3">
                    <p className="font-mono text-sm text-signal-flame-bright">
                      {section.equation}
                    </p>
                  </div>
                )}

                {section.worked_example && (
                  <div className="my-4 rail">
                    <p className="t-label mb-1.5">Worked</p>
                    <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink-300">
                      {section.worked_example}
                    </pre>
                  </div>
                )}
              </section>
            ))}
          </div>

          {/* ── The interactive part ────────────────────────── */}
          {topic.interactive && (
            <div className="mt-10">
              <InteractiveFigure
                kind={topic.interactive.kind}
                title={topic.interactive.title}
                instruction={topic.interactive.instruction}
                parameters={topic.interactive.parameters}
                outputs={topic.interactive.outputs}
                equation={topic.interactive.equation}
                equationNote={topic.interactive.equation_note}
              />
            </div>
          )}

          {/* ── Glossary ────────────────────────────────────── */}
          {Object.keys(topic.glossary).length > 0 && (
            <div className="mt-10 max-w-[38rem]">
              <SectionRule label="Terms" />
              <dl className="space-y-3">
                {Object.entries(topic.glossary).map(([term, definition]) => (
                  <div key={term} className="rail">
                    <dt className="font-condensed text-sm uppercase tracking-label text-ink-100">
                      {term}
                    </dt>
                    <dd className="mt-0.5 text-sm leading-relaxed text-ink-400">{definition}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>

        {/* ── Rail ──────────────────────────────────────────── */}
        <aside className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          {topic.outcomes.length > 0 && (
            <Panel className="space-y-2">
              <h2 className="t-label">After this you can</h2>
              <ul className="space-y-1.5">
                {topic.outcomes.map((outcome, i) => (
                  <li key={i} className="flex gap-2 text-xs leading-relaxed text-ink-300">
                    <span className="text-signal-nominal">·</span>
                    {outcome}
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          {topic.prerequisites.length > 0 && (
            <div>
              <SectionRule label="Read first" />
              <ul className="space-y-1">
                {topic.prerequisites.map((prerequisite) => (
                  <li key={prerequisite}>
                    <Link
                      to={`/learn/${prerequisite}`}
                      className="block py-1 text-sm text-ink-300 transition-colors hover:text-ink-50"
                    >
                      {prerequisite.replace(/-/g, ' ')} →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {topic.experiment_ids.length > 0 && (
            <div>
              <SectionRule label="Try it" />
              <ul className="space-y-1">
                {topic.experiment_ids.map((id) => (
                  <li key={id}>
                    <Link
                      to={`/experiments/${id}`}
                      className="block py-1 text-sm text-signal-flame transition-colors hover:text-signal-flame-bright"
                    >
                      {id.replace(/-/g, ' ')} →
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {topic.object_ids.length > 0 && (
            <div>
              <SectionRule label="See it" />
              <ul className="space-y-1">
                {topic.object_ids.map((id) => (
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

          {topic.explains_failures.length > 0 && (
            <Panel tone="caution" className="space-y-2">
              <h2 className="t-label">Explains these failures</h2>
              <ul className="space-y-1">
                {topic.explains_failures.map((failure) => (
                  <li key={failure} className="font-mono text-tiny text-ink-300">
                    {failure.replace(/_/g, ' ')}
                  </li>
                ))}
              </ul>
              <p className="text-tiny leading-relaxed text-ink-500">
                If your flight ends this way, this is the topic that says why.
              </p>
            </Panel>
          )}
        </aside>
      </div>
    </article>
  );
}

/**
 * Render the light markup the content uses.
 *
 * `**bold**` only. The content is authored prose, not user input, and a full
 * Markdown pipeline for one emphasis marker would be a dependency and an
 * injection surface bought for nothing.
 */
function renderInline(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? (
      <strong key={i} className="font-medium text-ink-50">
        {part.slice(2, -2)}
      </strong>
    ) : (
      <span key={i}>{part}</span>
    ),
  );
}

export { EmptyState };
