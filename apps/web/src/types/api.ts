export interface ApiResponse<T> {
  status: 'success';
  data: T;
  meta?: {
    page: number;
    per_page: number;
    total: number;
  };
}

export interface ApiError {
  status: 'error';
  error: {
    code: string;
    message: string;
    details?: unknown[];
  };
}

export interface User {
  id: string;
  email: string;
  name: string;
  avatar_url?: string | null;
  created_at: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Project {
  id: string;
  user_id: string;
  name: string;
  description: string;
  created_at: string;
  updated_at: string;
  mission_count: number;
}

export interface Mission {
  id: string;
  project_id: string;
  name: string;
  objective: string;
  status: 'draft' | 'ready' | 'simulated' | 'analyzed';
  target_altitude_km: number;
  target_type: 'suborbital' | 'leo' | 'meo' | 'geo' | 'escape';
  created_at: string;
  updated_at: string;
}

export interface SpaceObject {
  id: string;
  name: string;
  object_type: string;
  description?: string;
  physical_properties?: Record<string, unknown>;
  orbital_elements?: Record<string, unknown>;
  image_url?: string;
  source_name?: string;
}

export interface Lesson {
  id: string;
  slug: string;
  title: string;
  description: string;
  category: string;
  difficulty: 'beginner' | 'intermediate' | 'advanced';
  duration_minutes: number;
  content?: string;
  image_url?: string;
  completed?: boolean;
  progress?: number;
}

export interface LessonCategory {
  id: string;
  name: string;
  description: string;
  lesson_count: number;
  icon?: string;
}
