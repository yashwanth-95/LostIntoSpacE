import { useMemo } from 'react';
import type { ThrustCurvePoint } from '@lostintospace/simulation-engine/core/component-types';

import { cn } from '@/lib/utils';

/**
 * A motor's thrust against time.
 *
 * The single most informative picture of a solid motor, and the reason the
 * catalogue carries curves rather than a peak-thrust number: the shape tells
 * you whether the vehicle gets a hard kick off the pad that fades, a gentle
 * start that builds, or something flat — and those three fly completely
 * differently even at identical total impulse.
 *
 * The area under the curve is shaded because that area *is* the total impulse,
 * which is the quantity that actually sets how much velocity the motor can
 * deliver.
 */
export function ThrustCurve({
  curve,
  className,
  showAxes = true,
}: {
  curve: readonly ThrustCurvePoint[];
  className?: string;
  showAxes?: boolean;
}) {
  const geometry = useMemo(() => {
    if (curve.length < 2) return null;
    const maxT = curve[curve.length - 1]?.t ?? 1;
    const maxThrust = curve.reduce((max, p) => Math.max(max, p.thrust_N), 0) || 1;

    // Draw in a 100 × 60 space and let the viewBox scale it, so nothing here
    // needs to know the rendered size.
    const toX = (t: number) => (t / maxT) * 100;
    const toY = (thrust: number) => 60 - (thrust / maxThrust) * 54;

    const line = curve.map((p) => `${toX(p.t).toFixed(2)},${toY(p.thrust_N).toFixed(2)}`);
    const area = `M ${toX(0)},60 L ${line.join(' L ')} L ${toX(maxT)},60 Z`;

    // Average thrust as a reference line: the flat motor that would deliver the
    // same impulse over the same burn.
    let impulse = 0;
    for (let i = 1; i < curve.length; i += 1) {
      const a = curve[i - 1];
      const b = curve[i];
      if (!a || !b) continue;
      impulse += ((a.thrust_N + b.thrust_N) / 2) * (b.t - a.t);
    }
    const average = maxT > 0 ? impulse / maxT : 0;

    return {
      path: `M ${line.join(' L ')}`,
      area,
      maxT,
      maxThrust,
      average,
      averageY: toY(average),
    };
  }, [curve]);

  if (!geometry) {
    return null;
  }

  return (
    <div className={cn('plane-sunken relative', className)}>
      <svg
        viewBox="0 0 100 60"
        preserveAspectRatio="none"
        className="block h-full w-full"
        role="img"
        aria-label={`Thrust curve. Peak ${geometry.maxThrust.toFixed(0)} newtons over ${geometry.maxT.toFixed(1)} seconds.`}
      >
        {/* The impulse, as area. */}
        <path d={geometry.area} fill="#E4682E" opacity={0.16} />

        {/* Average thrust — what a flat motor of the same impulse would give. */}
        <line
          x1={0}
          y1={geometry.averageY}
          x2={100}
          y2={geometry.averageY}
          stroke="#847D6F"
          strokeWidth={0.4}
          strokeDasharray="2 2"
          vectorEffect="non-scaling-stroke"
        />

        <path
          d={geometry.path}
          fill="none"
          stroke="#FA8A4A"
          strokeWidth={1.2}
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
        />
      </svg>

      {showAxes && (
        <>
          <span className="pointer-events-none absolute left-1.5 top-1 font-mono text-[0.6rem] text-ink-500">
            {geometry.maxThrust >= 1000
              ? `${(geometry.maxThrust / 1000).toFixed(1)} kN`
              : `${geometry.maxThrust.toFixed(0)} N`}
          </span>
          <span className="pointer-events-none absolute bottom-1 right-1.5 font-mono text-[0.6rem] text-ink-500">
            {geometry.maxT.toFixed(1)} s
          </span>
          <span className="pointer-events-none absolute bottom-1 left-1.5 font-mono text-[0.6rem] text-ink-600">
            avg{' '}
            {geometry.average >= 1000
              ? `${(geometry.average / 1000).toFixed(1)} kN`
              : `${geometry.average.toFixed(0)} N`}
          </span>
        </>
      )}
    </div>
  );
}
