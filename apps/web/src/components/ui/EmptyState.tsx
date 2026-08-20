import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

/**
 * Nothing to show — and why.
 *
 * "No data" on its own is useless. This always carries a reason and, where one
 * exists, the action that fixes it.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center px-6 py-14 text-center',
        className,
      )}
    >
      {icon && <div className="mb-4 text-ink-600">{icon}</div>}
      <h3 className="font-display text-xl text-ink-100">{title}</h3>
      {description && (
        <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-400">{description}</p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}
