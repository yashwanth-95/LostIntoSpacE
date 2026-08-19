import type { FreshnessClass, SourceReference, SourceType } from './provenance';

export enum SearchEntityType {
  SPACE_OBJECT = 'SPACE_OBJECT',
  MISSION = 'MISSION',
  LESSON = 'LESSON',
  CONCEPT = 'CONCEPT',
  DOCUMENT = 'DOCUMENT',
  EVENT = 'EVENT',
  EO_PRODUCT = 'EO_PRODUCT',
  REFERENCE = 'REFERENCE',
  UNKNOWN = 'UNKNOWN',
}

export enum MatchType {
  EXACT = 'EXACT',
  ALIAS = 'ALIAS',
  PREFIX = 'PREFIX',
  PARTIAL = 'PARTIAL',
  SEMANTIC = 'SEMANTIC',
}

export enum SearchStatus {
  OK = 'OK',
  EMPTY = 'EMPTY',
  NO_RELIABLE_MATCH = 'NO_RELIABLE_MATCH',
}

export enum SortOrder {
  RELEVANCE = 'RELEVANCE',
  NEWEST = 'NEWEST',
  OLDEST = 'OLDEST',
  TITLE = 'TITLE',
}

export interface SearchQuery {
  text: string;
  entity_types: SearchEntityType[];
  sources: string[];
  source_types: SourceType[];
  object_types: string[];
  missions: string[];
  topics: string[];
  start_date?: string | null;
  end_date?: string | null;
  limit: number;
  offset: number;
  sort: SortOrder;
  min_score: number;
  include_stale: boolean;
  include_facets: boolean;
}

export interface ResultProvenance {
  sources: SourceReference[];
  attribution: string[];
  freshness_class?: FreshnessClass | null;
  may_present_as_live: boolean;
  caveat?: string | null;
  retrieved_at?: string | null;
}

export interface SearchResult {
  id: string;
  entity_type: SearchEntityType;
  title: string;
  summary?: string | null;
  score: number;
  match_type: MatchType;
  matched_fields: string[];
  provenance: ResultProvenance;
  object_type?: string | null;
  topics: string[];
  mission_ids: string[];
  date?: string | null;
  url?: string | null;
  metadata: Record<string, unknown>;
}

export interface SearchFacet {
  name: string;
  counts: Record<string, number>;
}

export interface SearchResponse {
  query: SearchQuery;
  status: SearchStatus;
  results: SearchResult[];
  total: number;
  offset: number;
  limit: number;
  took_ms?: number | null;
  facets: SearchFacet[];
  explanation?: string | null;
  suggestions: string[];
}
