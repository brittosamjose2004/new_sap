export enum RiskLevel {
  LOW = 'LOW',
  MEDIUM = 'MEDIUM',
  HIGH = 'HIGH',
  CRITICAL = 'CRITICAL'
}

export type PipelineStatus = 'QUEUED' | 'FETCHING' | 'SCORING' | 'NEEDS_REVIEW' | 'PUBLISHED' | 'ERROR';
export type Region = 'NA' | 'EU' | 'APAC' | 'LATAM' | 'EMEA';

export interface CompanySummary {
  id: string;
  name: string;
  ticker: string;
  lei: string;
  region: Region;
  sector: string;
  status: PipelineStatus;
  riskScores: {
    s: number; // Sustainability
    p: number; // PCHI
    o: number; // Operational
    f: number; // Financial
  };
  financialYear: string;
  lastUpdated: string;
}

export interface Driver {
  id: string;
  name: string;
  impact: number; // 0-100 impact on the score
}

export interface RiskPillar {
  id: string;
  name: string;
  score: number; // 0-100
  trend: 'up' | 'down' | 'stable';
  trendValue: number;
  drivers: Driver[];
}

export interface PendingSource {
  type: 'PDF' | 'URL' | 'CSV';
  value: string; // URL or filename
  tags: string[];
  justification: string;
  submittedAt: string;
  submittedBy: string;
}

export interface EvidenceItem {
  id: string;
  type: 'PDF' | 'URL' | 'NEWS' | 'CSV';
  name: string;
  date: string;
  status: 'processed' | 'processing' | 'error' | 'pending_review';
  tags: string[];
  pendingSource?: PendingSource;
}

export interface PendingOverride {
  newValue: string | number;
  evidenceType: 'PDF' | 'URL' | 'FILE';
  evidenceValue: string; // URL or filename
  justification: string;
  submittedAt: string;
  submittedBy: string;
}

export type ApprovalRequestType = 'OVERRIDE' | 'SOURCE';

export interface ApprovalRequest {
  id: string;
  type: ApprovalRequestType;
  companyId: string;
  companyName: string;
  companyTicker: string;
  submittedBy: string;
  submittedAt: string;
  justification: string;
  status: 'PENDING' | 'APPROVED' | 'REJECTED';
  
  // For Overrides
  indicatorName?: string;
  currentValue?: string | number;
  newValue?: string | number;
  
  // For Sources
  sourceType?: 'PDF' | 'URL' | 'CSV';
  sourceName?: string;
  sourceTags?: string[];
}

export type AuditLogEventType = 'SYSTEM_EXTRACTION' | 'MAKER_PROPOSAL' | 'CHECKER_APPROVAL' | 'SOURCE_ADDITION';

export interface AuditLogEvent {
  id: string;
  type: AuditLogEventType;
  timestamp: string;
  user?: string; // "System" or User Name
  description: string;
  metadata?: {
    previousValue?: string | number;
    newValue?: string | number;
    sourceName?: string;
    reason?: string;
  };
}

export interface Indicator {
  id: string;
  name: string;
  value: string | number;
  unit: string;
  confidence: number; // 0-100
  source: string;
  isOverridden: boolean;
  overrideReason?: string;
  pendingOverride?: PendingOverride;
  lastUpdated: string;
  auditLog?: AuditLogEvent[];
}

export interface CompanyData {
  id: string;
  name: string;
  ticker: string;
  lei: string;
  sector: string;
  financialYear: string;
  status: 'LIVE' | 'DRAFT' | 'REVIEW';
  lastUpdated: string;
  version: string;
  pillars: {
    sustainability: RiskPillar;
    pchi: RiskPillar;
    operational: RiskPillar;
    financial: RiskPillar;
  };
  indicators: Indicator[];
  evidence: EvidenceItem[];
}

export type UserRole = 'ADMIN' | 'OPERATIONS_MANAGER';

export interface User {
  id: string;
  name: string;
  email: string;
  role: UserRole;
}
