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

export function Tabs({ defaultValue, children, className }: { defaultValue: string; children: ReactNode; className?: string }) {
  const [active, setActive] = useState(defaultValue);
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  );
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex gap-1 border-b border-space-800 pb-px', className)} role="tablist">
      {children}
    </div>
  );
}

export function TabsTrigger({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const { active, setActive } = useTabs();
  const isActive = active === value;
  return (
    <button
      role="tab"
      aria-selected={isActive}
      onClick={() => setActive(value)}
      className={cn(
        'px-3 py-2 text-xs font-medium transition-colors rounded-t-md',
        isActive
          ? 'text-accent-cyan border-b-2 border-accent-cyan bg-accent-cyan/5'
          : 'text-space-400 hover:text-space-200',
        className,
      )}
    >
      {children}
    </button>
  );
}

export function TabsContent({ value, children, className }: { value: string; children: ReactNode; className?: string }) {
  const { active } = useTabs();
  if (active !== value) return null;
  return <div role="tabpanel" className={cn('pt-4 animate-fade-in', className)}>{children}</div>;
}
