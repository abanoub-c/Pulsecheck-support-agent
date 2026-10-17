import { Router, type Request, type Response } from 'express';
import { z } from 'zod';
import { analyticsQuerySchema, chatSchema, customerQuerySchema, decisionSchema } from '../middleware/validation.js';
import { decideEscalation, demoCustomers, getCustomerConversations, getCustomerDetail, getCustomers, getEscalations, getIncidents, getThread, getTickets, isDemoCustomer, resetDemo, runMockTurn } from '../services/mock-store.js';
import type { Customer, Subscription, Ticket } from '../types.js';

const router = Router();
const messageLimit = Number(process.env.RATE_LIMIT_MESSAGES_PER_HOUR ?? 30);
const maxChars = Number(process.env.MAX_MESSAGE_CHARS ?? 500);
const rateBuckets = new Map<string, { startedAt: number; count: number }>();
const lastThreadMessage = new Map<string, number>();
const useMock = () => process.env.MOCK_API !== 'false';

function limited(key: string, max: number, windowMs: number) {
  const now = Date.now();
  let bucket = rateBuckets.get(key);
  if (!bucket || now - bucket.startedAt >= windowMs) {
    bucket = { startedAt: now, count: 0 };
    rateBuckets.set(key, bucket);
  }
  bucket.count += 1;
  if (rateBuckets.size > 2000) {
    for (const [id, value] of rateBuckets) if (now - value.startedAt > windowMs * 2) rateBuckets.delete(id);
  }
  return bucket.count <= max;
}

function ipKey(req: Request) { return req.ip || req.socket.remoteAddress || 'unknown'; }
function sendValidationError(res: Response, error: z.ZodError) {
  res.status(400).json({ error: 'Invalid request', details: error.issues.map((issue) => ({ path: issue.path.join('.'), message: issue.message })) });
}
function agentUrl(pathAndQuery: string) {
  const base = process.env.AGENT_API_URL;
  if (!base) return null;
  const root = base.replace(/\/$/, '').replace(/\/api$/i, '');
  return `${root}/api/${pathAndQuery.replace(/^\/+/, '')}`;
}

function crmUrl(pathAndQuery: string) {
  const base = process.env.CRM_API_URL || (process.env.AGENT_API_URL ? `${process.env.AGENT_API_URL.replace(/\/$/, '').replace(/\/api$/i, '')}/crm` : '');
  if (!base) return null;
  const root = base.replace(/\/$/, '').replace(/\/crm$/i, '');
  return `${root}/crm/${pathAndQuery.replace(/^\/+/, '')}`;
}

function internalHeaders() {
  const key = process.env.INTERNAL_API_KEY;
  return key ? { 'x-internal-key': key } : {};
}

async function proxyJson(req: Request, res: Response, pathAndQuery: string, method = req.method, body?: unknown) {
  const url = agentUrl(pathAndQuery);
  if (!url) return res.status(503).json({ error: 'Agent service URL is not configured. Enable mock mode or configure AGENT_API_URL.' });
  try {
    const response = await fetch(url, {
      method,
      headers: { 'content-type': 'application/json', accept: req.header('accept') ?? 'application/json', ...internalHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(25_000),
    });
    const text = await response.text();
    res.status(response.status).type(response.headers.get('content-type') ?? 'application/json').send(text);
  } catch (error) {
    res.status(502).json({ error: 'The agent service could not be reached.', retryable: true });
  }
}

async function proxyDemoReset(res: Response) {
  const url = agentUrl('demo/reset');
  if (!url) return res.status(503).json({ error: 'AGENT_API_URL is not configured.' });
  try {
    const response = await fetch(url, { method: 'POST', headers: { ...internalHeaders() }, signal: AbortSignal.timeout(25_000) });
    const text = await response.text();
    if (response.ok) lastThreadMessage.clear();
    return res.status(response.status).type(response.headers.get('content-type') ?? 'application/json').send(text);
  } catch {
    return res.status(502).json({ error: 'The agent service could not be reached.', retryable: true });
  }
}

async function getCrmJson<T>(pathAndQuery: string): Promise<T> {
  const url = crmUrl(pathAndQuery);
  if (!url) throw new Error('CRM_API_URL is not configured.');
  const response = await fetch(url, { headers: { ...internalHeaders() }, signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new Error(`CRM request failed (${response.status}).`);
  return response.json() as Promise<T>;
}

async function crmCustomerExists(customerId: string) {
  const url = crmUrl(`customers/${encodeURIComponent(customerId)}`);
  if (!url) throw new Error('CRM_API_URL is not configured.');
  const response = await fetch(url, { headers: { ...internalHeaders() }, signal: AbortSignal.timeout(10_000) });
  if (response.status === 404) return false;
  if (!response.ok) throw new Error(`CRM customer lookup failed (${response.status}).`);
  return true;
}

function dateAtRuntime(value: string | null | undefined) {
  if (!value) return value ?? null;
  const source = Date.parse(value);
  if (!Number.isFinite(source)) return value;
  const today = new Date();
  const currentDay = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
  const referenceDay = Date.UTC(2026, 7, 25);
  const offset = currentDay - referenceDay;
  const shifted = new Date(source + offset);
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? shifted.toISOString().slice(0, 10) : shifted.toISOString();
}
function normalizeTicketDates(rows: Ticket[]) { return rows.map((row) => ({ ...row, created_at: dateAtRuntime(row.created_at) as string })); }
function normalizeCustomerDates(customer: Customer) { return { ...customer, signup_date: customer.signup_date }; }
function normalizeSubscriptionDates<T extends { next_billing_date?: string | null; trial_end_date?: string | null; cancelled_at?: string | null; created_at?: string }>(row: T) {
  return { ...row, next_billing_date: dateAtRuntime(row.next_billing_date), trial_end_date: dateAtRuntime(row.trial_end_date), cancelled_at: dateAtRuntime(row.cancelled_at), ...(row.created_at ? { created_at: dateAtRuntime(row.created_at) } : {}) };
}

router.get('/health', async (_req, res) => {
  if (useMock()) return res.json({ status: 'ok', agent_ready: true, mode: 'mock' });
  const url = agentUrl('health');
  if (!url) return res.json({ status: 'ok', agent_ready: false, mode: 'external' });
  try {
    const response = await fetch(url, { headers: { ...internalHeaders() }, signal: AbortSignal.timeout(3500) });
    const data = await response.json().catch(() => ({})) as Record<string, unknown>;
    const ready = response.ok && data.status === 'ok' && data.crm !== 'unreachable' && (data.agent_ready === true || data.agent === 'ready');
    return res.status(ready ? 200 : 503).json({ status: ready ? 'ok' : 'starting', agent_ready: ready, mode: 'external', crm: data.crm ?? 'unknown' });
  } catch {
    return res.status(503).json({ status: 'starting', agent_ready: false, mode: 'external' });
  }
});

router.post('/chat', async (req, res) => {
  const parsed = chatSchema.safeParse(req.body);
  if (!parsed.success) return sendValidationError(res, parsed.error);
  const input = parsed.data;
  if (input.message.length > maxChars) return res.status(413).json({ error: `Message must be ${maxChars} characters or fewer.` });
  if (useMock()) {
    if (!isDemoCustomer(input.customer_id)) return res.status(403).json({ error: 'This customer is not available for chat.' });
  } else {
    try {
      if (!await crmCustomerExists(input.customer_id)) return res.status(403).json({ error: 'This customer is not available for chat.' });
    } catch (error) {
      return res.status(502).json({ error: error instanceof Error ? error.message : 'Unable to validate this customer with the CRM.', retryable: true });
    }
  }
  if (!limited(`messages:${ipKey(req)}`, messageLimit, 60 * 60 * 1000)) return res.status(429).json({ error: 'Message limit reached. Try again later.' });
  const last = lastThreadMessage.get(input.thread_id) ?? 0;
  if (Date.now() - last < 650) return res.status(429).json({ error: 'Please wait a moment before sending another message.' });
  lastThreadMessage.set(input.thread_id, Date.now());

  if (!useMock()) {
    const url = agentUrl('chat');
    if (!url) return res.status(503).json({ error: 'AGENT_API_URL is not configured.' });
    try {
      const upstream = await fetch(url, { method: 'POST', headers: { 'content-type': 'application/json', accept: 'text/event-stream', ...internalHeaders() }, body: JSON.stringify(input), signal: AbortSignal.timeout(90_000) });
      res.status(upstream.status);
      res.setHeader('Content-Type', upstream.headers.get('content-type') ?? 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache, no-transform');
      res.setHeader('X-Accel-Buffering', 'no');
      if (!upstream.body) return res.end();
      const reader = upstream.body.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        res.write(Buffer.from(value));
      }
      return res.end();
    } catch {
      return res.status(502).json({ error: 'The agent service could not be reached.', retryable: true });
    }
  }

  let events;
  try { events = runMockTurn(input); }
  catch (error) { return res.status(409).json({ error: error instanceof Error ? error.message : 'Unable to process this thread.' }); }
  res.status(200);
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache, no-transform');
  res.setHeader('Connection', 'keep-alive');
  res.setHeader('X-Accel-Buffering', 'no');
  res.flushHeaders();
  for (const event of events) {
    if (res.destroyed) return;
    res.write(`event: ${event.event}\ndata: ${JSON.stringify(event.data)}\n\n`);
    await new Promise((resolve) => setTimeout(resolve, event.event === 'step' ? 260 : 90));
  }
  res.end();
});

router.get('/threads/:threadId', async (req, res) => {
  if (!useMock()) return proxyJson(req, res, `threads/${encodeURIComponent(req.params.threadId)}`, 'GET');
  const thread = getThread(req.params.threadId);
  if (!thread) return res.status(404).json({ error: 'Thread not found.' });
  return res.json(thread);
});

router.get('/escalations', async (req, res) => {
  if (!useMock()) {
    const url = agentUrl(`escalations?${new URLSearchParams({ status: String(req.query.status ?? 'pending') })}`);
    if (!url) return res.status(503).json({ error: 'AGENT_API_URL is not configured.' });
    try {
      const [payload, customers] = await Promise.all([
        fetch(url, { headers: { ...internalHeaders() }, signal: AbortSignal.timeout(15_000) }),
        getCrmJson<Array<{ customer_id: string; company_name: string }>>('customers'),
      ]);
      if (!payload.ok) return res.status(payload.status).type(payload.headers.get('content-type') ?? 'application/json').send(await payload.text());
      const rows = await payload.json() as Array<Record<string, unknown>>;
      const names = new Map(customers.map((customer) => [customer.customer_id, customer.company_name]));
      const items = rows.map((row) => ({
        ...row,
        reasoning: row.reasoning ?? 'human_review',
        reason_code: typeof row.reasoning === 'string' ? row.reasoning.split(' — ', 1)[0] : 'human_review',
        proposed_action: row.proposed_action && typeof row.proposed_action === 'object' ? row.proposed_action : {},
        customer_company_name: row.company_name ?? names.get(String(row.customer_id)) ?? String(row.customer_id),
      }));
      return res.json({ items, total: items.length });
    } catch (error) {
      return res.status(502).json({ error: error instanceof Error ? error.message : 'Unable to load escalations.', retryable: true });
    }
  }
  const status = req.query.status === 'resolved' ? 'resolved' : 'pending';
  const data = getEscalations().filter((row) => row.status === status).sort((a, b) => b.created_at.localeCompare(a.created_at));
  return res.json({ items: data, total: data.length });
});

router.get('/incidents', async (req, res) => {
  const parsed = z.object({ status: z.enum(['open', 'resolved']).optional().default('open') }).safeParse(req.query);
  if (!parsed.success) return sendValidationError(res, parsed.error);
  if (useMock()) {
    const items = getIncidents().filter((incident) => incident.status === parsed.data.status);
    return res.json({ items, total: items.length });
  }
  try {
    const payload = await getCrmJson<unknown[]>(`incidents?${new URLSearchParams({ status: parsed.data.status })}`);
    const items = Array.isArray(payload) ? payload : [];
    return res.json({ items, total: items.length });
  } catch (error) {
    return res.status(502).json({ error: error instanceof Error ? error.message : 'The CRM incident service could not be reached.', retryable: true });
  }
});

router.post('/escalations/:escalationId/decision', async (req, res) => {
  const parsed = decisionSchema.safeParse(req.body);
  if (!parsed.success) return sendValidationError(res, parsed.error);
  if (parsed.data.action === 'reject' && !parsed.data.note?.trim()) return res.status(400).json({ error: 'A short note is required when rejecting an escalation.' });
  if (parsed.data.action === 'edit' && !parsed.data.customer_message?.trim()) return res.status(400).json({ error: 'Add the edited message before sending.' });
  if (!useMock()) return proxyJson(req, res, `escalations/${encodeURIComponent(req.params.escalationId)}/decision`, 'POST', parsed.data);
  const record = decideEscalation({ escalationId: req.params.escalationId, action: parsed.data.action, customerMessage: parsed.data.customer_message, note: parsed.data.note });
  if (!record) return res.status(404).json({ error: 'Escalation not found.' });
  return res.json({ status: 'ok', escalation: record });
});

router.post('/demo/reset', (req, res) => {
  if (!limited(`reset:${ipKey(req)}`, 5, 60 * 60 * 1000)) return res.status(429).json({ error: 'Demo reset limit reached. Try again later.' });
  if (!useMock()) return proxyDemoReset(res);
  lastThreadMessage.clear();
  return res.json(resetDemo());
});

router.get('/dashboard/summary', async (req, res) => {
  if (!useMock()) return proxyJson(req, res, 'dashboard/summary', 'GET');
  const pending = getEscalations().filter((row) => row.status === 'pending');
  const incidents = getIncidents().filter((row) => row.status === 'open');
  return res.json({
    awaiting_review: pending.length,
    refunds_pending_review: pending.filter((row) => row.category === 'refund').length,
    open_incidents: incidents.length,
  });
});

function accountLabel(status: string): 'Active' | 'Inactive' | 'Pending' {
  if (status === 'active') return 'Active';
  if (status === 'cancelled') return 'Inactive';
  return 'Pending';
}
function assignedCategory(customerId: string, ticketRows: Ticket[]): string {
  const counts = new Map<string, number>();
  ticketRows.filter((ticket) => ticket.customer_id === customerId).forEach((ticket) => counts.set(ticket.category, (counts.get(ticket.category) ?? 0) + 1));
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))[0]?.[0] ?? 'other';
}

router.get('/customers', (req, res) => {
  const parsed = customerQuerySchema.safeParse(req.query);
  if (!parsed.success) return sendValidationError(res, parsed.error);
  if (!useMock()) {
    void (async () => {
      try {
        const customers = await getCrmJson<Array<Customer & { assigned_category?: string }>>('customers');
        let rows = customers.map((customer) => ({
          customer_id: customer.customer_id,
          company_name: customer.company_name,
          contact_name: customer.contact_name,
          contact_email: customer.contact_email,
          status: accountLabel(customer.account_status),
          assigned_category: customer.assigned_category ?? 'other',
          signup_date: customer.signup_date,
          plan: customer.tier,
        }));
        const query = parsed.data;
        const needle = query.q.trim().toLowerCase();
        if (needle) rows = rows.filter((row) => [row.customer_id, row.company_name, row.contact_name, row.contact_email].some((value) => value.toLowerCase().includes(needle)));
        if (query.status !== 'All') rows = rows.filter((row) => row.status === query.status);
        if (query.category !== 'All') rows = rows.filter((row) => row.assigned_category === query.category);
        const dir = query.dir === 'desc' ? -1 : 1;
        if (query.sort !== 'none') rows.sort((a, b) => String(a[query.sort] ?? '').localeCompare(String(b[query.sort] ?? ''), undefined, { numeric: true }) * dir);
        const total = rows.length;
        const start = (query.page - 1) * query.page_size;
        return res.json({ items: rows.slice(start, start + query.page_size), total, page: query.page, page_size: query.page_size });
      } catch (error) {
        return res.status(502).json({ error: error instanceof Error ? error.message : 'Unable to load clients.', retryable: true });
      }
    })();
    return;
  }
  const query = parsed.data;
  const ticketRows = normalizeTicketDates(getTickets());
  let rows = getCustomers().map((customer) => ({
    customer_id: customer.customer_id,
    company_name: customer.company_name,
    contact_name: customer.contact_name,
    contact_email: customer.contact_email,
    status: accountLabel(customer.account_status),
    assigned_category: assignedCategory(customer.customer_id, ticketRows),
    signup_date: customer.signup_date,
    plan: customer.tier,
    _account_status: customer.account_status,
  }));
  const needle = query.q.trim().toLowerCase();
  if (needle) rows = rows.filter((row) => [row.customer_id, row.company_name, row.contact_name, row.contact_email].some((value) => value.toLowerCase().includes(needle)));
  if (query.status !== 'All') rows = rows.filter((row) => row.status === query.status);
  if (query.category !== 'All') rows = rows.filter((row) => row.assigned_category === query.category);
  const sortKey = query.sort;
  const dir = query.dir === 'desc' ? -1 : 1;
  if (sortKey !== 'none') rows.sort((a, b) => String(a[sortKey] ?? '').localeCompare(String(b[sortKey] ?? ''), undefined, { numeric: true }) * dir);
  const total = rows.length;
  const start = (query.page - 1) * query.page_size;
  const items = rows.slice(start, start + query.page_size).map(({ _account_status: _discard, ...row }) => row);
  return res.json({ items, total, page: query.page, page_size: query.page_size });
});

router.get('/customers/:customerId/conversations', async (req, res) => {
  const customerId = String(req.params.customerId);
  if (!useMock()) return proxyJson(req, res, `customers/${encodeURIComponent(customerId)}/conversations`, 'GET');
  if (!isDemoCustomer(customerId)) return res.status(404).json({ error: 'Customer not found.' });
  return res.json({ items: getCustomerConversations(customerId) });
});

router.get('/customers/:customerId', async (req, res) => {
  if (!/^CUST-[A-Z0-9-]+$/i.test(req.params.customerId)) return res.status(400).json({ error: 'Invalid customer ID.' });
  if (!useMock()) {
    const id = encodeURIComponent(req.params.customerId);
    try {
      const [customer, subscription, ticketPayload] = await Promise.all([
        getCrmJson<Customer>(`customers/${id}`),
        getCrmJson<Subscription>(`subscriptions/${id}`),
        getCrmJson<Ticket[] | { items?: Ticket[] }>(`tickets?${new URLSearchParams({ customer_id: req.params.customerId, days: '30', limit: '6' })}`),
      ]);
      const recentTickets = Array.isArray(ticketPayload) ? ticketPayload : ticketPayload.items ?? [];
      return res.json({ customer: normalizeCustomerDates(customer), subscription: normalizeSubscriptionDates(subscription), recent_tickets: normalizeTicketDates(recentTickets), chat_allowed: true });
    } catch (error) {
      return res.status(502).json({ error: error instanceof Error ? error.message : 'The CRM customer service could not be reached.', retryable: true });
    }
  }
  const detail = getCustomerDetail(req.params.customerId);
  if (!detail) return res.status(404).json({ error: 'Customer not found.' });
  return res.json({
    customer: normalizeCustomerDates(detail.customer),
    subscription: detail.subscription ? normalizeSubscriptionDates(detail.subscription) : null,
    recent_tickets: normalizeTicketDates(detail.recent_tickets),
    chat_allowed: isDemoCustomer(req.params.customerId),
  });
});

router.get('/analytics/tickets', async (req, res) => {
  const parsed = analyticsQuerySchema.safeParse(req.query);
  if (!parsed.success) return sendValidationError(res, parsed.error);
  if (!useMock()) {
    try {
      const data = await getCrmJson<{ range_days: number; total: number; by_category: Array<{ category: string; total: number; solved: number; unsolved: number }> }>(`analytics/tickets?days=${parsed.data.days}`);
      return res.json(data);
    } catch (error) {
      return res.status(502).json({ error: error instanceof Error ? error.message : 'Unable to load ticket analytics.', retryable: true });
    }
  }
  const days = parsed.data.days;
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  const tickets = normalizeTicketDates(getTickets()).filter((ticket) => Date.parse(ticket.created_at) >= cutoff);
  const categories = ['billing', 'technical', 'refund', 'other'] as const;
  const by_category = categories.map((category) => {
    const matches = tickets.filter((ticket) => ticket.category === category);
    const solved = matches.filter((ticket) => ['resolved', 'closed', 'solved'].includes(ticket.status.toLowerCase())).length;
    return { category, total: matches.length, solved, unsolved: matches.length - solved };
  });
  return res.json({ range_days: days, total: tickets.length, by_category });
});

router.get('/demo/customers', async (_req, res) => {
  try {
    const rows = useMock() ? getCustomers() : await getCrmJson<Customer[]>('customers');
    const prompts = new Map(demoCustomers.map((customer) => [customer.customer_id, customer.prompt]));
    const items = rows.map((customer) => ({
      customer_id: customer.customer_id,
      company: customer.company_name,
      tier: customer.tier,
      status: customer.account_status,
      prompt: prompts.get(customer.customer_id) ?? `Could you help me with my ${customer.tier.toLowerCase()} subscription?`,
    }));
    return res.json({ items, total: items.length });
  } catch (error) {
    return res.status(502).json({ error: error instanceof Error ? error.message : 'Unable to load customers.', retryable: true });
  }
});
router.get('/demo/incidents', (_req, res) => res.json({ items: getIncidents() }));

export default router;
