import type { HTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const variants = {
  default: 'bg-space-800 text-space-300 border-space-700',
  cyan: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30',
  blue: 'bg-accent-blue/10 text-accent-blue border-accent-blue/30',
  amber: 'bg-accent-amber/10 text-accent-amber border-accent-amber/30',
  emerald: 'bg-accent-emerald/10 text-accent-emerald border-accent-emerald/30',
  rose: 'bg-accent-rose/10 text-accent-rose border-accent-rose/30',
  violet: 'bg-accent-violet/10 text-accent-violet border-accent-violet/30',
  info: 'bg-severity-info/10 text-severity-info border-severity-info/30',
  warning: 'bg-severity-warning/10 text-severity-warning border-severity-warning/30',
  critical: 'bg-severity-critical/10 text-severity-critical border-severity-critical/30',
  fatal: 'bg-severity-fatal/10 text-severity-fatal border-severity-fatal/30',
} as const;

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: keyof typeof variants;
}

export function Badge({ className, variant = 'default', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-2xs font-medium',
        variants[variant],
        className,
      )}
      {...props}
    />
  );
}
