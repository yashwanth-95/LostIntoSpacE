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
    <div className="flex min-h-screen flex-col bg-[color:var(--plane-0)]">
      <header className="sticky top-0 z-chrome h-14 bg-[color:var(--plane-0)]/85 backdrop-blur-sm hairline-b">
        <div className="mx-auto flex h-full max-w-[1600px] items-center justify-between px-6 md:px-12">
          <Link to="/" className="flex items-center gap-2.5 focus-ring rounded-md">
            <svg
              viewBox="0 0 16 16"
              className="h-5 w-5 shrink-0 text-signal-flame"
              fill="none"
              stroke="currentColor"
              strokeWidth={1.25}
              aria-hidden="true"
            >
              <circle cx="8" cy="8" r="3.2" />
              <ellipse cx="8" cy="8" rx="7" ry="2.6" transform="rotate(-24 8 8)" />
            </svg>
            <span className="font-display text-lg leading-none text-ink-50">LostIntoSpace</span>
          </Link>

          <nav className="hidden md:flex items-center gap-1" aria-label="Primary">
            {[
              { to: '/explore', label: 'Explore' },
              { to: '/learn', label: 'Understand' },
              { to: '/rocket-lab', label: 'Build' },
              { to: '/launch', label: 'Simulate' },
              { to: '/missions', label: 'Missions' },
              { to: '/help', label: 'Help' },
            ].map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'relative px-3 py-1.5 text-sm transition-colors duration-quick focus-ring',
                    isActive
                      ? 'text-ink-50 after:absolute after:inset-x-3 after:-bottom-[1px] after:h-px after:bg-signal-flame'
                      : 'text-ink-400 hover:text-ink-100',
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
                className="inline-flex h-8 items-center rounded-instrument border border-signal-flame/40 bg-signal-flame/12 px-3 text-xs text-signal-flame-bright transition-colors duration-quick hover:bg-signal-flame/20 focus-ring"
              >
                Workspace
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="inline-flex h-8 items-center px-3 text-xs text-ink-400 transition-colors duration-quick hover:text-ink-50 focus-ring"
                >
                  Sign in
                </Link>
                <Link
                  to="/signup"
                  className="inline-flex h-8 items-center rounded-instrument border border-signal-flame/40 bg-signal-flame/12 px-3 text-xs text-signal-flame-bright transition-colors duration-quick hover:bg-signal-flame/20 focus-ring"
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

      <footer className="mt-16 py-8 hairline-t">
        <div className="mx-auto flex max-w-[1600px] flex-col justify-between gap-4 px-6 text-xs text-ink-500 md:flex-row md:px-12">
          <p>
            LostIntoSpace — Learn. Build. Simulate. Explore.{' '}
            <span className="text-ink-600">
              Educational simulation; not flight-certified engineering.
            </span>
          </p>
          <nav className="flex gap-4" aria-label="Footer">
            <Link to="/help/guide" className="transition-colors hover:text-ink-200 focus-ring">
              Guide
            </Link>
            <Link to="/help/faq" className="transition-colors hover:text-ink-200 focus-ring">
              FAQ
            </Link>
            <Link to="/help/contact" className="transition-colors hover:text-ink-200 focus-ring">
              Contact
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
