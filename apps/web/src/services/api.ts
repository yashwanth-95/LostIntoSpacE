/**
 * Typed calls against the LostIntoSpacE API.
 *
 * One function per endpoint, no React in this file — hooks live in
 * `services/queries.ts`. Everything goes through `lib/api-client`, which
 * attaches the bearer token, unwraps the `{status, data}` envelope, and logs
 * out on a 401.
 */

import { api } from '@/lib/api-client';
import type { AuthTokens, Lesson, Project, SpaceObject, User } from '@/types';
import type { SimConfig, SimResult, SimulationLimits } from '@/types/simulation';

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export interface EngineAvailability {
  available: boolean;
  reason: string | null;
}

export interface EngineStatus {
  simulation: EngineAvailability;
  search: EngineAvailability;
  ai: EngineAvailability;
}

export const health = {
  /** Which compute engines this server can reach. Never fails for engine reasons. */
  engines: () => api.get<EngineStatus>('/health/engines'),
  liveness: () => api.get<{ state: string; service: string; version: string }>('/health'),
};

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export const auth = {
  register: (body: { email: string; password: string; name: string }) =>
    api.post<AuthTokens & { user?: User }>('/auth/register', body),
  login: (body: { email: string; password: string }) =>
    api.post<AuthTokens & { user?: User }>('/auth/login', body),
  me: () => api.get<User>('/auth/me'),
  logout: () => api.post<null>('/auth/logout'),
};

// ---------------------------------------------------------------------------
// Space data
// ---------------------------------------------------------------------------

export interface Paged<T> {
  items: T[];
  total: number;
}

export const spaceObjects = {
  list: (params: {
    q?: string;
    category?: string;
    page?: number;
    per_page?: number;
    sort?: string;
  } = {}) => api.getPaged<SpaceObject>('/space-objects', params),
  categories: () => api.get<string[]>('/space-objects/categories'),
  get: (id: string) => api.get<SpaceObject>(`/space-objects/${id}`),
};

// ---------------------------------------------------------------------------
// Learning
// ---------------------------------------------------------------------------

export const learning = {
  lessons: (params: { q?: string; category?: string; page?: number; per_page?: number } = {}) =>
    api.getPaged<Lesson>('/lessons', params),
  categories: () => api.get<string[]>('/lessons/categories'),
  lesson: (identifier: string) => api.get<Lesson>(`/lessons/${identifier}`),
  progress: () => api.get<{ lesson_id: string; status: string; progress: number }[]>(
    '/learning/progress',
  ),
  recordProgress: (body: { lesson_id: string; status: string; progress?: number }) =>
    api.post<unknown>('/learning/progress', body),
};

// ---------------------------------------------------------------------------
// Workspace
// ---------------------------------------------------------------------------

export const projects = {
  list: () => api.getPaged<Project>('/projects'),
  create: (body: { name: string; description?: string }) =>
    api.post<Project>('/projects', body),
  get: (id: string) => api.get<Project>(`/projects/${id}`),
  remove: (id: string) => api.delete<null>(`/projects/${id}`),
};

// ---------------------------------------------------------------------------
// Simulation
// ---------------------------------------------------------------------------

export interface SimulationRunResult {
  result: SimResult;
  meta: {
    engine: string;
    engine_version: string;
    compute_time_s: number;
    telemetry_points_generated: number;
    telemetry_points_returned: number;
    telemetry_decimated: boolean;
  };
}

export const simulation = {
  /** Fly one mission. Returns the complete flight, not a stream. */
  run: (config: SimConfig) => api.postWithMeta<SimResult>('/simulations/run', { config }),
  limits: () => api.get<SimulationLimits>('/simulations/limits'),
};

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

export interface SearchResultItem {
  id: string;
  title: string;
  summary?: string;
  entity_type: string;
  score: number;
  match_type?: string;
  topics?: string[];
  provenance?: {
    sources?: {
      source_name: string;
      source_type: string;
      source_url?: string | null;
    }[];
  };
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
  total?: number;
  took_ms?: number;
  explanation?: string;
  suggestions?: string[];
  facets?: { field: string; values: { value: string; count: number }[] }[];
}

export const search = {
  query: (params: { q: string; entity_type?: string[]; limit?: number }) =>
    api.get<SearchResponse>(`/search${toQuery(params)}`),
};

// ---------------------------------------------------------------------------
// AI
// ---------------------------------------------------------------------------

export interface SourceReference {
  source_name: string;
  source_type: string;
  source_url?: string | null;
  retrieved_at?: string | null;
}

export interface AIResponse {
  answer: string;
  citations?: { marker: string; title?: string; source?: SourceReference }[];
  sources?: SourceReference[];
  confidence?: string;
  data_origin?: string;
  freshness_note?: string | null;
  related_topics?: string[];
  suggested_questions?: string[];
  diagnostics?: Record<string, unknown>;
}

export interface FailureAnalysis {
  simulation_id?: string | null;
  summary: string;
  likely_cause?: string | null;
  observations: { label?: string; statement?: string; value?: number; unit?: string }[];
  affected_subsystems: string[];
  consequences: string[];
  explanations?: { statement: string }[];
  mitigations?: { action: string; rationale?: string }[];
  simulation_limitations: string[];
  sources?: SourceReference[];
  confidence?: string;
}

export const ai = {
  ask: (question: string) => api.post<AIResponse>('/ai/ask', { question }),
  explainFailure: (body: {
    simulation_result: SimResult;
    vehicle_description?: string;
    mission_description?: string;
  }) => api.post<FailureAnalysis>('/ai/explain-failure', body),
  provider: () =>
    api.get<{ selected_provider: string; available: string[] }>('/ai/provider'),
};

// ---------------------------------------------------------------------------

function toQuery(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue;
    if (Array.isArray(value)) {
      for (const item of value) search.append(key, String(item));
    } else {
      search.append(key, String(value));
    }
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}

export { toQuery };
