import type { FreshnessClass, SourceReference, SourceType } from './provenance';

export enum DataOrigin {
  LIVE = 'LIVE',
  CACHED = 'CACHED',
  STATIC = 'STATIC',
  SIMULATED = 'SIMULATED',
  MODEL_KNOWLEDGE = 'MODEL_KNOWLEDGE',
  MIXED = 'MIXED',
}

export enum ConfidenceLevel {
  HIGH = 'HIGH',
  MEDIUM = 'MEDIUM',
  LOW = 'LOW',
  INSUFFICIENT_EVIDENCE = 'INSUFFICIENT_EVIDENCE',
}

export enum ClaimType {
  OBSERVATION = 'OBSERVATION',
  MEASURED_VALUE = 'MEASURED_VALUE',
  DERIVED_VALUE = 'DERIVED_VALUE',
  ESTIMATE = 'ESTIMATE',
  THEORY = 'THEORY',
  SIMULATION = 'SIMULATION',
  AI_INFERENCE = 'AI_INFERENCE',
}

export interface ContextItem {
  ref: string;
  canonical_id: string;
  title: string;
  content: string;
  source: SourceReference;
  source_type: SourceType;
  url?: string | null;
  timestamp?: string | null;
  retrieved_at?: string | null;
  freshness_class?: FreshnessClass | null;
  relevance: number;
  may_present_as_live: boolean;
  staleness_note?: string | null;
}

export interface Citation {
  ref: string;
  canonical_id?: string | null;
  claim: string;
  claim_type: ClaimType;
  source?: SourceReference | null;
  url?: string | null;
  verified: boolean;
}

export interface AnswerLimitation {
  kind: string;
  detail: string;
}

export interface AIResponse {
  answer: string;
  confidence: ConfidenceLevel;
  data_origin: DataOrigin;
  citations: Citation[];
  sources: SourceReference[];
  context_items: ContextItem[];
  freshness?: FreshnessClass | null;
  freshness_note?: string | null;
  limitations: AnswerLimitation[];
  related_topics: string[];
  suggested_questions: string[];
  insufficient_evidence: boolean;
  evidence_gap?: string | null;
  model_id?: string | null;
  generated_at: string;
  latency_ms?: number | null;
  diagnostics: Record<string, unknown>;
}

export interface ConversationTurn {
  id?: string | null;
  role: 'user' | 'assistant';
  content: string;
  response?: AIResponse | null;
  created_at: string;
}

export interface Conversation {
  id?: string | null;
  user_id?: string | null;
  project_id?: string | null;
  title?: string | null;
  turns: ConversationTurn[];
  created_at: string;
  updated_at?: string | null;
}
