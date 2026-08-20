import { useEffect, useState } from 'react';
import { Card, ErrorPanel, Spinner } from '@/components/ui';
import { ai, type FailureAnalysis } from '@/services/api';
import type { SimResult } from '@/types/simulation';

/**
 * The AI explanation of a failed flight.
 *
 * This is the workflow the product is built around: telemetry and failure
 * records go to the server, relevant engineering knowledge is retrieved, and
 * the answer comes back grounded in sources.
 *
 * The panel deliberately keeps three things visually separate:
 *
 * - what the **simulation computed** (observations)
 * - what the **sources say** (explanations and citations)
 * - what the **simulation cannot model** (limitations)
 *
 * Collapsing those would let a modelled outcome read as a statement about a
 * real vehicle, which is exactly what this platform must not do.
 */
export function FailureAnalysisPanel({
  result,
  designName,
}: {
  result: SimResult;
  designName?: string;
}) {
  const [analysis, setAnalysis] = useState<FailureAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    ai.explainFailure({
      simulation_result: result,
      vehicle_description: designName,
    })
      .then((data) => {
        if (!cancelled) setAnalysis(data);
      })
      .catch((cause: unknown) => {
        if (!cancelled) {
          setError(cause instanceof Error ? cause.message : 'The analysis could not be produced.');
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [result, designName]);

  if (loading) {
    return (
      <Card className="flex items-center gap-3">
        <Spinner />
        <span className="text-xs text-space-400">Analysing the flight…</span>
      </Card>
    );
  }

  if (error) {
    return <ErrorPanel title="Analysis unavailable" message={error} />;
  }

  if (!analysis) return null;

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="font-display text-sm font-semibold text-space-200 mb-1">
          Failure analysis
        </h2>
        <p className="text-xs text-space-300 leading-relaxed">{analysis.summary}</p>
      </div>

      {analysis.likely_cause && (
        <div>
          <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1">Likely cause</h3>
          <p className="text-2xs text-space-300 leading-relaxed">{analysis.likely_cause}</p>
        </div>
      )}

      {analysis.observations.length > 0 && (
        <div>
          <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1.5">
            What the simulation measured
          </h3>
          <ul className="space-y-1">
            {analysis.observations.slice(0, 6).map((observation, i) => (
              <li key={i} className="text-2xs text-space-400 leading-relaxed">
                {observation.statement ?? observation.label}
                {typeof observation.value === 'number' && (
                  <span className="font-mono text-space-300">
                    {' '}
                    {observation.value.toFixed(2)}
                    {observation.unit ? ` ${observation.unit}` : ''}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.mitigations && analysis.mitigations.length > 0 && (
        <div>
          <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1.5">
            What to change
          </h3>
          <ul className="space-y-1.5">
            {analysis.mitigations.map((mitigation, i) => (
              <li key={i} className="text-2xs text-space-300 leading-relaxed">
                {mitigation.action}
                {mitigation.rationale && (
                  <span className="text-space-500"> — {mitigation.rationale}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {analysis.affected_subsystems.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {analysis.affected_subsystems.map((subsystem) => (
            <span
              key={subsystem}
              className="px-1.5 py-0.5 rounded text-2xs border border-space-700 bg-space-800/50 text-space-400"
            >
              {subsystem.toLowerCase()}
            </span>
          ))}
        </div>
      )}

      {analysis.simulation_limitations.length > 0 && (
        <details className="group">
          <summary className="text-2xs uppercase tracking-wider text-space-500 cursor-pointer hover:text-space-400 focus-ring rounded">
            What this simulation cannot model ({analysis.simulation_limitations.length})
          </summary>
          <ul className="mt-2 space-y-1">
            {analysis.simulation_limitations.map((limitation, i) => (
              <li key={i} className="text-2xs text-space-500 leading-relaxed">
                {limitation}
              </li>
            ))}
          </ul>
        </details>
      )}

      {analysis.sources && analysis.sources.length > 0 && (
        <div className="border-t border-space-800 pt-3">
          <h3 className="text-2xs uppercase tracking-wider text-space-500 mb-1.5">Sources</h3>
          <ul className="space-y-1">
            {analysis.sources.map((source, i) => (
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

      <p className="text-2xs text-space-600 leading-relaxed border-t border-space-800 pt-3">
        This explains a <strong className="text-space-500">simulated</strong> flight. It is not a
        claim about any real vehicle or accident.
      </p>
    </Card>
  );
}
