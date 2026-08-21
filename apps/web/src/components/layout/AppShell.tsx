import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { SearchModal } from '@/components/features/search/SearchModal';
import { useUIStore } from '@/stores/uiStore';
import { cn } from '@/lib/utils';
import { useEffect } from 'react';

export function AppShell() {
  const collapsed = useUIStore((s) => s.sidebarCollapsed);
  const searchOpen = useUIStore((s) => s.searchOpen);
  const setSearchOpen = useUIStore((s) => s.setSearchOpen);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen(!searchOpen);
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [searchOpen, setSearchOpen]);

  return (
    <div className="min-h-screen bg-[color:var(--plane-0)]">
      <Sidebar />
      <div className={cn('flex min-h-screen flex-col transition-[margin] duration-settle ease-instrument', collapsed ? 'ml-14' : 'ml-60')}>
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
