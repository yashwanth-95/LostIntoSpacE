import { useEffect, useRef, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  /** Widen for component inspection and comparison views. */
  size?: 'sm' | 'md' | 'lg' | 'xl';
  className?: string;
}

const widths = {
  sm: 'max-w-sm',
  md: 'max-w-lg',
  lg: 'max-w-3xl',
  xl: 'max-w-5xl',
} as const;

/**
 * A modal.
 *
 * The overlay dims rather than blurs — a blurred backdrop reads as consumer
 * software, and here the thing behind the dialog is usually a diagram the user
 * wants to keep locating themselves against.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  size = 'md',
  className,
}: ModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handler);
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = '';
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-modal flex items-start justify-center overflow-y-auto bg-ink-1000/80 p-4 py-[8vh] animate-acquire"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div
        className={cn(
          'plane-raised w-full',
          widths[size],
          className,
        )}
      >
        {title && (
          <div className="flex items-start justify-between gap-4 hairline-b px-5 py-3">
            <div className="min-w-0">
              <h2 className="font-display text-lg leading-tight text-ink-50">{title}</h2>
              {description && <p className="mt-0.5 text-tiny text-ink-400">{description}</p>}
            </div>
            <button
              onClick={onClose}
              className="-mr-1 shrink-0 p-1 text-ink-500 transition-colors hover:text-ink-100 focus-ring"
              aria-label="Close"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 16 16" stroke="currentColor" strokeWidth="1.4">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>
        )}
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}
