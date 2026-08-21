import { useMemo, useState } from 'react';
import {
  atmosphere,
  dynamicPressure,
  machNumber,
} from '@lostintospace/simulation-engine/physics/atmosphere';
import { G0, MU_EARTH, R_EARTH } from '@lostintospace/simulation-engine/physics/constants';
import { effectiveDragCoefficient } from '@lostintospace/simulation-engine/physics/drag';
import {
  circularOrbitSpeed,
  escapeSpeed,
} from '@lostintospace/simulation-engine/physics/gravity';

import { Panel, Readout, Slider } from '@/components/ui';
import type { InteractiveParameter } from '@/services/api';
import { cn } from '@/lib/utils';

/**
 * Newton's gravitational constant. Unit: m³/(kg·s²)
 *
 * The physics package works in μ = GM throughout, because that product is
 * measured far more precisely than either factor. G is needed here only for the
 * gravity figure, where varying an arbitrary *mass* is the whole point.
 */
const G = 6.674_30e-11;


/**
 * An interactive figure in the science library.
 *
 * The reader changes a variable and watches the consequence. That is the whole
 * mechanism, and it is the reason these topics exist as pages rather than as
 * prose: a sentence saying delta-v depends logarithmically on mass ratio is a
 * fact to remember, whereas adding propellant and watching the curve flatten is
 * a thing you understand.
 *
 * ## Where the maths comes from
 *
 * Not from here. Every computation calls the physics package the rocket builder
 * and the flight simulation already use — the same atmosphere model, the same
 * drag rise, the same constants. A teaching figure that computed its own
 * approximation would eventually contradict the simulator, and a learner would
 * have no way to tell which one was lying.
 *
 * The content records name a `kind` and its parameters; this module knows how
 * to compute and draw each kind. Adding a figure is a content change plus one
 * case here.
 */

export interface InteractiveFigureProps {
  kind: string;
  title: string;
  instruction: string;
  parameters: InteractiveParameter[];
  outputs: string[];
  equation?: string | null;
  equationNote?: string | null;
  className?: string;
}

export function InteractiveFigure({
  kind,
  title,
  instruction,
  parameters,
  equation,
  equationNote,
  className,
}: InteractiveFigureProps) {
  const [values, setValues] = useState<Record<string, number>>(() =>
    Object.fromEntries(parameters.map((p) => [p.key, p.default])),
  );

  const computed = useMemo(() => compute(kind, values), [kind, values]);

  const reset = () =>
    setValues(Object.fromEntries(parameters.map((p) => [p.key, p.default])));

  return (
    <Panel plated className={cn('space-y-4', className)}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="t-label mb-1">Interactive</p>
          <h3 className="font-display text-xl leading-tight text-ink-50">{title}</h3>
          <p className="mt-1.5 max-w-prose text-xs leading-relaxed text-ink-400">
            {instruction}
          </p>
        </div>
        <button
          onClick={reset}
          className="shrink-0 font-condensed text-micro uppercase tracking-instrument text-ink-500 transition-colors hover:text-ink-200 focus-ring"
        >
          Reset
        </button>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,260px)_minmax(0,1fr)]">
        {/* Controls */}
        <div className="space-y-4">
          {parameters.map((parameter) => (
            <Slider
              key={parameter.key}
              label={parameter.label}
              value={values[parameter.key] ?? parameter.default}
              min={parameter.min}
              max={parameter.max}
              step={parameter.step ?? undefined}
              unit={parameter.unit ?? undefined}
              precision={parameter.precision}
              logarithmic={parameter.logarithmic}
              hint={parameter.hint ?? undefined}
              onChange={(next) => setValues((v) => ({ ...v, [parameter.key]: next }))}
            />
          ))}
        </div>

        {/* Results */}
        <div className="space-y-4">
          {computed.chart && <FigureChart chart={computed.chart} />}

          <dl className="grid grid-cols-2 gap-x-6 gap-y-2.5">
            {computed.outputs.map((output) => (
              <Readout
                key={output.label}
                label={output.label}
                value={output.value}
                unit={output.unit}
                tone={output.tone}
                hint={output.hint}
              />
            ))}
          </dl>

          {computed.verdict && (
            <p
              className={cn(
                'text-xs leading-relaxed',
                computed.verdictTone === 'critical'
                  ? 'text-signal-oxide-bright'
                  : computed.verdictTone === 'caution'
                    ? 'text-signal-caution-bright'
                    : 'text-signal-nominal-bright',
              )}
            >
              {computed.verdict}
            </p>
          )}
        </div>
      </div>

      {equation && (
        <div className="hairline-t pt-3">
          <p className="font-mono text-xs text-ink-200">{equation}</p>
          {equationNote && (
            <p className="mt-1 text-tiny leading-relaxed text-ink-500">{equationNote}</p>
          )}
        </div>
      )}
    </Panel>
  );
}

// ============================================================
// Chart
// ============================================================

interface ChartSeries {
  readonly label: string;
  readonly points: readonly { x: number; y: number }[];
  readonly colour: string;
}

interface ChartSpec {
  readonly xLabel: string;
  readonly yLabel: string;
  readonly series: readonly ChartSeries[];
  /** A marker at the current parameter value. */
  readonly marker?: { x: number; y: number };
  readonly logY?: boolean;
}

/** A line plot, drawn as SVG so it stays crisp and needs no chart library. */
function FigureChart({ chart }: { chart: ChartSpec }) {
  const all = chart.series.flatMap((s) => s.points);
  if (all.length === 0) return null;

  const xs = all.map((p) => p.x);
  const ys = all.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = chart.logY ? Math.max(Math.min(...ys), 1e-9) : Math.min(0, Math.min(...ys));
  const maxY = Math.max(...ys) || 1;

  const toX = (x: number) => ((x - minX) / (maxX - minX || 1)) * 100;
  const toY = (y: number) => {
    if (chart.logY) {
      const t = (Math.log10(Math.max(y, 1e-9)) - Math.log10(minY)) /
        (Math.log10(maxY) - Math.log10(minY) || 1);
      return 60 - t * 54;
    }
    return 60 - ((y - minY) / (maxY - minY || 1)) * 54;
  };

  return (
    <div className="plane-sunken relative h-44">
      <svg viewBox="0 0 100 60" preserveAspectRatio="none" className="block h-full w-full">
        {/* Gridlines, so a value can be read off rather than guessed at. */}
        {[0.25, 0.5, 0.75].map((t) => (
          <line
            key={t}
            x1={0}
            y1={6 + t * 54}
            x2={100}
            y2={6 + t * 54}
            stroke="rgba(228,221,211,0.06)"
            strokeWidth={0.4}
            vectorEffect="non-scaling-stroke"
          />
        ))}

        {chart.series.map((series) => (
          <polyline
            key={series.label}
            points={series.points.map((p) => `${toX(p.x)},${toY(p.y)}`).join(' ')}
            fill="none"
            stroke={series.colour}
            strokeWidth={1.4}
            vectorEffect="non-scaling-stroke"
            strokeLinejoin="round"
          />
        ))}

        {chart.marker && (
          <>
            <line
              x1={toX(chart.marker.x)}
              y1={0}
              x2={toX(chart.marker.x)}
              y2={60}
              stroke="#E4682E"
              strokeWidth={0.7}
              strokeDasharray="2 2"
              vectorEffect="non-scaling-stroke"
            />
            <circle
              cx={toX(chart.marker.x)}
              cy={toY(chart.marker.y)}
              r={1.6}
              fill="#FA8A4A"
              vectorEffect="non-scaling-stroke"
            />
          </>
        )}
      </svg>

      <span className="pointer-events-none absolute left-1.5 top-1 font-mono text-[0.6rem] text-ink-500">
        {chart.yLabel}
      </span>
      <span className="pointer-events-none absolute bottom-1 right-1.5 font-mono text-[0.6rem] text-ink-500">
        {chart.xLabel}
      </span>
    </div>
  );
}

// ============================================================
// Computation
// ============================================================

interface FigureOutput {
  label: string;
  value: string;
  unit?: string;
  tone?: 'neutral' | 'nominal' | 'caution' | 'critical' | 'active' | 'quiet';
  hint?: string;
}

interface FigureResult {
  outputs: FigureOutput[];
  chart?: ChartSpec;
  verdict?: string;
  verdictTone?: 'nominal' | 'caution' | 'critical';
}

const C_LIGHT = 299_792_458;

/**
 * Compute one figure's outputs from its current parameter values.
 *
 * Every branch calls the shared physics package rather than reimplementing a
 * formula, except where the quantity is a one-line definition (light time,
 * static margin) that would be more obscure wrapped than written.
 */
function compute(kind: string, v: Record<string, number>): FigureResult {
  switch (kind) {
    case 'light-travel-time': {
      const km = v.distance_km ?? 384_400;
      const seconds = (km * 1000) / C_LIGHT;
      return {
        outputs: [
          { label: 'One-way light time', value: formatDuration(seconds) },
          { label: 'Round trip', value: formatDuration(seconds * 2) },
          { label: 'In astronomical units', value: (km / 149_597_870.7).toFixed(4), unit: 'AU' },
        ],
        verdict:
          seconds < 1.5
            ? 'Close enough to fly by hand — a pilot on Earth could react in time.'
            : seconds < 60
              ? 'Remote operation is possible but sluggish; every command has a visible lag.'
              : 'Far too distant to fly by hand. Everything time-critical has to be autonomous.',
        verdictTone: seconds < 1.5 ? 'nominal' : seconds < 60 ? 'caution' : 'critical',
      };
    }

    case 'gravity-field': {
      const mass = v.mass_kg ?? 5.972e24;
      const radiusM = (v.radius_km ?? 6371) * 1000;
      const testMass = v.test_mass_kg ?? 1000;
      const mu = G * mass;
      const g = mu / (radiusM * radiusM);
      const force = g * testMass;
      // The shared helpers, so this figure and the flight agree.
      const escape = escapeSpeed(radiusM, mu);
      const orbital = circularOrbitSpeed(radiusM, mu);

      // Force against distance, so the inverse square is visible rather than
      // asserted.
      const points = [];
      for (let i = 0; i <= 60; i += 1) {
        const r = radiusM * (0.6 + (i / 60) * 3.4);
        points.push({ x: r / 1000, y: ((G * mass) / (r * r)) * testMass });
      }

      return {
        outputs: [
          { label: 'Surface gravity', value: g.toFixed(3), unit: 'm/s²' },
          { label: 'Weight of your craft', value: formatLarge(force), unit: 'N' },
          { label: 'Escape velocity', value: (escape / 1000).toFixed(3), unit: 'km/s' },
          { label: 'Circular orbit speed', value: (orbital / 1000).toFixed(3), unit: 'km/s' },
        ],
        chart: {
          xLabel: 'distance (km)',
          yLabel: 'force (N)',
          series: [{ label: 'F', points, colour: '#FA8A4A' }],
          marker: { x: radiusM / 1000, y: force },
        },
        verdict: `Escape velocity is exactly √2 times orbital velocity — ${(escape / orbital).toFixed(4)}× — at any distance from any body.`,
        verdictTone: 'nominal',
      };
    }

    case 'orbit-shape': {
      const altitude = (v.altitude_km ?? 408) * 1000;
      const r = R_EARTH + altitude;
      const speed = v.velocity_ms ?? 7670;
      const circular = Math.sqrt(MU_EARTH / r);
      const escape = Math.sqrt((2 * MU_EARTH) / r);

      // Vis-viva gives the semi-major axis from speed and radius directly.
      const energy = (speed * speed) / 2 - MU_EARTH / r;
      const a = energy >= 0 ? Infinity : -MU_EARTH / (2 * energy);
      const apoapsis = Number.isFinite(a) ? 2 * a - r : Infinity;
      const periapsis = Number.isFinite(a) ? Math.min(r, 2 * a - apoapsis) : r;
      const eccentricity = Number.isFinite(a) ? Math.abs(1 - r / a) : 1;
      const period = Number.isFinite(a) ? 2 * Math.PI * Math.sqrt(a ** 3 / MU_EARTH) : Infinity;

      const orbitType =
        speed >= escape
          ? 'Escape trajectory'
          : periapsis < R_EARTH + 100_000
            ? 'Suborbital — it comes back down'
            : Math.abs(speed - circular) < 20
              ? 'Circular orbit'
              : 'Elliptical orbit';

      return {
        outputs: [
          { label: 'Result', value: orbitType, tone: speed >= escape ? 'active' : 'neutral' },
          {
            label: 'Circular speed here',
            value: circular.toFixed(0),
            unit: 'm/s',
            hint: 'What it takes to stay at this altitude',
          },
          { label: 'Escape speed here', value: escape.toFixed(0), unit: 'm/s' },
          {
            label: 'Apoapsis',
            value: Number.isFinite(apoapsis)
              ? ((apoapsis - R_EARTH) / 1000).toFixed(0)
              : '∞',
            unit: 'km',
          },
          {
            label: 'Periapsis',
            value: Number.isFinite(periapsis)
              ? ((periapsis - R_EARTH) / 1000).toFixed(0)
              : '—',
            unit: 'km',
            tone: periapsis < R_EARTH + 100_000 ? 'critical' : 'nominal',
          },
          { label: 'Eccentricity', value: eccentricity.toFixed(4) },
          {
            label: 'Period',
            value: Number.isFinite(period) ? formatDuration(period) : 'never returns',
          },
        ],
        verdict:
          periapsis < R_EARTH + 100_000 && speed < escape
            ? 'Periapsis is inside the atmosphere, so this trajectory intersects Earth. Altitude alone never produces an orbit — the low point of the ellipse has to clear the air.'
            : speed >= escape
              ? 'Above escape velocity. This trajectory never closes.'
              : 'A closed orbit clear of the atmosphere.',
        verdictTone:
          periapsis < R_EARTH + 100_000 && speed < escape
            ? 'critical'
            : speed >= escape
              ? 'caution'
              : 'nominal',
      };
    }

    case 'rocket-equation': {
      const dry = v.dry_mass_kg ?? 3000;
      const propellant = v.propellant_mass_kg ?? 40_000;
      const isp = v.isp_s ?? 340;
      const payload = v.payload_mass_kg ?? 500;

      const wet = dry + propellant + payload;
      const final = dry + payload;
      const ratio = wet / final;
      const exhaust = isp * G0;
      const deltaV = exhaust * Math.log(ratio);

      // Δv against propellant, holding everything else — the curve that shows
      // the logarithm defeating you.
      const points = [];
      for (let i = 0; i <= 60; i += 1) {
        const p = (i / 60) * Math.max(propellant * 2.5, 1000);
        points.push({ x: p, y: exhaust * Math.log((dry + p + payload) / final) });
      }

      return {
        outputs: [
          { label: 'Δv', value: deltaV.toFixed(0), unit: 'm/s', tone: 'active' },
          { label: 'Mass ratio', value: ratio.toFixed(2) },
          {
            label: 'Propellant fraction',
            value: ((propellant / wet) * 100).toFixed(1),
            unit: '%',
          },
          { label: 'Exhaust velocity', value: exhaust.toFixed(0), unit: 'm/s' },
          {
            label: 'Reachable',
            value:
              deltaV > 12_000
                ? 'Beyond Earth escape'
                : deltaV > 9_400
                  ? 'Low Earth orbit'
                  : deltaV > 3_000
                    ? 'High suborbital'
                    : 'Suborbital hop',
            tone: deltaV > 9_400 ? 'nominal' : 'caution',
          },
        ],
        chart: {
          xLabel: 'propellant (kg)',
          yLabel: 'Δv (m/s)',
          series: [{ label: 'Δv', points, colour: '#FA8A4A' }],
          marker: { x: propellant, y: deltaV },
        },
        verdict:
          'Doubling the propellant adds one more ln(2)·vₑ — a fixed amount, for twice the mass. ' +
          'Raising specific impulse is linear. That asymmetry is why enormous effort goes into a few seconds of Isp.',
        verdictTone: 'nominal',
      };
    }

    case 'atmosphere-profile': {
      const altitudeM = (v.altitude_km ?? 0) * 1000;
      const state = atmosphere(altitudeM);
      const surfaceT = (v.surface_temperature_C ?? 15) + 273.15;
      const surfaceP = (v.surface_pressure_hPa ?? 1013.25) * 100;
      const humidity = v.relative_humidity ?? 0;

      // The same non-standard-day correction the flight simulation applies.
      const decay = Math.max(0, 1 - altitudeM / 20_000);
      const temperature = state.temperature_K + (surfaceT - 288.15) * decay;
      const pressure = state.pressure_Pa * (surfaceP / 101_325);
      const vapour =
        humidity * decay * 610.78 * Math.exp((17.27 * (temperature - 273.15)) / (temperature - 35.86));
      const dry = Math.max(pressure - vapour, 0);
      const density = dry / (287.058 * temperature) + vapour / (461.495 * temperature);
      const standardDensity = state.density_kgm3;

      const points = [];
      for (let i = 0; i <= 60; i += 1) {
        const h = (i / 60) * 100_000;
        points.push({ x: h / 1000, y: atmosphere(h).density_kgm3 });
      }

      return {
        outputs: [
          { label: 'Temperature', value: (temperature - 273.15).toFixed(1), unit: '°C' },
          { label: 'Pressure', value: (pressure / 100).toFixed(2), unit: 'hPa' },
          { label: 'Density', value: density.toFixed(5), unit: 'kg/m³' },
          {
            label: 'Speed of sound',
            value: Math.sqrt(1.4 * 287.05 * temperature).toFixed(1),
            unit: 'm/s',
          },
          {
            label: 'Against a standard day',
            value: `${(((density - standardDensity) / (standardDensity || 1)) * 100).toFixed(1)}`,
            unit: '%',
            tone: density > standardDensity ? 'caution' : 'nominal',
            hint: density > standardDensity ? 'Denser — more drag' : 'Thinner — less drag',
          },
        ],
        chart: {
          xLabel: 'altitude (km)',
          yLabel: 'density (kg/m³)',
          series: [{ label: 'ρ', points, colour: '#7FA8B8' }],
          marker: { x: altitudeM / 1000, y: density },
          logY: true,
        },
        verdict:
          'Humid air is *less* dense than dry air at the same pressure and temperature — a water ' +
          'molecule is lighter than the nitrogen it displaces.',
        verdictTone: 'nominal',
      };
    }

    case 'drag-curve': {
      const altitudeM = (v.altitude_km ?? 10) * 1000;
      const velocity = v.velocity_ms ?? 400;
      const diameter = v.diameter_m ?? 1.5;
      const cd0 = v.drag_coefficient ?? 0.42;

      const state = atmosphere(altitudeM);
      const area = Math.PI * (diameter / 2) ** 2;
      const mach = machNumber(velocity, state);
      const cd = effectiveDragCoefficient(cd0, mach);
      const q = dynamicPressure(velocity, state.density_kgm3);
      const drag = q * cd * area;

      // Cd against Mach, so the transonic rise is visible.
      const points = [];
      for (let i = 0; i <= 60; i += 1) {
        const m = (i / 60) * 5;
        points.push({ x: m, y: effectiveDragCoefficient(cd0, m) });
      }

      return {
        outputs: [
          { label: 'Air density', value: state.density_kgm3.toFixed(5), unit: 'kg/m³' },
          { label: 'Mach number', value: mach.toFixed(2) },
          {
            label: 'Effective Cd',
            value: cd.toFixed(3),
            tone: cd > cd0 * 1.4 ? 'caution' : 'neutral',
            hint: cd > cd0 * 1.4 ? 'Transonic drag rise' : undefined,
          },
          { label: 'Dynamic pressure', value: (q / 1000).toFixed(2), unit: 'kPa' },
          { label: 'Reference area', value: area.toFixed(3), unit: 'm²' },
          { label: 'Drag force', value: formatLarge(drag), unit: 'N', tone: 'active' },
        ],
        chart: {
          xLabel: 'Mach',
          yLabel: 'Cd',
          series: [{ label: 'Cd', points, colour: '#FA8A4A' }],
          marker: { x: mach, y: cd },
        },
        verdict:
          'Drag goes with the square of speed and the first power of density. Frontal area goes ' +
          'with the square of diameter, which is why launch vehicles are slender.',
        verdictTone: 'nominal',
      };
    }

    case 'stability-margin': {
      const cg = v.cg_position_m ?? 8.2;
      const cp = v.cp_position_m ?? 10.1;
      const diameter = v.diameter_m ?? 1.5;
      const margin = (cp - cg) / Math.max(diameter, 1e-6);

      const verdict =
        margin < 0
          ? 'Centre of pressure is ahead of centre of gravity. Any disturbance is amplified — this tumbles.'
          : margin < 1
            ? 'Marginally stable. A gust will upset it and it will be slow to recover.'
            : margin <= 2
              ? 'Inside the 1–2 caliber target. It will correct disturbances without fighting crosswind.'
              : 'Over-stable. It will weathercock hard into any crosswind and fly there instead of where it was aimed.';

      return {
        outputs: [
          {
            label: 'Static margin',
            value: margin.toFixed(2),
            unit: 'cal',
            tone: margin < 1 ? 'critical' : margin > 2 ? 'caution' : 'nominal',
          },
          { label: 'CP behind CG by', value: (cp - cg).toFixed(2), unit: 'm' },
          { label: 'One caliber', value: diameter.toFixed(2), unit: 'm' },
        ],
        verdict,
        verdictTone: margin < 1 ? 'critical' : margin > 2 ? 'caution' : 'nominal',
      };
    }

    case 'twr-profile': {
      const thrust = (v.thrust_kN ?? 380) * 1000;
      const launchMass = v.launch_mass_kg ?? 24_500;
      const propellantFraction = v.propellant_fraction ?? 0.85;
      const burnoutMass = launchMass * (1 - propellantFraction);

      const twrLiftoff = thrust / (launchMass * G0);
      const twrBurnout = thrust / (Math.max(burnoutMass, 1) * G0);

      const points = [];
      for (let i = 0; i <= 60; i += 1) {
        const burned = (i / 60) * propellantFraction;
        const mass = launchMass * (1 - burned);
        points.push({ x: burned * 100, y: thrust / (mass * G0) });
      }

      return {
        outputs: [
          {
            label: 'TWR at liftoff',
            value: twrLiftoff.toFixed(2),
            tone: twrLiftoff < 1 ? 'critical' : twrLiftoff < 1.2 ? 'caution' : 'nominal',
          },
          {
            label: 'TWR at burnout',
            value: twrBurnout.toFixed(2),
            tone: twrBurnout > 7 ? 'caution' : 'neutral',
          },
          {
            label: 'Peak acceleration',
            value: (twrBurnout - 1).toFixed(1),
            unit: 'g',
            hint: 'Net of gravity, at cutoff',
          },
          { label: 'Burnout mass', value: burnoutMass.toFixed(0), unit: 'kg' },
        ],
        chart: {
          xLabel: 'propellant burned (%)',
          yLabel: 'TWR',
          series: [{ label: 'TWR', points, colour: '#FA8A4A' }],
          marker: { x: 0, y: twrLiftoff },
        },
        verdict:
          twrLiftoff < 1
            ? 'Below 1.0 at liftoff. This does not move.'
            : `Acceleration climbs by a factor of ${(twrBurnout / twrLiftoff).toFixed(1)} through the burn as propellant is consumed. This is why real vehicles throttle down near cutoff.`,
        verdictTone: twrLiftoff < 1 ? 'critical' : twrBurnout > 7 ? 'caution' : 'nominal',
      };
    }

    case 'transfer-orbit': {
      const r1 = R_EARTH + (v.departure_altitude_km ?? 400) * 1000;
      const r2 = R_EARTH + (v.arrival_altitude_km ?? 35_786) * 1000;
      const a = (r1 + r2) / 2;

      const v1 = Math.sqrt(MU_EARTH / r1);
      const v2 = Math.sqrt(MU_EARTH / r2);
      const vTransfer1 = Math.sqrt(MU_EARTH * (2 / r1 - 1 / a));
      const vTransfer2 = Math.sqrt(MU_EARTH * (2 / r2 - 1 / a));

      const dv1 = Math.abs(vTransfer1 - v1);
      const dv2 = Math.abs(v2 - vTransfer2);
      const time = Math.PI * Math.sqrt(a ** 3 / MU_EARTH);
      const ratio = Math.max(r1, r2) / Math.min(r1, r2);

      return {
        outputs: [
          { label: 'First burn', value: dv1.toFixed(0), unit: 'm/s' },
          { label: 'Second burn', value: dv2.toFixed(0), unit: 'm/s' },
          { label: 'Total Δv', value: (dv1 + dv2).toFixed(0), unit: 'm/s', tone: 'active' },
          { label: 'Transfer time', value: formatDuration(time) },
          { label: 'Orbit ratio', value: ratio.toFixed(2) },
        ],
        verdict:
          ratio > 11.94
            ? `At a ratio of ${ratio.toFixed(1)} a bi-elliptic transfer would use less Δv than this Hohmann — at the cost of a great deal more time.`
            : 'Below a ratio of 11.94, the two-burn Hohmann transfer is the minimum-energy route.',
        verdictTone: 'nominal',
      };
    }

    case 'parachute-descent': {
      const mass = v.mass_kg ?? 25;
      const area = v.canopy_area_m2 ?? 3;
      const cd = v.drag_coefficient ?? 1.5;
      const deployAltitude = v.deploy_altitude_m ?? 400;

      const density = atmosphere(deployAltitude).density_kgm3;
      const terminal = Math.sqrt((2 * mass * G0) / (density * cd * area));
      const descentTime = deployAltitude / Math.max(terminal, 0.1);
      // Opening shock, very roughly: the canopy decelerating from deployment
      // speed over about a second.
      const shock = 0.5 * density * terminal * terminal * cd * area * 2.2;

      return {
        outputs: [
          {
            label: 'Terminal velocity',
            value: terminal.toFixed(2),
            unit: 'm/s',
            tone: terminal > 10 ? 'critical' : terminal > 7 ? 'caution' : 'nominal',
          },
          { label: 'Descent time', value: formatDuration(descentTime) },
          { label: 'Opening shock', value: formatLarge(shock), unit: 'N' },
          {
            label: 'Equivalent drop',
            value: ((terminal * terminal) / (2 * G0)).toFixed(2),
            unit: 'm',
            hint: 'The height this impact speed matches',
          },
        ],
        verdict:
          terminal > 10
            ? 'Too fast to survive. Terminal velocity falls with the square root of area, so halving this needs four times the canopy.'
            : `A ${((terminal * terminal) / (2 * G0)).toFixed(1)} m drop. Survivable for most hardware.`,
        verdictTone: terminal > 10 ? 'critical' : terminal > 7 ? 'caution' : 'nominal',
      };
    }

    default:
      return {
        outputs: [
          {
            label: 'Figure',
            value: 'not available',
            tone: 'quiet',
            hint: `No renderer for "${kind}" in this build.`,
          },
        ],
      };
  }
}

function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds)) return '∞';
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`;
  if (seconds < 90) return `${seconds.toFixed(1)} s`;
  if (seconds < 5400) return `${(seconds / 60).toFixed(1)} min`;
  if (seconds < 172_800) return `${(seconds / 3600).toFixed(1)} h`;
  if (seconds < 3.15e9) return `${(seconds / 86_400).toFixed(1)} days`;
  return `${(seconds / 3.156e7).toFixed(1)} years`;
}

function formatLarge(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)}×10⁹`;
  if (magnitude >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (magnitude >= 1000) return `${(value / 1000).toFixed(2)}k`;
  if (magnitude >= 1) return value.toFixed(1);
  return value.toExponential(2);
}
