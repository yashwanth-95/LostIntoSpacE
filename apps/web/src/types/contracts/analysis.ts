import type { Citation, ConfidenceLevel, ContextItem } from './ai';
import type { SourceReference } from './provenance';

export enum FailureSeverity {
  INFO = 'info',
  WARNING = 'warning',
  CRITICAL = 'critical',
  FATAL = 'fatal',
}

export enum SubsystemKind {
  PROPULSION = 'PROPULSION',
  STRUCTURE = 'STRUCTURE',
  AERODYNAMICS = 'AERODYNAMICS',
  GUIDANCE = 'GUIDANCE',
  STAGING = 'STAGING',
  MASS_PROPERTIES = 'MASS_PROPERTIES',
  TRAJECTORY = 'TRAJECTORY',
  STABILITY = 'STABILITY',
  UNKNOWN = 'UNKNOWN',
}

export interface SimulationObservation {
  statement: string;
  time_s?: number | null;
  event_type?: string | null;
  severity?: FailureSeverity | null;
  values: Record<string, unknown>;
  phase?: string | null;
}

export interface ScientificExplanation {
  statement: string;
  citations: Citation[];
  is_inference: boolean;
}

export interface Mitigation {
  action: string;
  rationale: string;
  subsystem: SubsystemKind;
  citations: Citation[];
  is_heuristic: boolean;
}

export interface FailureAnalysis {
  simulation_id?: string | null;
  summary: string;
  observations: SimulationObservation[];
  explanation: ScientificExplanation[];
  likely_cause?: string | null;
  cause_confidence: ConfidenceLevel;
  affected_subsystems: SubsystemKind[];
  affected_components: string[];
  consequences: string[];
  mitigations: Mitigation[];
  uncertainty: string[];
  simulation_limitations: string[];
  sources: SourceReference[];
  context_items: ContextItem[];
  generated_at: string;
  diagnostics: Record<string, unknown>;
}

export interface MissionTimelineEntry {
  label: string;
  date?: string | null;
  when?: string | null;
  description?: string | null;
  citations: Citation[];
}

export interface SourceConflict {
  field: string;
  values: Record<string, string>;
  note: string;
}

export interface MissionSummary {
  canonical_id?: string | null;
  name: string;
  summary: string;
  agency?: string | null;
  scientific_objectives: string[];
  timeline: MissionTimelineEntry[];
  spacecraft: string[];
  launch_vehicle?: string | null;
  destinations: string[];
  major_events: string[];
  outcome?: string | null;
  scientific_findings: string[];
  citations: Citation[];
  sources: SourceReference[];
  conflicts: SourceConflict[];
  unknown_fields: string[];
  confidence: ConfidenceLevel;
  generated_at: string;
}
