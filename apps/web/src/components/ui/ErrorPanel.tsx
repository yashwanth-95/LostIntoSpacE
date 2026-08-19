import { Button } from './Button';
import { cn } from '@/lib/utils';

interface ErrorPanelProps {
  title?: string;
  message: string;
  onRetry?: () => void;
  className?: string;
}

export function ErrorPanel({ title = 'Something went wrong', message, onRetry, className }: ErrorPanelProps) {
  return (
    <div className={cn('glass-panel p-6 text-center', className)}>
      <div className="mx-auto mb-3 w-10 h-10 rounded-full bg-severity-fatal/10 flex items-center justify-center">
        <svg className="w-5 h-5 text-severity-fatal" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      </div>
      <h3 className="text-sm font-semibold text-space-100">{title}</h3>
      <p className="mt-1 text-xs text-space-400">{message}</p>
      {onRetry && (
        <Button variant="secondary" size="sm" onClick={onRetry} className="mt-4">
          Try again
        </Button>
      )}
    </div>
  );
}
