import { useNavigate } from 'react-router-dom';
import { useUIStore } from '@/stores/uiStore';
import { useAuthStore } from '@/stores/authStore';
import { Button } from '@/components/ui';

export function TopBar() {
  const setSearchOpen = useUIStore((s) => s.setSearchOpen);
  const user = useAuthStore((s) => s.user);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const navigate = useNavigate();

  return (
    <header className="h-14 border-b border-space-800 bg-space-900/60 backdrop-blur-md flex items-center justify-between px-6 shrink-0">
      <div className="flex items-center gap-4">
        <button
          onClick={() => setSearchOpen(true)}
          className="flex items-center gap-2 h-8 px-3 rounded-md border border-space-700 bg-space-800/50 text-space-400 text-xs hover:text-space-200 hover:border-space-600 transition-colors min-w-[240px]"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <span>Search space objects, missions, lessons...</span>
          <kbd className="ml-auto text-2xs text-space-500 border border-space-700 rounded px-1">Ctrl+K</kbd>
        </button>
      </div>

      <div className="flex items-center gap-3">
        {isAuthenticated && user ? (
          <button
            onClick={() => navigate('/settings')}
            className="flex items-center gap-2 text-sm text-space-300 hover:text-space-100 transition-colors"
          >
            <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent-indigo to-accent-violet flex items-center justify-center">
              <span className="text-xs font-semibold text-white">
                {user.name.charAt(0).toUpperCase()}
              </span>
            </div>
            <span className="text-xs">{user.name}</span>
          </button>
        ) : (
          <Button size="sm" onClick={() => navigate('/login')}>
            Sign in
          </Button>
        )}
      </div>
    </header>
  );
}
