import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  /** A unit rendered inside the right edge — for dimensioned fields. */
  suffix?: string;
}

/** A field. Sunken rather than raised, because you type *into* an instrument. */
export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, suffix, type = 'text', ...props }, ref) => (
    <div className="relative">
      <input
        ref={ref}
        type={type}
        className={cn(
          'w-full h-9 rounded-instrument border border-ink-700 bg-ink-950 px-3',
          'text-sm text-ink-100 placeholder:text-ink-500',
          'transition-colors duration-quick ease-instrument',
          'hover:border-ink-650 focus:border-signal-flame/60 focus:outline-none',
          'disabled:opacity-40',
          type === 'number' && 'font-mono tabular-nums',
          suffix && 'pr-12',
          className,
        )}
        {...props}
      />
      {suffix && (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 font-mono text-tiny text-ink-500">
          {suffix}
        </span>
      )}
    </div>
  ),
);

Input.displayName = 'Input';
