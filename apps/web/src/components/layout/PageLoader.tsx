import { Spinner } from '@/components/ui';

/** Shown while a lazily-loaded page is fetched. */
export function PageLoader() {
  return (
    <div className="flex items-center justify-center min-h-[60vh]" role="status" aria-live="polite">
      <div className="flex flex-col items-center gap-3">
        <Spinner />
        <span className="text-xs text-space-500">Loading…</span>
      </div>
    </div>
  );
}
