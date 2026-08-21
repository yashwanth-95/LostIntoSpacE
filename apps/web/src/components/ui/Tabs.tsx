import { createContext, useContext, useState, type ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface TabsContextValue {
  active: string;
  setActive: (id: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabs() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('Tabs compound components must be used within <Tabs>');
  return ctx;
}

/**
 * Tabs, as a channel selector.
 *
 * A hairline underline marks the active channel rather than a filled pill, so a
 * tab strip sits on the same visual plane as the rules that structure the rest
 * of the screen.
 */
export function Tabs({
  defaultValue,
  value,
  onValueChange,
  children,
  className,
}: {
  defaultValue: string;
  /** Controlled mode: drive the active tab from outside. */
  value?: string;
  onValueChange?: (id: string) => void;
  children: ReactNode;
  className?: string;
}) {
  const [internal, setInternal] = useState(defaultValue);
  const active = value ?? internal;
  const setActive = (id: string) => {
    setInternal(id);
    onValueChange?.(id);
  };

  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn('flex gap-5 hairline-b overflow-x-auto no-scrollbar', className)}
      role="tablist"
    >
      {children}
    </div>
  );
}

export function TabsTrigger({
  value,
  children,
  count,
  className,
}: {
  value: string;
  children: ReactNode;
  /** An optional item count, rendered as a monospaced superscript. */
  count?: number;
  className?: string;
}) {
  const { active, setActive } = useTabs();
  const isActive = active === value;
  return (
    <button
      role="tab"
      aria-selected={isActive}
      onClick={() => setActive(value)}
      className={cn(
        'relative -mb-px shrink-0 whitespace-nowrap pb-2 pt-1',
        'font-condensed text-micro uppercase tracking-instrument',
        'transition-colors duration-quick ease-instrument focus-ring',
        isActive
          ? 'text-ink-50 border-b border-signal-flame'
          : 'text-ink-500 border-b border-transparent hover:text-ink-200',
        className,
      )}
    >
      {children}
      {count !== undefined && (
        <span className="ml-1.5 font-mono text-[0.55rem] text-ink-600">{count}</span>
      )}
    </button>
  );
}

export function TabsContent({
  value,
  children,
  className,
}: {
  value: string;
  children: ReactNode;
  className?: string;
}) {
  const { active } = useTabs();
  if (active !== value) return null;
  return (
    <div role="tabpanel" className={cn('pt-4 animate-acquire', className)}>
      {children}
    </div>
  );
}
