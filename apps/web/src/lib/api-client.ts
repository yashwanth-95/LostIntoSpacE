import type { ApiError, ApiResponse } from '@/types';
import { useAuthStore } from '@/stores/authStore';

/**
 * Relative, so the Vite dev proxy and a production reverse proxy both work
 * without a rebuild. `VITE_API_URL` overrides it for a deployment where the API
 * lives on another origin — in that case CORS_ORIGINS must list this origin.
 */
const BASE_URL = import.meta.env.VITE_API_URL || '/api/v1';

/** An API failure that kept its structured envelope. */
export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly details?: unknown[],
  ) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

class ApiClient {
  private async request<T>(path: string, options: RequestInit = {}): Promise<ApiResponse<T>> {
    const token = useAuthStore.getState().token;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    let res: Response;
    try {
      res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
    } catch (cause) {
      // fetch only rejects on a network-level failure. Distinguished from an
      // API error so the UI can say "the server is unreachable" rather than
      // reporting a request that never happened as a rejected one.
      throw new ApiRequestError(
        'Could not reach the API. Is the backend running on port 8000?',
        0,
        'NETWORK_ERROR',
        [String(cause)],
      );
    }

    if (res.status === 401 && token) {
      // Only log out if we actually sent a token. A 401 on an anonymous call
      // to a protected route is expected and must not clear a valid session.
      useAuthStore.getState().logout();
      throw new ApiRequestError('Your session has expired. Sign in again.', 401, 'UNAUTHORIZED');
    }

    if (res.status === 204) {
      return { status: 'success', data: null as T };
    }

    let body: unknown;
    try {
      body = await res.json();
    } catch {
      throw new ApiRequestError(
        `The server returned an unreadable response (${res.status}).`,
        res.status,
        'MALFORMED_RESPONSE',
      );
    }

    if (!res.ok) {
      const error = body as ApiError;
      throw new ApiRequestError(
        error?.error?.message || `Request failed (${res.status})`,
        res.status,
        error?.error?.code || 'UNKNOWN',
        error?.error?.details,
      );
    }

    return body as ApiResponse<T>;
  }

  async get<T>(path: string): Promise<T> {
    return (await this.request<T>(path)).data;
  }

  /** A list endpoint, returning both the page and its total. */
  async getPaged<T>(
    path: string,
    params: Record<string, unknown> = {},
  ): Promise<{ items: T[]; total: number }> {
    const search = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null || value === '') continue;
      search.append(key, String(value));
    }
    const query = search.toString();
    const body = await this.request<T[]>(`${path}${query ? `?${query}` : ''}`);
    return { items: body.data ?? [], total: body.meta?.total ?? (body.data ?? []).length };
  }

  async post<T>(path: string, data?: unknown): Promise<T> {
    const body = await this.request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
    return body.data;
  }

  /** POST where the caller needs `meta` as well as `data` — a simulation run
   * carries its engine version and timing there. */
  async postWithMeta<T>(
    path: string,
    data?: unknown,
  ): Promise<{ data: T; meta: Record<string, unknown> }> {
    const body = await this.request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
    return { data: body.data, meta: (body.meta ?? {}) as Record<string, unknown> };
  }

  async patch<T>(path: string, data: unknown): Promise<T> {
    return (await this.request<T>(path, { method: 'PATCH', body: JSON.stringify(data) })).data;
  }

  async delete<T>(path: string): Promise<T> {
    return (await this.request<T>(path, { method: 'DELETE' })).data;
  }
}

export const api = new ApiClient();
