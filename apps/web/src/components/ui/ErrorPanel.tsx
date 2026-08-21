import { Button } from './Button';
import { Panel } from './Panel';
import { cn } from '@/lib/utils';

/**
 * A failure the user can act on.
 *
 * Oxide-edged, because oxide means failure everywhere in this system. The
 * message is shown verbatim: an error the user cannot read is an error they
 * cannot report.
 */
export function ErrorPanel({
  title = 'Something went wrong',
  message,
  detail,
  onRetry,
  className,
}: {
  title?: string;
  message: string;
  detail?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <Panel tone="oxide" className={cn('space-y-3', className)}>
      <div className="flex items-start gap-3">
        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-signal-oxide" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <h3 className="font-condensed text-micro uppercase tracking-instrument text-signal-oxide-bright">
            {title}
          </h3>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-200">{message}</p>
          {detail && (
            <p className="mt-2 font-mono text-tiny leading-relaxed text-ink-500 break-words">
              {detail}
            </p>
          )}
        </div>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </Panel>
  );
}
