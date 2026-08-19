export enum SourceType {
  PRIMARY_SCIENTIFIC = 'PRIMARY_SCIENTIFIC',
  SECONDARY_OPERATIONAL = 'SECONDARY_OPERATIONAL',
  AGENCY_PUBLIC_API = 'AGENCY_PUBLIC_API',
  LITERATURE = 'LITERATURE',
  EO_CATALOGUE = 'EO_CATALOGUE',
  BUNDLED_REFERENCE = 'BUNDLED_REFERENCE',
  CALCULATED = 'CALCULATED',
  SIMULATION = 'SIMULATION',
  EDITORIAL = 'EDITORIAL',
  USER_PROVIDED = 'USER_PROVIDED',
  UNKNOWN = 'UNKNOWN',
}

export enum FreshnessClass {
  REAL_TIME = 'REAL_TIME',
  NEAR_REAL_TIME = 'NEAR_REAL_TIME',
  RECENT = 'RECENT',
  HISTORICAL = 'HISTORICAL',
  STATIC = 'STATIC',
}

export interface SourceReference {
  source_name: string;
  source_type: SourceType;
  source_url?: string | null;
  source_record_id?: string | null;
  retrieved_at: string;
  source_timestamp?: string | null;
  source_version?: string | null;
  license?: string | null;
  attribution?: string | null;
}
