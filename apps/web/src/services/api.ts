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
// Reference catalog
// ---------------------------------------------------------------------------

export interface CatalogProperty {
  label: string;
  value?: number | null;
  unit?: string | null;
  precision?: number | null;
  display?: string | null;
  note?: string | null;
  earth_ratio?: number | null;
}

export interface CatalogImage {
  url: string;
  nasa_id?: string | null;
  title: string;
  credit: string;
  alt: string;
  date?: string | null;
  instrument?: string | null;
}

export interface CatalogAppearance {
  base_color: string;
  accent_color?: string | null;
  band_colors: string[];
  radius_km: number;
  texture: string;
  albedo: number;
  atmosphere_color?: string | null;
  atmosphere_strength: number;
  emissive: boolean;
  axial_tilt_deg: number;
  ring?: {
    inner_radius_ratio: number;
    outer_radius_ratio: number;
    color: string;
    opacity: number;
    tilt_deg: number;
    gaps: number[];
  } | null;
}

export interface CatalogObject {
  id: string;
  name: string;
  designation?: string | null;
  kind: string;
  parent_id?: string | null;
  classification: string;
  tagline: string;
  overview: string;
  physical: CatalogProperty[];
  orbital: CatalogProperty[];
  atmosphere: CatalogProperty[];
  facts: string[];
  mission_ids: string[];
  related_ids: string[];
  concept_slugs: string[];
  appearance: CatalogAppearance;
  image?: CatalogImage | null;
  gallery: CatalogImage[];
  field_x?: number | null;
  field_y?: number | null;
  field_depth: number;
  sources: SourceReference[];
}

export interface FieldObject {
  id: string;
  name: string;
  kind: string;
  classification: string;
  tagline: string;
  appearance: CatalogAppearance;
  x: number;
  y: number;
  depth: number;
  headline: CatalogProperty[];
  image?: CatalogImage | null;
}

export interface LaunchSiteRecord {
  id: string;
  name: string;
  short_name: string;
  country: string;
  operator: string;
  latitude_deg: number;
  longitude_deg: number;
  elevation_m: number;
  pads: string[];
  azimuth_range_deg: number[];
  typical_orbits: string[];
  vehicles: string[];
  notes: string;
  min_inclination_deg?: number | null;
  earth_rotation_bonus_ms?: number | null;
  established_year?: number | null;
}

export interface InteractiveParameter {
  key: string;
  label: string;
  unit?: string | null;
  min: number;
  max: number;
  default: number;
  step?: number | null;
  logarithmic: boolean;
  precision: number;
  hint?: string | null;
}

export interface ScienceTopic {
  slug: string;
  title: string;
  strand: string;
  level: 'foundation' | 'intermediate' | 'advanced';
  summary: string;
  outcomes: string[];
  prerequisites: string[];
  sections: {
    heading: string;
    body: string;
    equation?: string | null;
    worked_example?: string | null;
    image?: CatalogImage | null;
  }[];
  interactive?: {
    kind: string;
    title: string;
    instruction: string;
    parameters: InteractiveParameter[];
    outputs: string[];
    equation?: string | null;
    equation_note?: string | null;
  } | null;
  glossary: Record<string, string>;
  object_ids: string[];
  experiment_ids: string[];
  explains_failures: string[];
  estimated_minutes: number;
  image?: CatalogImage | null;
}

export interface Experiment {
  id: string;
  title: string;
  objective: string;
  question: string;
  category: string;
  level: string;
  base_design: string;
  variable: string;
  variable_label: string;
  variable_unit?: string | null;
  sweep: number[];
  controls: string[];
  measures: string[];
  procedure: { instruction: string; changes: Record<string, number | string | boolean>; expectation?: string | null }[];
  hypothesis: string;
  explanation: string;
  topic_slugs: string[];
  estimated_runs: number;
}

export interface ReferenceMission {
  id: string;
  name: string;
  operator: string;
  status: string;
  mission_type: string;
  objective: string;
  overview: string;
  launch_date?: string | null;
  end_date?: string | null;
  launch_vehicle?: string | null;
  launch_site_id?: string | null;
  destination_ids: string[];
  crew: string[];
  timeline: { date: string; title: string; detail: string; significant: boolean }[];
  discoveries: string[];
  vehicle_facts: CatalogProperty[];
  failures: string[];
  concept_slugs: string[];
  image?: CatalogImage | null;
}

export interface AssetRecord {
  id: string;
  title: string;
  kind: string;
  url: string;
  thumbnail_url?: string | null;
  credit: string;
  license: string;
  alt: string;
  description: string;
  tags: string[];
  subject_ids: string[];
  nasa_id?: string | null;
  date?: string | null;
}

export interface CatalogSummary {
  space_objects: { total: number; by_kind: Record<string, number> };
  launch_sites: { total: number };
  science: { total: number; strands: { name: string; count: number }[]; interactive: number };
  experiments: { total: number };
  missions: { total: number };
  assets: { total: number; by_kind: Record<string, number> };
}

export const catalog = {
  summary: () => api.get<CatalogSummary>('/catalog'),

  objects: (params: { kind?: string; parent_id?: string; q?: string } = {}) =>
    api.get<CatalogObject[]>(`/catalog/objects${toQuery(params)}`),
  object: (id: string) => api.get<CatalogObject>(`/catalog/objects/${id}`),
  /** The curated landing-page field: enough to draw and label, nothing more. */
  field: () => api.get<{ objects: FieldObject[]; total_catalog: number }>('/catalog/objects/field'),

  launchSites: () => api.get<LaunchSiteRecord[]>('/catalog/launch-sites'),
  launchSite: (id: string) => api.get<LaunchSiteRecord>(`/catalog/launch-sites/${id}`),

  science: (params: { strand?: string; level?: string; q?: string } = {}) =>
    api.get<ScienceTopic[]>(`/catalog/science${toQuery(params)}`),
  topic: (slug: string) => api.get<ScienceTopic>(`/catalog/science/${slug}`),

  experiments: (params: { category?: string; level?: string } = {}) =>
    api.get<Experiment[]>(`/catalog/experiments${toQuery(params)}`),
  experiment: (id: string) => api.get<Experiment>(`/catalog/experiments/${id}`),

  missions: (params: { status?: string; destination?: string; q?: string } = {}) =>
    api.get<ReferenceMission[]>(`/catalog/missions${toQuery(params)}`),
  mission: (id: string) => api.get<ReferenceMission>(`/catalog/missions/${id}`),

  assets: (params: { kind?: string; tag?: string; subject?: string; q?: string } = {}) =>
    api.get<AssetRecord[]>(`/catalog/assets${toQuery(params)}`),
  asset: (id: string) => api.get<AssetRecord>(`/catalog/assets/${id}`),
};

// ---------------------------------------------------------------------------
// Launch-site environment
// ---------------------------------------------------------------------------

export interface WeatherObservation {
  site_id: string;
  observed_at: string;
  temperature_K: number;
  dew_point_K?: number | null;
  pressure_Pa: number;
  sea_level_pressure_Pa?: number | null;
  relative_humidity: number;
  wind: { speed_ms: number; direction_deg: number; gust_ms?: number | null };
  precipitation_mm_h: number;
  cloud_cover: number;
  visibility_m?: number | null;
  air_density_kgm3: number;
  speed_of_sound_ms: number;
  jet_wind_speed_ms?: number | null;
  provider: string;
  /** False when no provider could be reached; `fallback_reason` says why. */
  is_live: boolean;
  fallback_reason?: string | null;
  attribution: string;
}

export interface LaunchConstraint {
  id: string;
  label: string;
  status: 'go' | 'caution' | 'no-go';
  measured: number;
  limit: number;
  unit: string;
  explanation: string;
}

export interface LaunchSuitability {
  status: 'go' | 'caution' | 'no-go';
  summary: string;
  constraints: LaunchConstraint[];
  violations: string[];
}

/** Exactly the shape the simulation's `EnvironmentConfig` takes. */
export interface SimulationEnvironment {
  temperature_K: number;
  pressure_Pa: number;
  wind_speed_ms: number;
  wind_direction_deg: number;
  relative_humidity: number;
  jet_wind_speed_ms: number;
  source: string;
  observed_at: string;
}

export interface SiteWeather {
  site: {
    id: string;
    name: string;
    short_name: string;
    country: string;
    operator: string;
    latitude_deg: number;
    longitude_deg: number;
    elevation_m: number;
  };
  observation: WeatherObservation;
  suitability: LaunchSuitability;
  /** Feed this straight into a simulation — no values are retyped in between. */
  simulation_environment: SimulationEnvironment;
}

export const environment = {
  weather: (siteId: string, refresh = false) =>
    api.get<SiteWeather>(`/environment/weather/${siteId}${refresh ? '?refresh=true' : ''}`),
  simulationConfig: (siteId: string) =>
    api.get<SimulationEnvironment>(`/environment/simulation-config/${siteId}`),
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
