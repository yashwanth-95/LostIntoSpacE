import { Suspense, lazy, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { Badge, Button, Card, EmptyState, Spinner } from '@/components/ui';
import {
  PLAYBACK_SPEEDS,
  useTelemetryPlayback,
} from '@/components/features/simulation/useTelemetryPlayback';
import { FailureAnalysisPanel } from '@/components/features/simulation/FailureAnalysisPanel';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass, formatVelocity } from '@/lib/utils';
import type { SimEvent } from '@/types/simulation';

/**
 * Mission Control.
 *
 * The 3D viewport is loaded lazily and separately from the rest of the page:
 * Three.js is the single heaviest dependency in the bundle, and the telemetry,
 * events and mission summary are all useful before it arrives.
 */
const FlightViewport = lazy(() =>
  import('@/components/features/simulation/FlightViewport').then((m) => ({
    default: m.FlightViewport,
  })),
);

export default function MissionControl() {
  const result = useMissionStore((s) => s.result);
  const mission = useMissionStore((s) => s.mission);
  const design = useMissionStore((s) => s.design);
  const meta = useMissionStore((s) => s.resultMeta);

  const telemetry = result?.telemetry ?? [];
  const playback = useTelemetryPlayback(telemetry, { autoPlay: true });
  const [showAnalysis, setShowAnalysis] = useState(false);

  // Events that have already happened at the current mission time.
  const elapsedEvents = useMemo(
    () => (result?.events ?? []).filter((e) => e.t <= playback.missionTime),
    [result, playback.missionTime],
  );

  if (!result) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState
          title="No flight to monitor"
          description="Configure a launch and run it, and the telemetry will appear here."
          action={
            <Link to="/launch">
              <Button>Go to Launch</Button>
            </Link>
          }
        />
      </div>
    );
  }

  const frame = playback.frame;
  const failed = result.outcome === 'failure' || result.failures.length > 0;

  return (
    <div className="mx-auto max-w-[1600px] px-6 py-6">
      <header className="flex flex-wrap items-start justify-between gap-4 mb-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <h1 className="font-display text-xl font-semibold text-space-100">
              {mission.name}
            </h1>
            <Badge
              variant={
                result.outcome === 'success'
                  ? 'nominal'
                  : result.outcome === 'partial'
                    ? 'warning'
                    : 'fatal'
              }
            >
              {result.outcome.toUpperCase()}
            </Badge>
          </div>
          <p className="text-xs text-space-500">
            {design?.name} · {mission.launchSite.name} · target{' '}
            {mission.targetAltitudeKm} km · {result.termination_reason}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Link to="/launch">
            <Button size="sm" variant="ghost">
              Reconfigure
            </Button>
          </Link>
          <Link to="/builder">
            <Button size="sm" variant="secondary">
              Edit rocket
            </Button>
          </Link>
        </div>
      </header>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        {/* Viewport + controls */}
        <div className="space-y-4">
          <div className="glass-panel overflow-hidden">
            <Suspense
              fallback={
                <div className="h-[420px] flex items-center justify-center">
                  <div className="flex flex-col items-center gap-2">
                    <Spinner />
                    <span className="text-2xs text-space-500">Loading 3D view…</span>
                  </div>
                </div>
              }
            >
              <FlightViewport
                telemetry={telemetry}
                index={playback.index}
                className="h-[420px] w-full"
              />
            </Suspense>

            {/* Transport */}
            <div className="border-t border-space-800 p-3 space-y-2">
              <div className="flex items-center gap-3">
                <Button size="sm" onClick={playback.toggle}>
                  {playback.isPlaying ? 'Pause' : 'Play'}
                </Button>
                <Button size="sm" variant="ghost" onClick={playback.reset}>
                  Reset
                </Button>

                <span className="font-mono text-xs text-accent-cyan tabular-nums w-20">
                  T+{playback.missionTime.toFixed(1)}s
                </span>

                <input
                  type="range"
                  min={0}
                  max={playback.duration || 1}
                  step={0.1}
                  value={playback.missionTime}
                  onChange={(e) => playback.seek(Number(e.target.value))}
                  className="flex-1 accent-accent-cyan"
                  aria-label="Mission time"
                />

                <div className="flex items-center gap-1" role="group" aria-label="Playback speed">
                  {PLAYBACK_SPEEDS.map((speed) => (
                    <button
                      key={speed}
                      onClick={() => playback.setSpeed(speed)}
                      className={cn(
                        'px-1.5 py-0.5 rounded text-2xs font-mono border transition-colors focus-ring',
                        playback.speed === speed
                          ? 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30'
                          : 'text-space-500 border-space-700 hover:text-space-300',
                      )}
                      aria-pressed={playback.speed === speed}
                    >
                      {speed}×
                    </button>
                  ))}
                </div>
              </div>
              <p className="text-2xs text-space-600">
                Playback speed is independent of the render frame rate — the flight was computed
                once, on the server, and is being replayed here.
              </p>
            </div>
          </div>

          {/* Telemetry */}
          <Card>
            <h2 className="font-display text-sm font-semibold text-space-200 mb-3">Telemetry</h2>
            <dl className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
              <Gauge label="Altitude" value={`${((frame?.altitude_m ?? 0) / 1000).toFixed(1)}`} unit="km" primary />
              <Gauge label="Speed" value={formatVelocity(frame?.speed_ms ?? 0)} />
              <Gauge label="Vertical" value={formatVelocity(frame?.vertical_speed_ms ?? 0)} />
              <Gauge label="Downrange" value={`${((frame?.downrange_m ?? 0) / 1000).toFixed(1)}`} unit="km" />
              <Gauge label="Mass" value={formatMass(frame?.mass_kg ?? 0)} />
              <Gauge label="Propellant" value={`${((frame?.fuel_fraction ?? 0) * 100).toFixed(0)}`} unit="%" />
              <Gauge label="Thrust" value={`${((frame?.thrust_N ?? 0) / 1000).toFixed(0)}`} unit="kN" />
              <Gauge label="Drag" value={`${((frame?.drag_N ?? 0) / 1000).toFixed(1)}`} unit="kN" />
              <Gauge label="g-load" value={(frame?.g_load_g ?? 0).toFixed(2)} unit="g" />
              <Gauge label="Dyn. pressure" value={`${((frame?.dynamic_pressure_Pa ?? 0) / 1000).toFixed(1)}`} unit="kPa" />
              <Gauge label="Mach" value={(frame?.mach ?? 0).toFixed(2)} />
              <Gauge label="TWR" value={(frame?.twr ?? 0).toFixed(2)} />
            </dl>

            <div className="mt-3 pt-3 border-t border-space-800 flex flex-wrap items-center gap-4">
              <StatusChip label="Stage" value={`${(frame?.stage ?? 0) + 1}`} />
              <StatusChip label="Engine" value={frame?.engine_on ? 'BURNING' : 'OFF'} tone={frame?.engine_on ? 'good' : 'idle'} />
              <StatusChip label="Stage status" value={(frame?.stage_status ?? 'stowed').toUpperCase()} />
              <StatusChip
                label="Mission state"
                value={frame?.mission_state ?? 'PREPARATION'}
                tone={frame?.mission_state === 'FAILURE' ? 'bad' : 'good'}
              />
              {frame?.in_orbit && <StatusChip label="Orbit" value="ACHIEVED" tone="good" />}
            </div>

            {frame?.in_orbit && (
              <p className="mt-2 text-2xs text-space-500 font-mono">
                periapsis {(frame.periapsis_altitude_m / 1000).toFixed(0)} km · apoapsis{' '}
                {(frame.apoapsis_altitude_m / 1000).toFixed(0)} km · e ={' '}
                {frame.eccentricity.toFixed(4)}
              </p>
            )}
          </Card>
        </div>

        {/* Right rail */}
        <aside className="space-y-4">
          {/* Events */}
          <Card>
            <h2 className="font-display text-sm font-semibold text-space-200 mb-3">
              Mission events
            </h2>
            <ol className="space-y-1.5 max-h-[280px] overflow-y-auto pr-1">
              {result.events.map((event, i) => (
                <EventRow
                  key={`${event.t}-${event.type}-${i}`}
                  event={event}
                  reached={elapsedEvents.includes(event)}
                  onSeek={() => playback.seek(event.t)}
                />
              ))}
            </ol>
          </Card>

          {/* Summary */}
          <Card>
            <h2 className="font-display text-sm font-semibold text-space-200 mb-3">
              Flight summary
            </h2>
            <dl className="space-y-1.5 text-2xs">
              <SummaryRow label="Max altitude" value={`${(result.summary.max_altitude_m / 1000).toFixed(1)} km`} />
              <SummaryRow label="Max speed" value={formatVelocity(result.summary.max_speed_ms)} />
              <SummaryRow label="Max g-load" value={`${result.summary.max_acceleration_g.toFixed(2)} g`} />
              <SummaryRow label="Max-Q" value={`${(result.summary.max_dynamic_pressure_Pa / 1000).toFixed(1)} kPa at ${(result.summary.max_q_altitude_m / 1000).toFixed(1)} km`} />
              <SummaryRow label="Max Mach" value={result.summary.max_mach.toFixed(2)} />
              <SummaryRow label="Downrange" value={`${(result.summary.max_downrange_m / 1000).toFixed(0)} km`} />
              <SummaryRow label="Flight time" value={`${result.summary.flight_time_s.toFixed(1)} s`} />
              <SummaryRow label="Stages separated" value={`${result.summary.stages_separated}`} />
              <SummaryRow label="Propellant used" value={formatMass(result.summary.propellant_used_kg)} />
              <SummaryRow label="Ideal Δv" value={`${result.summary.delta_v_ideal_ms.toFixed(0)} m/s`} />
              <SummaryRow label="Gravity loss" value={`${result.summary.gravity_loss_ms.toFixed(0)} m/s`} />
              <SummaryRow label="Drag loss" value={`${result.summary.drag_loss_ms.toFixed(0)} m/s`} />
            </dl>

            {meta && (
              <p className="mt-3 pt-3 border-t border-space-800 text-2xs text-space-600 leading-relaxed">
                Computed by {String(meta.engine ?? 'the simulation engine')} in{' '}
                {Number(meta.compute_time_s ?? 0).toFixed(2)}s
                {meta.telemetry_decimated ? ', telemetry decimated for transport' : ''}. Educational
                simulation with documented approximations — not flight-certified engineering.
              </p>
            )}
          </Card>

          {/* Failures */}
          {failed && (
            <Card className="border-severity-fatal/30 space-y-3">
              <h2 className="font-display text-sm font-semibold text-severity-fatal">
                Failure{result.failures.length === 1 ? '' : 's'}
              </h2>
              {result.failures.map((failure) => (
                <div key={failure.id} className="space-y-1.5">
                  <div className="flex items-center gap-2">
                    <Badge variant="fatal">{failure.mode_id}</Badge>
                    <span className="text-2xs font-mono text-space-500">
                      T+{failure.t.toFixed(1)}s
                    </span>
                  </div>
                  <p className="text-2xs text-space-300 leading-relaxed">
                    {failure.educational_explanation}
                  </p>
                  <p className="text-2xs text-space-500 leading-relaxed">
                    <span className="text-space-400">Fix:</span> {failure.recommended_fix}
                  </p>
                  <p className="text-2xs font-mono text-space-600">
                    {failure.trigger_condition}: {failure.measured_value.toFixed(2)} vs{' '}
                    {failure.threshold_value.toFixed(2)} {failure.unit}
                  </p>
                </div>
              ))}

              {!showAnalysis && (
                <Button size="sm" className="w-full" onClick={() => setShowAnalysis(true)}>
                  Ask the assistant why
                </Button>
              )}
            </Card>
          )}

          {showAnalysis && <FailureAnalysisPanel result={result} designName={design?.name} />}
        </aside>
      </div>
    </div>
  );
}

function Gauge({
  label,
  value,
  unit,
  primary,
}: {
  label: string;
  value: string;
  unit?: string;
  primary?: boolean;
}) {
  return (
    <div>
      <dt className="text-2xs text-space-500 mb-0.5">{label}</dt>
      <dd
        className={cn(
          'font-mono tabular-nums',
          primary ? 'text-lg text-accent-cyan' : 'text-sm text-space-100',
        )}
      >
        {value}
        {unit && <span className="text-2xs text-space-500 ml-1">{unit}</span>}
      </dd>
    </div>
  );
}

function StatusChip({
  label,
  value,
  tone = 'idle',
}: {
  label: string;
  value: string;
  tone?: 'good' | 'bad' | 'idle';
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-2xs text-space-600">{label}</span>
      <span
        className={cn(
          'font-mono text-2xs px-1.5 py-0.5 rounded border',
          tone === 'good' && 'text-accent-emerald border-accent-emerald/30 bg-accent-emerald/10',
          tone === 'bad' && 'text-severity-fatal border-severity-fatal/30 bg-severity-fatal/10',
          tone === 'idle' && 'text-space-300 border-space-700 bg-space-800/50',
        )}
      >
        {value}
      </span>
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-2">
      <dt className="text-space-500">{label}</dt>
      <dd className="font-mono text-space-200">{value}</dd>
    </div>
  );
}

function EventRow({
  event,
  reached,
  onSeek,
}: {
  event: SimEvent;
  reached: boolean;
  onSeek: () => void;
}) {
  const severityTone =
    event.severity === 'fatal' || event.severity === 'critical'
      ? 'text-severity-fatal'
      : event.severity === 'warning'
        ? 'text-severity-warning'
        : 'text-space-300';

  return (
    <li>
      <button
        onClick={onSeek}
        className={cn(
          'w-full text-left flex items-baseline gap-2 px-2 py-1 rounded transition-colors focus-ring hover:bg-space-800/60',
          !reached && 'opacity-40',
        )}
      >
        <span className="font-mono text-2xs text-space-500 shrink-0 w-14 tabular-nums">
          T+{event.t.toFixed(1)}
        </span>
        <span className={cn('text-2xs leading-snug', severityTone)}>{event.description}</span>
      </button>
    </li>
  );
}
