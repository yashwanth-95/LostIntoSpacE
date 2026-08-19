import type { ApiResponse, ApiError } from '@/types';
import { useAuthStore } from '@/stores/authStore';

const BASE_URL = '/api/v1';

class ApiClient {
  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = useAuthStore.getState().token;
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((options.headers as Record<string, string>) || {}),
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const res = await fetch(`${BASE_URL}${path}`, {
      ...options,
      headers,
    });

    if (res.status === 401) {
      useAuthStore.getState().logout();
      throw new Error('Session expired');
    }

    const body = await res.json();

    if (!res.ok) {
      const error = body as ApiError;
      throw new Error(error.error?.message || 'Request failed');
    }

    return (body as ApiResponse<T>).data;
  }

  get<T>(path: string) {
    return this.request<T>(path);
  }

  post<T>(path: string, data?: unknown) {
    return this.request<T>(path, {
      method: 'POST',
      body: data ? JSON.stringify(data) : undefined,
    });
  }

  patch<T>(path: string, data: unknown) {
    return this.request<T>(path, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
  }

  delete<T>(path: string) {
    return this.request<T>(path, { method: 'DELETE' });
  }
}

export const api = new ApiClient();
