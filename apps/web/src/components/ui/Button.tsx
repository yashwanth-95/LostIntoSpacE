import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

/**
 * A control on an instrument.
 *
 * Square-ish corners, a hairline edge, no gradient and no shadow. The primary
 * variant is flame because flame means "release energy" everywhere else in this
 * system, and the primary action is always the one that commits.
 */

const variants = {
  /** Commit. Run the simulation, open the builder, take the next step. */
  primary:
    'bg-signal-flame/12 text-signal-flame-bright border-signal-flame/40 hover:bg-signal-flame/20 hover:border-signal-flame/70',
  /** An equal alternative. */
  secondary:
    'bg-ink-800 text-ink-200 border-ink-700 hover:bg-ink-750 hover:border-ink-650 hover:text-ink-100',
  /** Tertiary — reads as text until touched. */
  ghost: 'bg-transparent text-ink-300 border-transparent hover:text-ink-50 hover:bg-ink-850',
  /** Destructive or abort. */
  danger:
    'bg-signal-oxide/12 text-signal-oxide-bright border-signal-oxide/40 hover:bg-signal-oxide/22',
  /** Confirmed-good state. */
  nominal:
    'bg-signal-nominal/12 text-signal-nominal-bright border-signal-nominal/40 hover:bg-signal-nominal/22',
  /** A pure outline, for dense toolbars. */
  outline: 'bg-transparent text-ink-200 border-ink-700 hover:border-ink-500 hover:text-ink-50',
} as const;

const sizes = {
  xs: 'h-6 px-2 text-micro gap-1 tracking-label uppercase font-condensed',
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-9 px-4 text-sm gap-2',
  lg: 'h-11 px-6 text-[0.95rem] gap-2.5',
} as const;

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', loading, disabled, children, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center rounded-instrument border font-medium',
        'transition-colors duration-quick ease-instrument focus-ring',
        'disabled:opacity-40 disabled:pointer-events-none',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && (
        <span
          className="h-3 w-3 rounded-full border border-current border-r-transparent animate-spin"
          aria-hidden="true"
        />
      )}
      {children}
    </button>
  ),
);

Button.displayName = 'Button';
