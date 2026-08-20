import { create } from 'zustand';
import type { User } from '@/types';

/**
 * Session state.
 *
 * ## Where the token lives
 *
 * The access token is held in memory; only the **refresh** token is persisted,
 * in `localStorage`. That is a deliberate trade-off rather than an oversight:
 *
 * - Keeping the access token in memory only means a reload loses the session
 *   entirely, which is a poor experience for a platform people return to.
 * - Putting the access token in `localStorage` exposes it to any XSS on the
 *   page for its full lifetime.
 *
 * Persisting only the refresh token and exchanging it on boot keeps the
 * short-lived credential out of storage while surviving a reload. The genuinely
 * correct answer is an httpOnly refresh cookie, which needs a backend change
 * (Set-Cookie on login, CSRF protection on refresh) and is recorded as a
 * follow-up in docs/integration/MVP_STATUS.md.
 *
 * ## Guest mode
 *
 * `isGuest` is not "logged out". A visitor who chooses "Continue as guest" has
 * made a decision, and the interface stops asking them to sign in. Everything
 * except persistence works in that state.
 */

const REFRESH_TOKEN_KEY = 'lis.refresh_token';
const GUEST_KEY = 'lis.guest';

interface AuthState {
  user: User | null;
  token: string | null;
  refreshToken: string | null;
  isAuthenticated: boolean;
  /** True until the boot-time session restore has finished. */
  isLoading: boolean;
  isGuest: boolean;

  login: (user: User | null, token: string, refreshToken?: string | null) => void;
  logout: () => void;
  setUser: (user: User) => void;
  setLoading: (loading: boolean) => void;
  continueAsGuest: () => void;
}

function readStoredRefreshToken(): string | null {
  try {
    return localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    // Private browsing and blocked storage both throw here. A session that
    // cannot be persisted still has to work for the current tab.
    return null;
  }
}

function persistRefreshToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(REFRESH_TOKEN_KEY, token);
    else localStorage.removeItem(REFRESH_TOKEN_KEY);
  } catch {
    /* storage unavailable — the in-memory session is still valid */
  }
}

function readGuestFlag(): boolean {
  try {
    return localStorage.getItem(GUEST_KEY) === '1';
  } catch {
    return false;
  }
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,
  refreshToken: readStoredRefreshToken(),
  isAuthenticated: false,
  isLoading: true,
  isGuest: readGuestFlag(),

  login: (user, token, refreshToken = null) => {
    if (refreshToken) persistRefreshToken(refreshToken);
    try {
      localStorage.removeItem(GUEST_KEY);
    } catch {
      /* ignore */
    }
    set({
      user,
      token,
      refreshToken: refreshToken ?? null,
      isAuthenticated: true,
      isLoading: false,
      isGuest: false,
    });
  },

  logout: () => {
    persistRefreshToken(null);
    set({
      user: null,
      token: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
    });
  },

  setUser: (user) => set({ user }),
  setLoading: (isLoading) => set({ isLoading }),

  continueAsGuest: () => {
    try {
      localStorage.setItem(GUEST_KEY, '1');
    } catch {
      /* ignore */
    }
    set({ isGuest: true, isLoading: false });
  },
}));

export { REFRESH_TOKEN_KEY };
