import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import { analyzeRocket } from '@lostintospace/simulation-engine/core/builder';
import { vehicleFromAnalysis } from '@lostintospace/simulation-engine/core/vehicle';

import { WeatherPanel } from '@/components/features/launch/WeatherPanel';
import {
  Badge,
  Button,
  EmptyState,
  ErrorPanel,
  Input,
  Panel,
  Readout,
  SectionRule,
  Select,
  StatusDot,
} from '@/components/ui';
import { MISSION_PROFILES, buildSimConfig } from '@/lib/simConfig';
import {
  catalog,
  environment as environmentApi,
  simulation,
  type LaunchSiteRecord,
  type SiteWeather,
} from '@/services/api';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass } from '@/lib/utils';

/**
 * Launch configuration and pre-flight.
 *
 * Three decisions, made in the order they constrain each other: *where* you
 * launch from, *what the weather is doing there*, and *where you are trying to
 * go*. The brief was explicit that these are related but not the same thing,
 * and that a user should not have to reason about orbital mechanics to pick a
 * pad — so the site is chosen on its own terms, and the page then tells you
 * what that choice costs.
 *
 * Latitude is the constraint that does the work. It fixes the lowest
 * inclination reachable without a plane change and the eastward velocity a
 * launch inherits from Earth's rotation, and both are shown against the site
 * rather than buried in a physics lesson.
 *
 * The pre-flight checks are computed from the design's own analysis, not from a
 * successful simulation — the point is to tell someone their rocket cannot fly
 * *before* they watch it not fly. A failing check does not block launch, though:
 * flying a vehicle you have been told will fail, and seeing exactly how, is the
 * most useful thing this platform does.
 */

/**
 * Liftoff thrust-to-weight above which max-Q becomes the limiting risk.
 *
 * Real launch vehicles fly 1.2–1.5. Past roughly 2.5 the vehicle is still in
 * dense air when it gets fast, and dynamic pressure — which grows with the
 * square of speed — threatens the airframe before the atmosphere thins out.
 * Advisory: the vehicle's own rated limit is what the simulation enforces.
 */
const MAX_SAFE_LIFTOFF_TWR = 2.5;

export default function Launch() {
  const navigate = useNavigate();
  const design = useMissionStore((s) => s.design);
  const mission = useMissionStore((s) => s.mission);
  const updateMission = useMissionStore((s) => s.updateMission);
  const setResult = useMissionStore((s) => s.setResult);

  const [sites, setSites] = useState<LaunchSiteRecord[]>([]);
  const [siteId, setSiteId] = useState<string>('ksc-lc39a');
  const [weather, setWeather] = useState<SiteWeather | null>(null);
  const [weatherLoading, setWeatherLoading] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const registry = useMemo(() => createStockRegistry(), []);
  const analysis = useMemo(
    () => (design ? analyzeRocket(design, registry) : null),
    [design, registry],
  );
  const vehicle = useMemo(
    () => (design && analysis ? vehicleFromAnalysis(analysis, design) : null),
    [design, analysis],
  );

  useEffect(() => {
    catalog
      .launchSites()
      .then(setSites)
      .catch(() => setSites([]));
  }, []);

  // Weather follows the site. Changing the pad invalidates the observation,
  // because conditions at Baikonur say nothing about conditions at Kourou.
  useEffect(() => {
    let cancelled = false;
    setWeatherLoading(true);
    environmentApi
      .weather(siteId)
      .then((data) => {
        if (cancelled) return;
        setWeather(data);
        updateMission({
          launchSite: {
            name: data.site.name,
            latitude_deg: data.site.latitude_deg,
            longitude_deg: data.site.longitude_deg,
            altitude_m: data.site.elevation_m,
          },
          environment: data.simulation_environment,
          environmentSiteId: data.site.id,
        });
      })
      .catch(() => {
        if (!cancelled) setWeather(null);
      })
      .finally(() => {
        if (!cancelled) setWeatherLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // `updateMission` is a stable zustand action.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteId]);

  const site = sites.find((s) => s.id === siteId) ?? null;

  const refreshWeather = () => {
    setWeatherLoading(true);
    environmentApi
      .weather(siteId, true)
      .then((data) => {
        setWeather(data);
        updateMission({
          environment: data.simulation_environment,
          environmentSiteId: data.site.id,
        });
      })
      .catch(() => undefined)
      .finally(() => setWeatherLoading(false));
  };

  const checks = useMemo(() => {
    if (!analysis) return [];
    const targetDeltaV = estimateRequiredDeltaV(mission.targetAltitudeKm, mission.missionType);
    const inclination = site?.min_inclination_deg ?? Math.abs(mission.launchSite.latitude_deg);

    return [
      {
        id: 'stages',
        label: 'Vehicle has at least one stage',
        pass: analysis.stages.length > 0,
        detail: `${analysis.stages.length} stage${analysis.stages.length === 1 ? '' : 's'}`,
      },
      {
        id: 'twr',
        label: 'Liftoff thrust exceeds weight',
        pass: analysis.liftoffTWR >= 1,
        detail: `TWR ${analysis.liftoffTWR.toFixed(2)}${
          analysis.liftoffTWR < 1 ? ' — will not leave the pad' : ''
        }`,
      },
      {
        // Too much thrust is a real failure mode, and a non-obvious one: a
        // vehicle with a high liftoff TWR reaches high speed while still deep
        // in dense air, and dynamic pressure grows with the square of speed.
        id: 'max-q-risk',
        label: 'Liftoff TWR is not excessive',
        pass: analysis.liftoffTWR <= MAX_SAFE_LIFTOFF_TWR,
        detail:
          analysis.liftoffTWR > MAX_SAFE_LIFTOFF_TWR
            ? `TWR ${analysis.liftoffTWR.toFixed(2)} builds speed low in the atmosphere — likely to exceed the airframe's max-Q limit`
            : `TWR ${analysis.liftoffTWR.toFixed(2)}, within the usual 1.2–1.5 band`,
      },
      {
        id: 'deltav',
        label: 'Δv budget covers the target',
        pass: analysis.totalDeltaV_ms >= targetDeltaV,
        detail: `${analysis.totalDeltaV_ms.toFixed(0)} m/s available, about ${targetDeltaV.toFixed(0)} m/s needed`,
      },
      {
        id: 'stability',
        label: 'Statically stable when full',
        pass: analysis.stabilityWet.stabilityMargin_cal >= 0.5,
        detail: `${analysis.stabilityWet.stabilityMargin_cal.toFixed(2)} calibers`,
      },
      {
        // The constraint people forget until it bites: you cannot reach an
        // inclination below your launch latitude without a plane change, and a
        // plane change at orbital speed costs more than most upper stages have.
        id: 'inclination',
        label: 'Target inclination is reachable from this site',
        pass: mission.missionType === 'suborbital' || inclination <= 90,
        detail:
          mission.missionType === 'suborbital'
            ? 'Not applicable to a suborbital profile'
            : `Lowest reachable inclination from ${site?.short_name ?? 'this site'} is ${inclination.toFixed(1)}° without a plane change`,
      },
      {
        id: 'weather',
        label: 'Conditions are within commit criteria',
        pass: (weather?.suitability.status ?? 'go') !== 'no-go',
        detail: weather
          ? weather.suitability.summary
          : 'No observation — the flight will use standard-day values',
      },
      {
        id: 'payload',
        label: 'Carries a payload',
        pass: analysis.payloadMass_kg > 0,
        detail:
          analysis.payloadMass_kg > 0
            ? formatMass(analysis.payloadMass_kg)
            : 'No payload — the flight still runs',
      },
    ];
  }, [analysis, mission, site, weather]);

  const blocking = checks.filter((c) => !c.pass);

  const launch = async () => {
    if (!vehicle) return;
    setLaunching(true);
    setError(null);
    try {
      const config = buildSimConfig({
        vehicle,
        missionName: mission.name,
        objective: mission.objective,
        targetAltitudeKm: mission.targetAltitudeKm,
        missionType: mission.missionType,
        launchSite: mission.launchSite,
        guidanceMode: mission.guidanceMode,
        launchAzimuthDeg: mission.launchAzimuthDeg,
        // The measured conditions, passed through untouched.
        environment: mission.environment ?? undefined,
      });

      const { data, meta } = await simulation.run(config);
      setResult(data, config, meta);
      navigate('/mission-control');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'The launch could not be started.');
    } finally {
      setLaunching(false);
    }
  };

  if (!design || !analysis) {
    return (
      <div className="mx-auto max-w-3xl px-6 py-16">
        <EmptyState
          title="No rocket to launch"
          description="Build a vehicle first, or start from one of the reference designs in the Rocket Lab."
          action={
            <Link to="/rocket-lab">
              <Button>Open Rocket Lab</Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[1400px] px-6 py-6">
      <header className="mb-5 hairline-b pb-4">
        <p className="t-label mb-1">Simulate · Launch setup</p>
        <h1 className="font-display text-3xl leading-none text-ink-50">{mission.name}</h1>
        <p className="mt-1.5 font-mono text-tiny text-ink-500">
          Flying {design.name} · {formatMass(analysis.totalWetMass_kg)} on the pad ·{' '}
          {analysis.totalDeltaV_ms.toFixed(0)} m/s ideal Δv
        </p>
      </header>

      {error && <ErrorPanel message={error} className="mb-4" onRetry={() => setError(null)} />}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          {/* ── Launch site ───────────────────────────────────── */}
          <SectionRule label="Launch site" />

          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {sites.map((candidate) => (
              <button
                key={candidate.id}
                onClick={() => setSiteId(candidate.id)}
                className={cn(
                  'rounded-instrument border p-3 text-left transition-colors duration-quick focus-ring',
                  candidate.id === siteId
                    ? 'border-signal-flame/50 bg-signal-flame/8'
                    : 'border-ink-800 bg-ink-900 hover:border-ink-600',
                )}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm text-ink-100">{candidate.short_name}</span>
                  <span className="shrink-0 font-mono text-micro text-ink-500">
                    {candidate.latitude_deg.toFixed(1)}°
                  </span>
                </div>
                <p className="mt-0.5 truncate font-mono text-[0.6rem] text-ink-600">
                  {candidate.country} · {candidate.operator}
                </p>
                <p className="mt-1 font-mono text-[0.6rem] text-ink-500">
                  +{candidate.earth_rotation_bonus_ms?.toFixed(0) ?? '—'} m/s rotation
                </p>
              </button>
            ))}
          </div>

          {site && (
            <Panel className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-xl leading-tight text-ink-50">{site.name}</h2>
                  <p className="mt-0.5 font-mono text-tiny text-ink-500">
                    {site.latitude_deg.toFixed(4)}°, {site.longitude_deg.toFixed(4)}° ·{' '}
                    {site.elevation_m.toFixed(0)} m
                  </p>
                </div>
                <div className="flex flex-wrap justify-end gap-1">
                  {site.typical_orbits.slice(0, 3).map((orbit) => (
                    <Badge key={orbit}>{orbit}</Badge>
                  ))}
                </div>
              </div>

              <p className="max-w-prose text-xs leading-relaxed text-ink-400">{site.notes}</p>

              <dl className="grid grid-cols-2 gap-x-6 gap-y-2 hairline-t pt-3 sm:grid-cols-4">
                <Readout
                  label="Lowest inclination"
                  value={site.min_inclination_deg?.toFixed(2) ?? '—'}
                  unit="°"
                  hint="Without a plane change"
                />
                <Readout
                  label="Rotation bonus"
                  value={`+${site.earth_rotation_bonus_ms?.toFixed(0) ?? '—'}`}
                  unit="m/s"
                  hint="Free, eastward, ×cos(latitude)"
                />
                <Readout
                  label="Azimuth range"
                  value={
                    site.azimuth_range_deg.length === 2
                      ? `${site.azimuth_range_deg[0]}–${site.azimuth_range_deg[1]}`
                      : '—'
                  }
                  unit="°"
                  hint="Corridors that avoid populated land"
                />
                <Readout
                  label="Established"
                  value={site.established_year ?? '—'}
                  hint={`${site.pads.length} pad${site.pads.length === 1 ? '' : 's'}`}
                />
              </dl>

              {site.vehicles.length > 0 && (
                <p className="text-tiny leading-relaxed text-ink-500 hairline-t pt-3">
                  <span className="t-label mr-2">Flies from here</span>
                  {site.vehicles.join(' · ')}
                </p>
              )}
            </Panel>
          )}

          {/* ── Mission ───────────────────────────────────────── */}
          <SectionRule label="Mission" />

          <Panel className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="t-label mb-1 block">Mission name</span>
                <Input
                  value={mission.name}
                  onChange={(e) => updateMission({ name: e.target.value })}
                />
              </label>
              <label className="block">
                <span className="t-label mb-1 block">Objective</span>
                <Input
                  value={mission.objective}
                  onChange={(e) => updateMission({ objective: e.target.value })}
                />
              </label>
            </div>

            <div>
              <span className="t-label mb-2 block">Profile</span>
              <div className="grid gap-2 sm:grid-cols-2">
                {MISSION_PROFILES.map((profile) => {
                  const selected =
                    mission.missionType === profile.id &&
                    mission.targetAltitudeKm === profile.altitude_km;
                  return (
                    <button
                      key={`${profile.id}-${profile.altitude_km}`}
                      onClick={() =>
                        updateMission({
                          missionType: profile.id,
                          targetAltitudeKm: profile.altitude_km,
                          guidanceMode: profile.guidance,
                        })
                      }
                      className={cn(
                        'rounded-instrument border p-3 text-left transition-colors duration-quick focus-ring',
                        selected
                          ? 'border-signal-flame/50 bg-signal-flame/8'
                          : 'border-ink-800 bg-ink-900 hover:border-ink-600',
                      )}
                    >
                      <div className="flex items-baseline justify-between gap-2">
                        <span className="text-sm text-ink-100">{profile.label}</span>
                        <span className="font-mono text-micro text-ink-500">
                          {profile.altitude_km} km
                        </span>
                      </div>
                      <p className="mt-1 text-tiny leading-relaxed text-ink-500">
                        {profile.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="t-label mb-1 block">Guidance program</span>
                <Select
                  value={mission.guidanceMode}
                  onChange={(e) =>
                    updateMission({ guidanceMode: e.target.value as typeof mission.guidanceMode })
                  }
                  options={[
                    { value: 'vertical', label: 'Vertical — straight up, no pitchover' },
                    { value: 'pitch_program', label: 'Pitch program — scheduled by altitude' },
                    { value: 'gravity_turn', label: 'Gravity turn — kick, then let gravity steer' },
                  ]}
                />
              </label>
              <label className="block">
                <span className="t-label mb-1 block">Launch azimuth</span>
                <Input
                  type="number"
                  value={mission.launchAzimuthDeg}
                  suffix="°"
                  onChange={(e) =>
                    updateMission({ launchAzimuthDeg: Number(e.target.value) || 90 })
                  }
                />
                <span className="mt-1 block text-tiny text-ink-600">
                  90° is due east, which collects the full rotation bonus.
                </span>
              </label>
            </div>
          </Panel>

          {/* ── Pre-flight ────────────────────────────────────── */}
          <SectionRule
            label="Pre-flight"
            aside={
              <span className="font-mono text-micro text-ink-600">
                {checks.length - blocking.length}/{checks.length} clear
              </span>
            }
          />

          <Panel flush className="divide-y divide-[color:var(--rule-faint)]">
            {checks.map((check) => (
              <div key={check.id} className="flex items-start gap-3 px-4 py-2.5">
                <StatusDot tone={check.pass ? 'nominal' : 'caution'} className="mt-1.5 shrink-0" />
                <div className="min-w-0 flex-1">
                  <p className="text-xs text-ink-200">{check.label}</p>
                  <p className="mt-0.5 font-mono text-[0.65rem] leading-relaxed text-ink-500">
                    {check.detail}
                  </p>
                </div>
              </div>
            ))}
          </Panel>
        </div>

        {/* ── Right rail ────────────────────────────────────── */}
        <aside className="space-y-4">
          <WeatherPanel weather={weather} loading={weatherLoading} onRefresh={refreshWeather} />

          <Panel className="space-y-3">
            <h2 className="t-label">Commit</h2>

            {blocking.length > 0 ? (
              <p className="text-xs leading-relaxed text-signal-caution">
                {blocking.length} check{blocking.length === 1 ? '' : 's'} did not pass. You can
                fly anyway — watching it fail, and reading exactly why, is usually more useful
                than fixing it blind.
              </p>
            ) : (
              <p className="text-xs leading-relaxed text-signal-nominal-bright">
                Everything checks out. This should fly.
              </p>
            )}

            <Button size="lg" className="w-full" onClick={launch} loading={launching}>
              {launching ? 'Flying…' : 'Launch'}
            </Button>

            <p className="text-tiny leading-relaxed text-ink-600">
              The flight runs on the server: RK4 integration against the US Standard
              Atmosphere, corrected for the conditions above. A typical ascent takes under a
              second.
            </p>
          </Panel>

          <Panel className="space-y-2">
            <h2 className="t-label">Vehicle</h2>
            <dl className="space-y-1.5">
              <Readout inline label="Launch mass" value={formatMass(analysis.totalWetMass_kg)} />
              <Readout
                inline
                label="Liftoff TWR"
                value={analysis.liftoffTWR.toFixed(2)}
                tone={analysis.liftoffTWR < 1 ? 'critical' : 'neutral'}
              />
              <Readout
                inline
                label="Ideal Δv"
                value={analysis.totalDeltaV_ms.toFixed(0)}
                unit="m/s"
              />
              <Readout
                inline
                label="Static margin"
                value={analysis.stabilityWet.stabilityMargin_cal.toFixed(2)}
                unit="cal"
                tone={analysis.stabilityWet.stabilityMargin_cal < 1 ? 'caution' : 'neutral'}
              />
              <Readout inline label="Stages" value={analysis.stages.length} />
            </dl>
            <Link
              to="/builder"
              className="mt-2 block font-condensed text-micro uppercase tracking-instrument text-signal-flame hover:text-signal-flame-bright"
            >
              ← Back to the builder
            </Link>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

/**
 * Roughly what a mission costs in Δv.
 *
 * A pre-flight estimate, not a trajectory: enough to tell someone their vehicle
 * is 3 km/s short before they watch it be 3 km/s short. The orbital case adds a
 * flat 1,800 m/s for gravity, drag and steering losses, which is the middle of
 * the real range for a launch to low Earth orbit.
 */
function estimateRequiredDeltaV(targetAltitudeKm: number, missionType: string): number {
  if (missionType === 'suborbital') {
    // Ballistic: v = sqrt(2 g h), plus a modest loss allowance.
    return Math.sqrt(2 * 9.80665 * targetAltitudeKm * 1000) * 1.25;
  }
  const R_EARTH_M = 6_371_000;
  const MU = 3.986e14;
  const radius = R_EARTH_M + targetAltitudeKm * 1000;
  const circularSpeed = Math.sqrt(MU / radius);
  return circularSpeed + 1800;
}
