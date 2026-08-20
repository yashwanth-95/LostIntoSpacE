import { useEffect } from 'react';
import { api } from '@/lib/api-client';
import { useAuthStore } from '@/stores/authStore';
import type { AuthTokens, User } from '@/types';

/**
 * Exchange a persisted refresh token for a live session, once, on boot.
 *
 * Without this the app renders as logged-out on every reload even when the user
 * has a valid session, which reads as "it forgot me" rather than "it signed me
 * out". `isLoading` stays true until this settles so protected routes do not
 * flash a redirect to /login before the answer is known.
 *
 * Any failure is a clean logged-out state, never an error screen: an expired or
 * revoked refresh token is a completely ordinary thing to find in storage.
 */
export function useSessionRestore(): void {
  useEffect(() => {
    const { refreshToken, login, logout } = useAuthStore.getState();

    if (!refreshToken) {
      useAuthStore.getState().setLoading(false);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const tokens = await api.post<AuthTokens>('/auth/refresh', {
          refresh_token: refreshToken,
        });
        if (cancelled) return;

        // The token is set before /auth/me so the client can authenticate it.
        login(null, tokens.access_token, tokens.refresh_token ?? refreshToken);

        const user = await api.get<User>('/auth/me');
        if (!cancelled) useAuthStore.getState().setUser(user);
      } catch {
        if (!cancelled) logout();
      } finally {
        if (!cancelled) useAuthStore.getState().setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);
}
