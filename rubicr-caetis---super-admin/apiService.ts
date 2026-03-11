/**
 * apiService.ts
 * ──────────────────────────────────────────────────────────────────────────
 * Typed API client that connects the Rubicr Caetis frontend to the
 * FastAPI backend running at http://localhost:8000.
 *
 * Usage:
 *   import api from './apiService';
 *   const companies = await api.getCompanies();
 */

import {
  CompanySummary,
  CompanyData,
  User,
  ApprovalRequest,
  EvidenceItem,
} from './types';

const BASE_URL = '';

// ── Token storage ─────────────────────────────────────────────────────────────

let _token: string | null = localStorage.getItem('rubicr_token');

export function setToken(token: string) {
  _token = token;
  localStorage.setItem('rubicr_token', token);
}

export function clearToken() {
  _token = null;
  localStorage.removeItem('rubicr_token');
}

// ── HTTP helper ────────────────────────────────────────────────────────────────

type Method = 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH';

async function request<T>(
  method: Method,
  path: string,
  body?: unknown,
  params?: Record<string, string>,
): Promise<T> {
  let url = `${BASE_URL}${path}`;
  if (params && Object.keys(params).length > 0) {
    const qs = new URLSearchParams(params).toString();
    url = `${url}?${qs}`;
  }

  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (_token) headers['Authorization'] = `Bearer ${_token}`;

  const res = await fetch(url, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 204) return undefined as unknown as T;

  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.detail ?? `HTTP ${res.status}`);
  }
  return data as T;
}

// ── Auth ──────────────────────────────────────────────────────────────────────

interface LoginResponse {
  access_token: string;
  token_type: string;
  user: { id: string; name: string; email: string; role: string };
}

export async function login(email: string, password: string): Promise<User> {
  const resp = await request<LoginResponse>('POST', '/api/auth/login', { email, password });
  setToken(resp.access_token);
  return {
    id: resp.user.id,
    name: resp.user.name,
    email: resp.user.email,
    role: resp.user.role as User['role'],
  };
}

export async function getMe(): Promise<User> {
  const u = await request<{ id: string; name: string; email: string; role: string }>('GET', '/api/auth/me');
  return { id: u.id, name: u.name, email: u.email, role: u.role as User['role'] };
}

// ── Companies ─────────────────────────────────────────────────────────────────

export async function getCompanies(): Promise<CompanySummary[]> {
  const list = await request<any[]>('GET', '/api/companies');
  return list.map(c => ({
    id: c.id,
    name: c.name,
    ticker: c.ticker,
    lei: c.lei,
    region: c.region,
    sector: c.sector,
    status: c.status,
    riskScores: c.riskScores,
    financialYear: c.financialYear,
    lastUpdated: c.lastUpdated,
  })) as CompanySummary[];
}

export async function getCompany(id: string, year?: string): Promise<CompanyData> {
  const params: Record<string, string> = {};
  if (year) params['year'] = year.replace('FY', '');
  const c = await request<any>('GET', `/api/companies/${id}`, undefined, params);
  return _mapCompanyDetail(c);
}

export async function addCompany(data: {
  name: string;
  lei?: string;
  ticker?: string;
  region?: string;
  sector?: string;
  nse_symbol?: string;
}): Promise<CompanySummary> {
  const c = await request<any>('POST', '/api/companies', data);
  return c as CompanySummary;
}

export async function deleteCompany(id: string): Promise<void> {
  await request<void>('DELETE', `/api/companies/${id}`);
}

export async function getCompanyYears(id: string): Promise<string[]> {
  const resp = await request<{ years: string[] }>('GET', `/api/companies/${id}/years`);
  return resp.years;
}

function _mapCompanyDetail(c: any): CompanyData {
  return {
    id: c.id,
    name: c.name,
    ticker: c.ticker,
    lei: c.lei,
    sector: c.sector,
    financialYear: c.financialYear,
    status: c.status,
    lastUpdated: c.lastUpdated,
    version: c.version,
    pillars: c.pillars,
    indicators: (c.indicators ?? []).map((i: any) => ({
      id: i.id,
      name: i.name,
      value: i.value,
      unit: i.unit,
      confidence: i.confidence,
      source: i.source,
      isOverridden: i.isOverridden,
      overrideReason: i.overrideReason,
      lastUpdated: i.lastUpdated,
    })),
    evidence: (c.evidence ?? []).map((e: any) => ({
      id: e.id,
      type: e.type,
      name: e.name,
      date: e.date,
      status: e.status,
      tags: e.tags ?? [],
    })),
  };
}

// ── Pipeline ──────────────────────────────────────────────────────────────────

export interface PipelineJob {
  id: string;
  company_id: string;
  company_name: string;
  year: number | null;
  status: string;
  error_msg?: string;
  started_at: string;
  finished_at?: string;
}

export async function runPipeline(config: {
  company_ids: string[];
  data_sources: string[];
  financial_years: string[];
  all_years?: boolean;
}): Promise<PipelineJob[]> {
  return request<PipelineJob[]>('POST', '/api/pipeline/run', config);
}

export async function getPipelineJobStatus(jobId: string): Promise<PipelineJob> {
  return request<PipelineJob>('GET', `/api/pipeline/status/${jobId}`);
}

export async function listPipelineJobs(): Promise<PipelineJob[]> {
  return request<PipelineJob[]>('GET', '/api/pipeline/jobs');
}

// ── Approvals ──────────────────────────────────────────────────────────────────

export async function getApprovals(statusFilter: string = 'PENDING'): Promise<ApprovalRequest[]> {
  const list = await request<any[]>('GET', '/api/approvals', undefined, { status_filter: statusFilter });
  return list.map(r => ({
    id: r.id,
    type: r.type,
    companyId: r.company_id,
    companyName: r.company_name,
    companyTicker: r.company_ticker,
    submittedBy: r.submitted_by,
    submittedAt: r.submitted_at,
    justification: r.justification,
    status: r.status,
    indicatorName: r.indicator_name,
    currentValue: r.current_value,
    newValue: r.new_value,
    sourceType: r.source_type,
    sourceName: r.source_name,
    sourceTags: r.source_tags ?? [],
  })) as ApprovalRequest[];
}

export async function submitOverride(data: {
  company_id: string;
  indicator_id: string;
  indicator_name: string;
  current_value: string | number;
  new_value: string | number;
  justification: string;
  submitted_by?: string;
}): Promise<ApprovalRequest> {
  const r = await request<any>('POST', '/api/approvals/override', data);
  return _mapApproval(r);
}

export async function submitSourceRequest(data: {
  company_id: string;
  source_type: string;
  source_name: string;
  source_tags: string[];
  justification: string;
  submitted_by?: string;
}): Promise<ApprovalRequest> {
  const r = await request<any>('POST', '/api/approvals/source', data);
  return _mapApproval(r);
}

export async function approveRequest(id: string, reviewed_by?: string): Promise<ApprovalRequest> {
  const r = await request<any>('PUT', `/api/approvals/${id}/approve`, { reviewed_by: reviewed_by ?? 'Admin' });
  return _mapApproval(r);
}

export async function rejectRequest(id: string, reason: string, reviewed_by?: string): Promise<ApprovalRequest> {
  const r = await request<any>('PUT', `/api/approvals/${id}/reject`, { reason, reviewed_by: reviewed_by ?? 'Admin' });
  return _mapApproval(r);
}

function _mapApproval(r: any): ApprovalRequest {
  return {
    id: r.id,
    type: r.type,
    companyId: r.company_id,
    companyName: r.company_name,
    companyTicker: r.company_ticker,
    submittedBy: r.submitted_by,
    submittedAt: r.submitted_at,
    justification: r.justification,
    status: r.status,
    indicatorName: r.indicator_name,
    currentValue: r.current_value,
    newValue: r.new_value,
    sourceType: r.source_type,
    sourceName: r.source_name,
    sourceTags: r.source_tags ?? [],
  };
}

// ── Evidence ──────────────────────────────────────────────────────────────────

export async function getEvidence(companyId: string): Promise<EvidenceItem[]> {
  const list = await request<any[]>('GET', `/api/companies/${companyId}/evidence`);
  return list.map(e => ({
    id: e.id, type: e.type, name: e.name,
    date: e.date, status: e.status, tags: e.tags ?? [],
  })) as EvidenceItem[];
}

export async function addEvidence(
  companyId: string,
  data: { type: string; name: string; tags: string[]; justification?: string; submitted_by?: string },
): Promise<EvidenceItem> {
  const e = await request<any>('POST', `/api/companies/${companyId}/evidence`, data);
  return { id: e.id, type: e.type, name: e.name, date: e.date, status: e.status, tags: e.tags ?? [] };
}

export async function deleteEvidence(companyId: string, evidenceId: string): Promise<void> {
  await request<void>('DELETE', `/api/companies/${companyId}/evidence/${evidenceId}`);
}

// ── Risk Config ────────────────────────────────────────────────────────────────

export interface DriverWeight {
  id: string;
  name: string;
  category: string;
  weight: number;
}

export async function getWeights(): Promise<DriverWeight[]> {
  return request<DriverWeight[]>('GET', '/api/config/weights');
}

export async function updateWeights(items: DriverWeight[]): Promise<DriverWeight[]> {
  return request<DriverWeight[]>('PUT', '/api/config/weights', items);
}

export async function getThresholds(): Promise<{ medium: number; high: number }> {
  return request('GET', '/api/config/thresholds');
}

export async function updateThresholds(t: { medium: number; high: number }): Promise<{ medium: number; high: number }> {
  return request('PUT', '/api/config/thresholds', t);
}

export interface DomainRule {
  id: string;
  domain: string;
  type: string;
  sub_type?: string;
  status: string;
  added_by: string;
  date: string;
}

export async function getDomains(): Promise<DomainRule[]> {
  return request<DomainRule[]>('GET', '/api/config/domains');
}

export async function addDomain(data: { domain: string; type: string; sub_type?: string }): Promise<DomainRule> {
  return request<DomainRule>('POST', '/api/config/domains', data);
}

export async function deleteDomain(id: string): Promise<void> {
  await request<void>('DELETE', `/api/config/domains/${id}`);
}

export async function toggleDomain(id: string): Promise<DomainRule> {
  return request<DomainRule>('PUT', `/api/config/domains/${id}/toggle`, {});
}

export async function getBlockedUrls(): Promise<{ id: string; url: string; date: string }[]> {
  return request('GET', '/api/config/blocked');
}

export async function blockUrls(urls: string[]): Promise<{ id: string; url: string; date: string }[]> {
  return request('POST', '/api/config/blocked', { urls });
}

export async function unblockUrl(id: string): Promise<void> {
  await request<void>('DELETE', `/api/config/blocked/${id}`);
}

const api = {
  login,
  getMe,
  getCompanies,
  getCompany,
  addCompany,
  deleteCompany,
  getCompanyYears,
  runPipeline,
  getPipelineJobStatus,
  listPipelineJobs,
  getApprovals,
  submitOverride,
  submitSourceRequest,
  approveRequest,
  rejectRequest,
  getEvidence,
  addEvidence,
  deleteEvidence,
  getWeights,
  updateWeights,
  getThresholds,
  updateThresholds,
  getDomains,
  addDomain,
  deleteDomain,
  toggleDomain,
  getBlockedUrls,
  blockUrls,
  unblockUrl,
};

export default api;
