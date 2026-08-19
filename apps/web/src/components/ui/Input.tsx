import { forwardRef, type InputHTMLAttributes } from 'react';
import { cn } from '@/lib/utils';

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');
    return (
      <div className="flex flex-col gap-1.5">
        {label && (
          <label htmlFor={inputId} className="text-xs font-medium text-space-300">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            'h-9 w-full rounded-md border bg-space-900/60 px-3 text-sm text-space-100 placeholder:text-space-500 transition-colors focus-ring',
            error
              ? 'border-severity-fatal/50 focus:border-severity-fatal'
              : 'border-space-700 focus:border-accent-cyan/50',
            className,
          )}
          {...props}
        />
        {error && <p className="text-2xs text-severity-fatal">{error}</p>}
      </div>
    );
  },
);

Input.displayName = 'Input';
