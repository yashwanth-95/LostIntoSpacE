import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A measured value.
 *
 * The single most repeated element in the product, so it is worth getting
 * exactly right:
 *
 * - the label is condensed, uppercase, quiet — you read it once
 * - the value is monospaced and tabular, so digits do not shift as it updates
 * - the unit is separate and subordinate, because `1482 m/s` is one number and
 *   one unit, not a string
 * - `tone` colours only the value, never the label, so a panel of readouts
 *   still scans as a column
 */

const tones = {
  neutral: 'text-ink-100',
  nominal: 'text-signal-nominal-bright',
  caution: 'text-signal-caution-bright',
  critical: 'text-signal-oxide-bright',
  active: 'text-signal-flame-bright',
  quiet: 'text-ink-400',
} as const;

export type ReadoutTone = keyof typeof tones;

const sizes = {
  sm: { value: 'text-xs', unit: 'text-micro' },
  md: { value: 'text-sm', unit: 'text-tiny' },
  lg: { value: 'text-lg', unit: 'text-xs' },
  xl: { value: 'text-3xl', unit: 'text-sm' },
} as const;

export interface ReadoutProps {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  tone?: ReadoutTone;
  size?: keyof typeof sizes;
  /** Label to the left, value right-aligned — for dense stacked lists. */
  inline?: boolean;
  hint?: ReactNode;
  className?: string;
}

export function Readout({
  label,
  value,
  unit,
  tone = 'neutral',
  size = 'md',
  inline,
  hint,
  className,
}: ReadoutProps) {
  const s = sizes[size];

  const valueNode = (
    <span className={cn('font-mono tabular-nums leading-none', s.value, tones[tone])}>
      {value}
      {unit && <span className={cn('ml-1 font-mono text-ink-500', s.unit)}>{unit}</span>}
    </span>
  );

  if (inline) {
    return (
      <div className={cn('flex items-baseline justify-between gap-3', className)}>
        <span className="t-label truncate">{label}</span>
        {valueNode}
      </div>
    );
  }

  return (
    <div className={className}>
      <div className="t-label mb-1">{label}</div>
      {valueNode}
      {hint && <p className="mt-1 text-tiny text-ink-500 leading-snug">{hint}</p>}
    </div>
  );
}

/**
 * A gauge with an acceptable band.
 *
 * Shows where a value sits against the range it is allowed to occupy, which is
 * the question an engineer actually has — "is 1.14 bad?" is unanswerable
 * without the band, and the band is exactly what a bare number hides.
 */
export function Gauge({
  value,
  min = 0,
  max,
  goodMin,
  goodMax,
  tone = 'neutral',
  className,
}: {
  value: number;
  min?: number;
  max: number;
  /** Lower edge of the acceptable band, in value units. */
  goodMin?: number;
  /** Upper edge of the acceptable band, in value units. */
  goodMax?: number;
  tone?: ReadoutTone;
  className?: string;
}) {
  const span = max - min || 1;
  const pct = (v: number) => Math.max(0, Math.min(100, ((v - min) / span) * 100));

  const fillTone = {
    neutral: 'bg-ink-300',
    nominal: 'bg-signal-nominal',
    caution: 'bg-signal-caution',
    critical: 'bg-signal-oxide',
    active: 'bg-signal-flame',
    quiet: 'bg-ink-500',
  }[tone];

  const bandLeft = goodMin !== undefined ? pct(goodMin) : null;
  const bandRight = goodMax !== undefined ? pct(goodMax) : 100;

  return (
    <div className={cn('gauge-track', className)}>
      {bandLeft !== null && (
        <span
          className="absolute inset-y-0 bg-signal-nominal/15"
          style={{ left: `${bandLeft}%`, width: `${Math.max(0, bandRight - bandLeft)}%` }}
          aria-hidden="true"
        />
      )}
      <span className={cn('gauge-fill', fillTone)} style={{ width: `${pct(value)}%` }} />
      {bandLeft !== null && (
        <span
          className="absolute inset-y-0 w-px bg-signal-nominal/60"
          style={{ left: `${bandLeft}%` }}
          aria-hidden="true"
        />
      )}
    </div>
  );
}

/** A status dot. `live` gives it the single slow breath. */
export function StatusDot({
  tone = 'neutral',
  live,
  className,
}: {
  tone?: ReadoutTone;
  live?: boolean;
  className?: string;
}) {
  const colour = {
    neutral: 'bg-ink-400',
    nominal: 'bg-signal-nominal',
    caution: 'bg-signal-caution',
    critical: 'bg-signal-oxide',
    active: 'bg-signal-flame',
    quiet: 'bg-ink-600',
  }[tone];

  return (
    <span
      className={cn('inline-block h-1.5 w-1.5 rounded-full', colour, live && 'animate-beacon', className)}
      aria-hidden="true"
    />
  );
}
