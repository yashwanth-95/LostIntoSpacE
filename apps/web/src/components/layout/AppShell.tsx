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
    <div className="min-h-screen bg-space-950">
      <Sidebar />
      <div className={cn('flex flex-col min-h-screen transition-all duration-200', collapsed ? 'ml-16' : 'ml-56')}>
        <TopBar />
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
    </div>
  );
}
