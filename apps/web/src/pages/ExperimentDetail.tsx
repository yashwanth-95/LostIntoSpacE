import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import {
  Acquiring,
  Badge,
  Button,
  ErrorPanel,
  Panel,
  Readout,
  SectionRule,
  StatusDot,
} from '@/components/ui';
import { catalog, type Experiment } from '@/services/api';

/**
 * One experiment.
 *
 * Laid out as a scientific procedure rather than as a tutorial: question,
 * hypothesis, controls, method, and only then the explanation — which is kept
 * behind a deliberate reveal, because reading the answer before running the
 * sweep turns an experiment back into a demonstration.
 */
export default function ExperimentDetail() {
  const { experimentId } = useParams<{ experimentId: string }>();
  const [experiment, setExperiment] = useState<Experiment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    if (!experimentId) return;
    let cancelled = false;
    setExperiment(null);
    setRevealed(false);
    catalog
      .experiment(experimentId)
      .then((data) => {
        if (!cancelled) setExperiment(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'This experiment could not be loaded.');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [experimentId]);

  if (error) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <ErrorPanel title="Experiment not found" message={error} />
        <Link to="/experiments" className="mt-4 inline-block">
          <Button variant="outline">Back to experiments</Button>
        </Link>
      </div>
    );
  }

  if (!experiment) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <Acquiring rows={6} />
      </div>
    );
  }

  return (
    <article className="mx-auto max-w-[1200px] px-6 py-8">
      <Link
        to="/experiments"
        className="mb-6 inline-block font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200"
      >
        ← {experiment.category}
      </Link>

      <header className="mb-8 max-w-[42rem]">
        <div className="mb-3 flex flex-wrap items-center gap-2">
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
          <span className="font-mono text-micro text-ink-600">
            {experiment.sweep.length || experiment.estimated_runs} runs
          </span>
        </div>

        <h1 className="font-display text-display-sm leading-[1.05] text-ink-50">
          {experiment.title}
        </h1>
        <p className="mt-4 font-editorial text-lg leading-relaxed text-ink-300">
          {experiment.question}
        </p>
      </header>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-8">
          <section>
            <SectionRule label="Objective" />
            <p className="max-w-[40rem] text-sm leading-relaxed text-ink-200">
              {experiment.objective}
            </p>
          </section>

          <section>
            <SectionRule label="Hypothesis" />
            <Panel tone="caution">
              <p className="text-sm leading-relaxed text-ink-100">{experiment.hypothesis}</p>
              <p className="mt-2 text-tiny text-ink-500">
                This is what most people expect. Run the sweep before reading further.
              </p>
            </Panel>
          </section>

          <section>
            <SectionRule label="Method" />
            <ol className="space-y-3">
              {experiment.procedure.map((step, index) => (
                <li key={index}>
                  <Panel className="flex gap-3">
                    <span className="shrink-0 font-mono text-sm text-signal-flame">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <div className="min-w-0 space-y-1.5">
                      <p className="text-sm leading-relaxed text-ink-100">{step.instruction}</p>
                      {Object.keys(step.changes).length > 0 && (
                        <p className="font-mono text-tiny text-ink-500">
                          {Object.entries(step.changes)
                            .map(([key, value]) => `${key} = ${value}`)
                            .join(' · ')}
                        </p>
                      )}
                      {step.expectation && (
                        <p className="text-tiny leading-relaxed text-signal-cryo-bright">
                          Expect: {step.expectation}
                        </p>
                      )}
                    </div>
                  </Panel>
                </li>
              ))}
            </ol>
          </section>

          <section>
            <SectionRule label="What actually happens" />
            {revealed ? (
              <Panel tone="nominal" className="space-y-3">
                {experiment.explanation.split('\n\n').map((paragraph, i) => (
                  <p key={i} className="text-sm leading-relaxed text-ink-100">
                    {paragraph}
                  </p>
                ))}
              </Panel>
            ) : (
              <Panel className="space-y-3 text-center">
                <p className="text-sm leading-relaxed text-ink-400">
                  Run the sweep first. Reading the answer before doing the experiment turns it
                  into something you were told rather than something you found.
                </p>
                <Button variant="outline" onClick={() => setRevealed(true)}>
                  Reveal the explanation
                </Button>
              </Panel>
            )}
          </section>
        </div>

        <aside className="space-y-5 lg:sticky lg:top-20 lg:self-start">
          <Panel className="space-y-3">
            <h2 className="t-label">The variable</h2>
            <Readout
              size="lg"
              label={experiment.variable_label}
              value={
                experiment.sweep.length > 0
                  ? `${experiment.sweep[0]} → ${experiment.sweep[experiment.sweep.length - 1]}`
                  : 'categorical'
              }
              unit={experiment.variable_unit ?? undefined}
            />
            {experiment.sweep.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {experiment.sweep.map((value) => (
                  <span
                    key={value}
                    className="rounded-instrument border border-ink-700 bg-ink-850 px-1.5 py-0.5 font-mono text-[0.6rem] text-ink-300"
                  >
                    {value}
                  </span>
                ))}
              </div>
            )}
          </Panel>

          <Panel className="space-y-2">
            <h2 className="t-label">Held constant</h2>
            <ul className="space-y-1.5">
              {experiment.controls.map((control, i) => (
                <li key={i} className="flex gap-2 text-tiny leading-relaxed text-ink-400">
                  <StatusDot tone="quiet" className="mt-1.5 shrink-0" />
                  {control}
                </li>
              ))}
            </ul>
            <p className="text-tiny leading-relaxed text-ink-600 hairline-t pt-2">
              An experiment that does not say what it held constant is a demonstration.
            </p>
          </Panel>

          <Panel className="space-y-2">
            <h2 className="t-label">Measured</h2>
            <ul className="space-y-1">
              {experiment.measures.map((measure) => (
                <li key={measure} className="font-mono text-tiny text-ink-300">
                  {measure.replace(/_/g, ' ')}
                </li>
              ))}
            </ul>
          </Panel>

          {experiment.topic_slugs.length > 0 && (
            <div>
              <SectionRule label="The science" />
              <ul className="space-y-1">
                {experiment.topic_slugs.map((slug) => (
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

          <div className="flex flex-col gap-2">
            <Link to="/builder">
              <Button className="w-full">Set up the vehicle</Button>
            </Link>
            <Link to="/launch">
              <Button variant="outline" className="w-full">
                Run the first case
              </Button>
            </Link>
          </div>
        </aside>
      </div>
    </article>
  );
}
