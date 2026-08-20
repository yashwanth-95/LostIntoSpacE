import { cn } from '@/lib/utils';

const sizeMap = { sm: 'h-3 w-3', md: 'h-4 w-4', lg: 'h-6 w-6' };

/**
 * Work in progress.
 *
 * A thin rotating arc rather than a chunky spinner — closer to a radar sweep
 * than to a loading GIF, and quiet enough to sit inside a dense panel.
 */
export function Spinner({
  size = 'md',
  className,
  label = 'Working',
}: {
  size?: keyof typeof sizeMap;
  className?: string;
  label?: string;
}) {
  return (
    <span
      role="status"
      aria-label={label}
      className={cn(
        'inline-block rounded-full border border-ink-600 border-t-signal-flame animate-spin',
        sizeMap[size],
        className,
      )}
    />
  );
}

/**
 * A skeleton for content still being fetched.
 *
 * Named for what it is: the channel has not delivered yet. One sweep, not an
 * infinite shimmer.
 */
export function Acquiring({ className, rows = 3 }: { className?: string; rows?: number }) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="relative h-3 overflow-hidden bg-ink-850">
          <span className="absolute inset-0 animate-sweep bg-gradient-to-r from-transparent via-ink-750 to-transparent" />
        </div>
      ))}
    </div>
  );
}
