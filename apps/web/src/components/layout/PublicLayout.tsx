import { Link, NavLink, Outlet } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { cn } from '@/lib/utils';

/**
 * Chrome for the pages a visitor meets before they are "in" the product:
 * landing, help, and the auth screens.
 *
 * No sidebar. A dashboard rail is a promise that there is work in progress, and
 * on a first visit there isn't — the job of these pages is to explain what this
 * is and get someone into the platform.
 */
export function PublicLayout() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isGuest = useAuthStore((s) => s.isGuest);

  return (
    <div className="min-h-screen bg-space-950 flex flex-col">
      <header className="sticky top-0 z-40 h-14 border-b border-space-800/60 bg-space-950/80 backdrop-blur-md">
        <div className="mx-auto max-w-7xl h-full px-6 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5 focus-ring rounded-md">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center">
              <span className="text-xs font-bold text-white">L</span>
            </div>
            <span className="font-display font-semibold text-sm text-space-100">
              LostIntoSpace
            </span>
          </Link>

          <nav className="hidden md:flex items-center gap-1" aria-label="Primary">
            {[
              { to: '/explore', label: 'Explore' },
              { to: '/learn', label: 'Learn' },
              { to: '/rocket-lab', label: 'Rocket Lab' },
              { to: '/missions', label: 'Missions' },
              { to: '/help', label: 'Help' },
            ].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'px-3 py-1.5 rounded-md text-sm transition-colors focus-ring',
                    isActive
                      ? 'text-accent-cyan bg-accent-cyan/10'
                      : 'text-space-400 hover:text-space-100 hover:bg-space-800/60',
                  )
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            {isAuthenticated ? (
              <Link
                to="/workspace"
                className="h-8 px-3 inline-flex items-center rounded-md text-xs bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/20 transition-colors focus-ring"
              >
                Workspace
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="h-8 px-3 inline-flex items-center rounded-md text-xs text-space-300 hover:text-space-100 transition-colors focus-ring"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="h-8 px-3 inline-flex items-center rounded-md text-xs bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/20 transition-colors focus-ring"
                >
                  {isGuest ? 'Create account' : 'Sign up'}
                </Link>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-space-800/60 py-8 mt-16">
        <div className="mx-auto max-w-7xl px-6 flex flex-col md:flex-row gap-4 justify-between text-xs text-space-500">
          <p>
            LostIntoSpace — Learn. Build. Simulate. Explore.{' '}
            <span className="text-space-600">
              Educational simulation; not flight-certified engineering.
            </span>
          </p>
          <nav className="flex gap-4" aria-label="Footer">
            <Link to="/help/guide" className="hover:text-space-300 focus-ring rounded">
              Guide
            </Link>
            <Link to="/help/faq" className="hover:text-space-300 focus-ring rounded">
              FAQ
            </Link>
            <Link to="/help/contact" className="hover:text-space-300 focus-ring rounded">
              Contact
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
