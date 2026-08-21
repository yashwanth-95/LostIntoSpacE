import { Acquiring, Panel, Readout, StatusDot } from '@/components/ui';
import type { SiteWeather } from '@/services/api';
import { cn } from '@/lib/utils';

/**
 * Launch-day conditions at the selected pad.
 *
 * These numbers are not decoration. Surface temperature and pressure shift the
 * whole atmosphere profile away from the standard day, humidity changes air
 * density, and the wind drives a full altitude profile that the force model
 * resolves into airspeed and angle of attack. Change the site and the
 * trajectory changes.
 *
 * The panel is explicit about provenance. A live observation says so and names
 * the provider; a standard-day fallback says *that*, with the reason, and is
 * never dressed up as a measurement.
 */

const STATUS_TONE = {
  go: 'nominal',
  caution: 'caution',
  'no-go': 'critical',
} as const;

export function WeatherPanel({
  weather,
  loading,
  onRefresh,
}: {
  weather: SiteWeather | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  if (loading && !weather) {
    return (
      <Panel className="space-y-3">
        <h2 className="t-label">Conditions</h2>
        <Acquiring rows={5} />
      </Panel>
    );
  }

  if (!weather) {
    return (
      <Panel tone="caution" className="space-y-2">
        <h2 className="t-label">Conditions</h2>
        <p className="text-xs leading-relaxed text-ink-400">
          No observation available. The flight will use US Standard Atmosphere values in still
          air — a defensible default, but not a measurement.
        </p>
      </Panel>
    );
  }

  const { observation, suitability } = weather;
  const tone = STATUS_TONE[suitability.status];

  return (
    <Panel
      tone={suitability.status === 'no-go' ? 'oxide' : suitability.status === 'caution' ? 'caution' : 'nominal'}
      className="space-y-4"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="t-label">Conditions</h2>
          <p className="mt-0.5 flex items-center gap-1.5">
            <StatusDot tone={tone} live={observation.is_live} />
            <span
              className={cn(
                'font-condensed text-sm uppercase tracking-label',
                suitability.status === 'go'
                  ? 'text-signal-nominal-bright'
                  : suitability.status === 'caution'
                    ? 'text-signal-caution-bright'
                    : 'text-signal-oxide-bright',
              )}
            >
              {suitability.status === 'no-go' ? 'Hold' : suitability.status}
            </span>
          </p>
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="shrink-0 font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200 disabled:opacity-40 focus-ring"
        >
          {loading ? 'Fetching…' : 'Refresh'}
        </button>
      </div>

      <p className="text-xs leading-relaxed text-ink-300">{suitability.summary}</p>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3 hairline-t pt-3">
        <Readout
          label="Temperature"
          value={(observation.temperature_K - 273.15).toFixed(1)}
          unit="°C"
        />
        <Readout
          label="Pressure"
          value={(observation.pressure_Pa / 100).toFixed(1)}
          unit="hPa"
        />
        <Readout
          label="Wind"
          value={observation.wind.speed_ms.toFixed(1)}
          unit="m/s"
          hint={`from ${observation.wind.direction_deg.toFixed(0)}°${
            observation.wind.gust_ms ? `, gusting ${observation.wind.gust_ms.toFixed(1)}` : ''
          }`}
        />
        <Readout
          label="Humidity"
          value={(observation.relative_humidity * 100).toFixed(0)}
          unit="%"
        />
        <Readout
          label="Air density"
          value={observation.air_density_kgm3.toFixed(4)}
          unit="kg/m³"
          tone={weather.density_vs_standard_pct > 2 ? 'caution' : 'neutral'}
          hint={`${weather.density_vs_standard_pct > 0 ? '+' : ''}${weather.density_vs_standard_pct.toFixed(1)}% vs standard`}
        />
        <Readout
          label="Speed of sound"
          value={observation.speed_of_sound_ms.toFixed(1)}
          unit="m/s"
          hint="Where Mach 1 sits today"
        />
        {observation.jet_wind_speed_ms != null && (
          <Readout
            label="Wind at 250 hPa"
            value={observation.jet_wind_speed_ms!.toFixed(0)}
            unit="m/s"
            tone={observation.jet_wind_speed_ms! > 40 ? 'caution' : 'neutral'}
            hint="Near max-Q altitude"
          />
        )}
        <Readout
          label="Cloud"
          value={(observation.cloud_cover * 100).toFixed(0)}
          unit="%"
        />
      </dl>

      {/* Each criterion, with the measurement that produced its verdict. */}
      <div className="space-y-1.5 hairline-t pt-3">
        {suitability.constraints.map((constraint) => (
          <div key={constraint.id} className="group">
            <div className="flex items-baseline justify-between gap-2">
              <span className="flex min-w-0 items-center gap-1.5">
                <StatusDot tone={STATUS_TONE[constraint.status]} />
                <span className="truncate text-tiny text-ink-300">{constraint.label}</span>
              </span>
              <span className="shrink-0 font-mono text-[0.65rem] tabular-nums text-ink-400">
                {constraint.measured} / {constraint.limit} {constraint.unit}
              </span>
            </div>
            {constraint.status !== 'go' && (
              <p className="mt-0.5 pl-3 text-[0.65rem] leading-relaxed text-ink-500">
                {constraint.explanation}
              </p>
            )}
          </div>
        ))}
      </div>

      <p className="text-[0.6rem] leading-relaxed text-ink-600 hairline-t pt-3">
        {observation.is_live ? (
          <>
            Observed {new Date(observation.observed_at).toUTCString().slice(5, 22)} UTC ·{' '}
            {observation.attribution}
          </>
        ) : (
          observation.fallback_reason ?? 'Not a live observation.'
        )}
      </p>
    </Panel>
  );
}
