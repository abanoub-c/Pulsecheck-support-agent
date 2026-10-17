import type { AnalyticsData, ApiError, ConversationSummary, CustomerDetail, CustomerRow, DashboardSummary, DemoCustomer, Escalation, Incident, SseEvent, ThreadRecord } from './types';
import { consumeEventStream } from './sse';

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '');
const apiUrl = (path: string) => `${API_BASE_URL}${path}`;

export class ApiRequestError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = 'ApiRequestError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: { ...(init?.body ? { 'Content-Type': 'application/json' } : {}), ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: 'Request failed.' })) as ApiError;
    throw new ApiRequestError(body.error || `Request failed (${response.status}).`, response.status);
  }
  return response.json() as Promise<T>;
}

export async function getHealth() {
  return request<{ status: string; agent_ready: boolean; mode: string }>('/api/health');
}
export async function getDemoCustomers() {
  const data = await request<{ items: Array<{ customer_id: string; company: string; tier: string; status: string; prompt: string }> }>('/api/demo/customers');
  return data.items as DemoCustomer[];
}
export async function getCustomerDetail(customerId: string) {
  return request<CustomerDetail>(`/api/customers/${encodeURIComponent(customerId)}`);
}
export async function getCustomers(params: { q?: string; status?: string; category?: string; sort?: string; dir?: string; page?: number; page_size?: number }) {
  const query = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)); });
  return request<{ items: CustomerRow[]; total: number; page: number; page_size: number }>(`/api/customers?${query.toString()}`);
}
export async function getAnalytics(days: number) {
  return request<AnalyticsData>(`/api/analytics/tickets?days=${days}`);
}
export async function getEscalations(status: 'pending' | 'resolved' = 'pending') {
  return request<{ items: Escalation[]; total: number }>(`/api/escalations?status=${status}`);
}
export async function getIncidents(status: 'open' | 'resolved' = 'open') {
  return request<{ items: Incident[]; total: number }>(`/api/incidents?status=${status}`);
}
export async function getDashboardSummary() {
  return request<DashboardSummary>('/api/dashboard/summary');
}
export async function getThread(threadId: string) {
  return request<ThreadRecord>(`/api/threads/${encodeURIComponent(threadId)}`);
}
export async function getCustomerConversations(customerId: string) {
  return request<{ items: ConversationSummary[] }>(`/api/customers/${encodeURIComponent(customerId)}/conversations`);
}
export async function postChat(input: { thread_id: string; customer_id: string; message_id: string; message: string }, onEvent: (event: SseEvent) => void, signal?: AbortSignal) {
  const response = await fetch(apiUrl('/api/chat'), { method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' }, body: JSON.stringify(input), signal });
  await consumeEventStream(response, onEvent);
}
export async function decideEscalation(escalationId: string, input: { action: 'approve' | 'edit' | 'reject'; customer_message?: string; note?: string }) {
  return request<{ status: string; escalation: Escalation }>(`/api/escalations/${encodeURIComponent(escalationId)}/decision`, { method: 'POST', body: JSON.stringify(input) });
}
export async function resetDemo() {
  return request<{ status: string; message?: string }>('/api/demo/reset', { method: 'POST', body: JSON.stringify({}) });
}
export function getThreadId(customerId: string) {
  const key = `pulsecheck-thread:${customerId}`;
  let id = sessionStorage.getItem(key);
  if (!id || !/^[A-Za-z0-9_-]{8,64}$/.test(id)) {
    id = crypto.randomUUID();
    sessionStorage.setItem(key, id);
  }
  return id;
}
export function clearThreadIds() {
  Object.keys(sessionStorage).filter((key) => key.startsWith('pulsecheck-thread:')).forEach((key) => sessionStorage.removeItem(key));
}
export function formatDate(value: string | null | undefined) {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}
export function daysUntil(value: string | null | undefined) {
  if (!value) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const date = new Date(value); date.setHours(0, 0, 0, 0);
  return Math.ceil((date.getTime() - today.getTime()) / 86400000);
}
