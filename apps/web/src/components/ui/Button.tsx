import { forwardRef, type ButtonHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

const variants = {
  primary:
    'bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/20 hover:border-accent-cyan/50',
  secondary:
    'bg-space-800 text-space-200 border border-space-700 hover:bg-space-700 hover:text-space-100',
  ghost:
    'text-space-300 hover:text-space-100 hover:bg-space-800',
  danger:
    'bg-severity-fatal/10 text-severity-fatal border border-severity-fatal/30 hover:bg-severity-fatal/20',
  success:
    'bg-accent-emerald/10 text-accent-emerald border border-accent-emerald/30 hover:bg-accent-emerald/20',
} as const;

const sizes = {
  sm: 'h-8 px-3 text-xs gap-1.5',
  md: 'h-9 px-4 text-sm gap-2',
  lg: 'h-11 px-6 text-base gap-2.5',
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
        'inline-flex items-center justify-center rounded-md font-medium transition-colors focus-ring disabled:opacity-50 disabled:pointer-events-none',
        variants[variant],
        sizes[size],
        className,
      )}
      {...props}
    >
      {loading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      )}
      {children}
    </button>
  ),
);

Button.displayName = 'Button';
