import { forwardRef, type HTMLAttributes, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * A plane.
 *
 * The one surface primitive. It is deliberately *not* a card: no shadow, no
 * blur, a 3px radius, and a hairline rule instead of a border with weight. A
 * screen made of these reads as an instrument face divided into regions rather
 * than as a page of floating tiles.
 *
 * `tone` exists so a panel can carry status — a failure panel is edged in oxide
 * — without any component inventing its own colour.
 */

const tones = {
  default: 'border-[color:var(--rule)]',
  raised: 'border-[color:var(--rule)] bg-[color:var(--plane-2)]',
  sunken: 'border-[color:var(--rule-faint)] bg-[color:var(--plane-0)]',
  nominal: 'border-signal-nominal/30',
  caution: 'border-signal-caution/35',
  oxide: 'border-signal-oxide/40',
  flame: 'border-signal-flame/35',
} as const;

export interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  tone?: keyof typeof tones;
  /** Draw the faint engineering grid. For readouts and diagram backgrounds. */
  plated?: boolean;
  /** Remove the default padding — for panels that host their own layout. */
  flush?: boolean;
}

export const Panel = forwardRef<HTMLDivElement, PanelProps>(
  ({ className, tone = 'default', plated, flush, ...props }, ref) => (
    <div
      ref={ref}
      className={cn(
        plated ? 'plate' : 'plane',
        tones[tone],
        !flush && 'p-4',
        className,
      )}
      {...props}
    />
  ),
);

Panel.displayName = 'Panel';

/**
 * A panel header: a condensed uppercase label, an optional right-hand slot, and
 * a hairline beneath. This is the shape almost every region on the instrument
 * takes.
 */
export function PanelHeader({
  label,
  aside,
  className,
}: {
  label: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex items-center justify-between gap-3 pb-2 mb-3 hairline-b',
        className,
      )}
    >
      <h2 className="t-label">{label}</h2>
      {aside}
    </div>
  );
}

/** A labelled horizontal rule. The main way this interface divides space. */
export function SectionRule({
  label,
  className,
  aside,
}: {
  label: ReactNode;
  className?: string;
  aside?: ReactNode;
}) {
  return (
    <div className={cn('flex items-center gap-3 mb-4', className)}>
      <span className="t-label whitespace-nowrap">{label}</span>
      <span className="flex-1 h-px bg-[color:var(--rule)]" />
      {aside}
    </div>
  );
}

/** Backwards-compatible alias while pages migrate off the old card shape. */
export const Card = Panel;
