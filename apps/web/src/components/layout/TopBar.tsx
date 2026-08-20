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
    <header className="flex h-14 shrink-0 items-center justify-between bg-[color:var(--plane-1)] px-6 hairline-b">
      <div className="flex items-center gap-4">
        <button
          onClick={() => setSearchOpen(true)}
          className="flex h-8 min-w-[260px] items-center gap-2 rounded-instrument border border-ink-700 bg-ink-950 px-3 text-xs text-ink-500 transition-colors duration-quick hover:border-ink-600 hover:text-ink-200 focus-ring"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <span>Search objects, missions, science…</span>
          <kbd className="ml-auto rounded-instrument border border-ink-700 px-1 font-mono text-micro text-ink-600">Ctrl K</kbd>
        </button>
      </div>

      <div className="flex items-center gap-3">
        {isAuthenticated && user ? (
          <button
            onClick={() => navigate('/workspace')}
            className="flex items-center gap-2 text-sm text-ink-300 transition-colors hover:text-ink-50 focus-ring"
          >
            <div className="flex h-7 w-7 items-center justify-center rounded-instrument border border-ink-650 bg-ink-850">
              <span className="font-mono text-xs text-ink-200">
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
