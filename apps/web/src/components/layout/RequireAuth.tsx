import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/authStore';
import { PageLoader } from './PageLoader';

/**
 * Gates a route that genuinely needs an account.
 *
 * Waits for the boot-time session restore before deciding. Redirecting while
 * `isLoading` is still true would bounce a signed-in user to /login on every
 * reload — exactly the bug that makes an app feel like it forgot you.
 *
 * The attempted path travels in router state so sign-in can return there.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const isLoading = useAuthStore((s) => s.isLoading);
  const location = useLocation();

  if (isLoading) return <PageLoader />;
  if (!isAuthenticated) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <>{children}</>;
}
