import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

/**
 * A tag.
 *
 * Square, not a pill: pills read as consumer UI, and everything here is
 * classification — a subsystem, a severity, an object type. Variants map onto
 * the semantic palette so a tag's colour always means the same thing.
 */

const variants = {
  default: 'bg-ink-850 text-ink-300 border-ink-700',
  flame: 'bg-signal-flame/10 text-signal-flame-bright border-signal-flame/30',
  oxide: 'bg-signal-oxide/10 text-signal-oxide-bright border-signal-oxide/30',
  nominal: 'bg-signal-nominal/10 text-signal-nominal-bright border-signal-nominal/30',
  caution: 'bg-signal-caution/10 text-signal-caution-bright border-signal-caution/30',
  cryo: 'bg-signal-cryo/10 text-signal-cryo-bright border-signal-cryo/30',
  xenon: 'bg-signal-xenon/10 text-signal-xenon-bright border-signal-xenon/30',
  outline: 'bg-transparent text-ink-400 border-ink-700',

  // Severity aliases, so failure and event rendering can pass the engine's own
  // severity string straight through.
  info: 'bg-signal-cryo/10 text-signal-cryo-bright border-signal-cryo/30',
  warning: 'bg-signal-caution/10 text-signal-caution-bright border-signal-caution/30',
  critical: 'bg-signal-flame/12 text-signal-flame-bright border-signal-flame/35',
  fatal: 'bg-signal-oxide/12 text-signal-oxide-bright border-signal-oxide/40',
} as const;

export type BadgeVariant = keyof typeof variants;

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-instrument border px-1.5 py-0.5',
        'font-condensed text-micro uppercase tracking-label',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
