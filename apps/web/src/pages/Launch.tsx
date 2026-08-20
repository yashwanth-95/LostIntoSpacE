import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { createStockRegistry } from '@lostintospace/simulation-engine/core/catalog';
import { analyzeRocket } from '@lostintospace/simulation-engine/core/builder';
import { vehicleFromAnalysis } from '@lostintospace/simulation-engine/core/vehicle';

import { Badge, Button, Card, EmptyState, Input, Select } from '@/components/ui';
import { LAUNCH_SITES, MISSION_PROFILES, buildSimConfig } from '@/lib/simConfig';
import { simulation } from '@/services/api';
import { useMissionStore } from '@/stores/missionStore';
import { cn, formatMass } from '@/lib/utils';

/**
 * Launch configuration and pre-flight.
 *
 * The checks below are computed from the design's own analysis, not from a
 * successful simulation — the point is to tell someone their rocket cannot fly
 * *before* they watch it not fly. A failing check does not block launch,
 * though: flying a rocket you have been told will fail, and seeing exactly how,
 * is the most useful thing this platform does.
 */

export default function Launch() {
  const navigate = useNavigate();
  const design = useMissionStore((s) => s.design);
  const mission = useMissionStore((s) => s.mission);
  const updateMission = useMissionStore((s) => s.updateMission);
  const setResult = useMissionStore((s) => s.setResult);

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

  const checks = useMemo(() => {
    if (!analysis) return [];
    const targetDeltaV = estimateRequiredDeltaV(mission.targetAltitudeKm, mission.missionType);
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
        id: 'deltav',
        label: 'Δv budget covers the target',
        pass: analysis.totalDeltaV_ms >= targetDeltaV,
        detail: `${analysis.totalDeltaV_ms.toFixed(0)} m/s available, about ${targetDeltaV.toFixed(
          0,
        )} m/s needed`,
      },
      {
        id: 'stability',
        label: 'Statically stable when full',
        pass: analysis.stabilityWet.stabilityMargin_cal >= 0.5,
        detail: `${analysis.stabilityWet.stabilityMargin_cal.toFixed(2)} calibers`,
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
  }, [analysis, mission.targetAltitudeKm, mission.missionType]);

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
        windSpeedMs: mission.windSpeedMs,
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
          description="Build a rocket first, or start from one of the designs in Rocket Lab."
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
    <div className="mx-auto max-w-6xl px-6 py-8">
      <header className="mb-6">
        <h1 className="font-display text-2xl font-semibold text-space-100 mb-1">Launch</h1>
        <p className="text-sm text-space-400">
          Flying <span className="text-space-200">{design.name}</span> ·{' '}
          {formatMass(analysis.totalWetMass_kg)} on the pad
        </p>
      </header>

      <div className="grid gap-5 lg:grid-cols-[1fr_340px]">
        <div className="space-y-5">
          {/* Mission */}
          <Card className="space-y-4">
            <h2 className="font-display text-sm font-semibold text-space-200">Mission</h2>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">Mission name</span>
                <Input
                  value={mission.name}
                  onChange={(e) => updateMission({ name: e.target.value })}
                />
              </label>

              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">Objective</span>
                <Input
                  value={mission.objective}
                  onChange={(e) => updateMission({ objective: e.target.value })}
                />
              </label>
            </div>

            <div>
              <span className="text-2xs text-space-500 block mb-2">Profile</span>
              <div className="grid gap-2 sm:grid-cols-2">
                {MISSION_PROFILES.map((profile) => {
                  const active =
                    mission.targetAltitudeKm === profile.altitude_km &&
                    mission.missionType === profile.id;
                  return (
                    <button
                      key={`${profile.id}-${profile.altitude_km}`}
                      onClick={() =>
                        updateMission({
                          missionType: profile.id,
                          targetAltitudeKm: profile.altitude_km,
                          guidanceMode: profile.guidance,
                          objective: `Reach ${profile.altitude_km} km`,
                        })
                      }
                      className={cn(
                        'text-left p-3 rounded-md border transition-colors focus-ring',
                        active
                          ? 'bg-accent-cyan/10 border-accent-cyan/40'
                          : 'bg-space-800/40 border-space-700 hover:border-space-600',
                      )}
                      aria-pressed={active}
                    >
                      <div className="flex items-center justify-between gap-2 mb-1">
                        <span
                          className={cn(
                            'text-xs font-medium',
                            active ? 'text-accent-cyan' : 'text-space-200',
                          )}
                        >
                          {profile.label}
                        </span>
                        <span className="text-2xs font-mono text-space-500">
                          {profile.altitude_km} km
                        </span>
                      </div>
                      <p className="text-2xs text-space-500 leading-relaxed">
                        {profile.description}
                      </p>
                    </button>
                  );
                })}
              </div>
            </div>
          </Card>

          {/* Site and guidance */}
          <Card className="space-y-4">
            <h2 className="font-display text-sm font-semibold text-space-200">
              Launch site and guidance
            </h2>

            <div className="grid gap-4 sm:grid-cols-2">
              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">Launch site</span>
                <Select
                  value={mission.launchSite.name}
                  options={LAUNCH_SITES.map((site) => ({
                    value: site.name,
                    label: `${site.name} (${site.agency})`,
                  }))}
                  onChange={(e) => {
                    const site = LAUNCH_SITES.find((s) => s.name === e.target.value);
                    if (site) updateMission({ launchSite: site });
                  }}
                />
                <span className="text-2xs text-space-600 mt-1 block">
                  {mission.launchSite.latitude_deg.toFixed(2)}° lat ·{' '}
                  {mission.launchSite.altitude_m} m elevation
                </span>
              </label>

              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">Guidance program</span>
                <Select
                  value={mission.guidanceMode}
                  options={[
                    { value: 'vertical', label: 'Vertical — straight up' },
                    { value: 'pitch_program', label: 'Pitch program — scheduled by altitude' },
                    { value: 'gravity_turn', label: 'Gravity turn — follow the velocity vector' },
                  ]}
                  onChange={(e) =>
                    updateMission({
                      guidanceMode: e.target.value as typeof mission.guidanceMode,
                    })
                  }
                />
                <span className="text-2xs text-space-600 mt-1 block">
                  {mission.guidanceMode === 'vertical'
                    ? 'Never reaches orbit — orbit needs horizontal speed.'
                    : 'Pitches over to build the sideways speed an orbit needs.'}
                </span>
              </label>

              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">
                  Launch azimuth (° from north)
                </span>
                <Input
                  type="number"
                  min={0}
                  max={360}
                  value={mission.launchAzimuthDeg}
                  onChange={(e) =>
                    updateMission({ launchAzimuthDeg: Number(e.target.value) || 0 })
                  }
                />
              </label>

              <label className="block">
                <span className="text-2xs text-space-500 block mb-1">Surface wind (m/s)</span>
                <Input
                  type="number"
                  min={0}
                  max={40}
                  value={mission.windSpeedMs}
                  onChange={(e) => updateMission({ windSpeedMs: Number(e.target.value) || 0 })}
                />
              </label>
            </div>

            <p className="text-2xs text-space-600 leading-relaxed border-t border-space-800 pt-3">
              The engine does not model Earth's rotation, so an eastward equatorial launch does
              not receive the roughly 465 m/s a real one would. Latitude still sets the
              achievable inclination.
            </p>
          </Card>
        </div>

        {/* Pre-flight */}
        <aside className="space-y-4">
          <Card className="space-y-3">
            <h2 className="font-display text-sm font-semibold text-space-200">
              Pre-flight checks
            </h2>
            <ul className="space-y-2.5">
              {checks.map((check) => (
                <li key={check.id} className="flex gap-2.5">
                  <span
                    className={cn(
                      'mt-0.5 shrink-0 text-xs',
                      check.pass ? 'text-accent-emerald' : 'text-severity-critical',
                    )}
                    aria-hidden="true"
                  >
                    {check.pass ? '✓' : '✕'}
                  </span>
                  <div className="min-w-0">
                    <p className="text-2xs text-space-200 leading-snug">{check.label}</p>
                    <p className="text-2xs text-space-500 leading-snug">{check.detail}</p>
                  </div>
                </li>
              ))}
            </ul>

            {blocking.length > 0 && (
              <p className="text-2xs text-severity-warning leading-relaxed border-t border-space-800 pt-3">
                {blocking.length} check{blocking.length === 1 ? '' : 's'} failed. You can still
                launch — watching it fail is often the clearest way to see why.
              </p>
            )}
          </Card>

          <Card className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-2xs text-space-500">Readiness</span>
              <Badge variant={blocking.length === 0 ? 'emerald' : 'warning'}>
                {blocking.length === 0 ? 'GO' : `${blocking.length} WARNING`}
              </Badge>
            </div>

            <Button
              size="lg"
              className="w-full"
              loading={launching}
              onClick={launch}
              variant={blocking.length === 0 ? 'primary' : 'secondary'}
            >
              {launching ? 'Running simulation…' : 'Launch'}
            </Button>

            {error && <p className="text-2xs text-severity-fatal leading-relaxed">{error}</p>}

            <p className="text-2xs text-space-600 leading-relaxed">
              The flight is computed by the Python physics engine on the server, then replayed
              in Mission Control.
            </p>
          </Card>

          <Link to="/builder" className="block text-2xs text-accent-cyan hover:underline">
            ← Back to the Builder
          </Link>
        </aside>
      </div>
    </div>
  );
}

/**
 * Roughly how much delta-v the target needs, for the pre-flight budget check.
 *
 * Orbital speed plus a conventional allowance for gravity and drag losses
 * (~1.5–2 km/s for an Earth ascent). This is a *check*, not a simulation: the
 * engine computes the real losses during flight, and this only has to be good
 * enough to warn someone before they burn a launch on an impossible target.
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
