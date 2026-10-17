import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import type {
  AgentEvent, Category, Customer, DecisionAction, Escalation, Incident,
  Subscription, ThreadMessage, ThreadRecord, ThreadState, Ticket, ToolCall, TraceStep,
} from '../types.js';

type SeedFixture = {
  reference_date: string;
  tiers: Record<string, { monitor_limit: number; price_monthly: number }>;
  customers: Customer[];
  subscriptions: Subscription[];
  tickets: Ticket[];
  incidents: Incident[];
};

const fixturePath = path.join(process.cwd(), 'server/data/seed-data.json');
const fixture = JSON.parse(readFileSync(fixturePath, 'utf8')) as SeedFixture;
const CHAT_PROMPTS: Record<string, { company: string; tier: string; status: string; prompt: string }> = {
  'CUST-0006': { company: 'Crestpoint Systems', tier: 'Business', status: 'active', prompt: "We've consolidated services and only need about 20 monitors now. Can you switch us down to the Team plan?" },
  'CUST-0002': { company: 'Vertex Cloud Systems', tier: 'Team', status: 'active', prompt: "We're running out of monitors. Can we upgrade to Business?" },
  'CUST-0022': { company: 'Kestrel Systems', tier: 'Starter', status: 'active', prompt: 'I want a refund of $15 for the bad first week.' },
  'CUST-0012': { company: 'Halcyon Cloud', tier: 'Business', status: 'past_due', prompt: "I want a refund for last month's Business plan charge." },
  'CUST-0005': { company: 'Ferroline Technologies', tier: 'Team', status: 'past_due', prompt: "My card was declined and I can't figure out how to update my payment info." },
  'CUST-0014': { company: 'Quicksilver APIs', tier: 'Team', status: 'active', prompt: 'One of our monitors keeps flapping between up and down.' },
  'CUST-0019': { company: 'Hollowbrook Tech', tier: 'Team', status: 'active', prompt: "We're getting paged twice for every incident through PagerDuty." },
  'CUST-0010': { company: 'Solace Systems', tier: 'Starter', status: 'trialing', prompt: "We're still in our trial and decided Pulsecheck isn't for us. Can you confirm we won't be charged?" },
};

const initialState = (): ThreadState => ({
  category: null,
  pending_categories: [],
  confidence: null,
  clarify_attempts: 0,
  turn_count: 0,
  resolution_status: 'open',
  escalation_reason: null,
});

let customers: Customer[] = [];
let subscriptions: Subscription[] = [];
let tickets: Ticket[] = [];
let incidents: Incident[] = [];
let threads = new Map<string, ThreadRecord>();
let escalations = new Map<string, Escalation>();

function buildInitialEscalation() {
  const customer = customers.find((row) => row.customer_id === 'CUST-0012');
  if (!customer) return;
  const threadId = 'demo-thread-cust-0012';
  const now = new Date().toISOString();
  const prompt = CHAT_PROMPTS['CUST-0012'].prompt;
  const steps: TraceStep[] = [
    { id: randomUUID(), at: now, node: 'context_manager', kind: 'context', title: 'Context loaded', detail: { customer_id: customer.customer_id, company: customer.company_name } },
    { id: randomUUID(), at: now, node: 'router', kind: 'classification', title: 'Refund request classified', detail: { categories: ['refund'], confidence: 0.94, reasoning: 'The customer requested a refund for a specific monthly plan charge.', wants_human: false, is_smalltalk: false } },
    { id: randomUUID(), at: now, node: 'refund', kind: 'tool_call', title: 'Refund amount requires review', detail: { tool: 'prepare_refund', args: { customer_id: customer.customer_id, amount: 299 } } },
    { id: randomUUID(), at: now, node: 'escalate', kind: 'escalation', title: 'Manager review required', detail: { reason: 'refund_exceeds_threshold', escalation_id: 'ESC-DEMO-299' } },
  ];
  const state: ThreadState = { ...initialState(), category: 'refund', confidence: 0.94, resolution_status: 'escalated', escalation_reason: 'refund_exceeds_threshold' };
  threads.set(threadId, {
    thread_id: threadId,
    customer_id: customer.customer_id,
    status: 'escalated',
    messages: [
      { id: randomUUID(), role: 'user', content: prompt, at: now },
      { id: randomUUID(), role: 'assistant', content: 'I prepared a $299 refund request for manager review. No refund has been issued yet.', at: now, trace: { steps, toolCalls: [{ id: randomUUID(), tool: 'prepare_refund', args: { customer_id: customer.customer_id, amount: 299 }, result: { status: 'pending_review', amount: 299 }, ok: true, duration_ms: 318 }], state, startedAt: now, finishedAt: now } },
    ],
    state,
    steps,
    updated_at: now,
  });
  escalations.set('ESC-DEMO-299', {
    escalation_id: 'ESC-DEMO-299', customer_id: customer.customer_id, ticket_id: 'TICK-DEMO-299',
    category: 'refund', confidence: 0.94, reasoning: 'refund_exceeds_threshold',
    proposed_action: { tool: 'issue_refund', args: { customer_id: customer.customer_id, amount: 299, currency: 'USD' }, status: 'pending_review' },
    conversation_summary: 'The customer requested a refund for last month’s Business plan charge. The agent prepared the request but has not issued a refund.',
    status: 'pending', decision: null, decision_note: null, customer_message: 'I have prepared your $299 refund request. A manager is reviewing it before any refund is issued.',
    created_at: now, resolved_at: null, thread_id: threadId, customer_company_name: customer.company_name,
  });
}

function seed() {
  customers = structuredClone(fixture.customers);
  subscriptions = structuredClone(fixture.subscriptions);
  tickets = structuredClone(fixture.tickets);
  incidents = structuredClone(fixture.incidents);
  threads = new Map();
  escalations = new Map();
  buildInitialEscalation();
}
seed();

export const demoCustomers = Object.entries(CHAT_PROMPTS).map(([customer_id, details]) => ({ customer_id, ...details }));
export const isDemoCustomer = (id: string) => customers.some((customer) => customer.customer_id === id);
export const getCustomers = () => customers;
export const getSubscriptions = () => subscriptions;
export const getTickets = () => tickets;
export const getIncidents = () => incidents;
export const getThread = (id: string) => threads.get(id);
export const getCustomerConversations = (customerId: string) => [...threads.values()]
  .filter((thread) => thread.customer_id === customerId && thread.messages.length > 0)
  .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
  .map((thread) => {
    const firstUserMessage = thread.messages.find((message) => message.role === 'user')?.content ?? 'Support conversation';
    return {
      thread_id: thread.thread_id,
      customer_id: thread.customer_id,
      title: firstUserMessage.replace(/\s+/g, ' ').slice(0, 180),
      status: thread.status,
      message_count: thread.messages.length,
      last_message_preview: thread.messages.at(-1)?.content.slice(0, 180) ?? '',
      created_at: thread.messages[0]?.at ?? thread.updated_at,
      updated_at: thread.updated_at,
    };
  });
export const getEscalations = () => [...escalations.values()];

export function getCustomerDetail(id: string) {
  const customer = customers.find((row) => row.customer_id === id);
  if (!customer) return null;
  const subscription = subscriptions.find((row) => row.customer_id === id) ?? null;
  const recentTickets = tickets.filter((row) => row.customer_id === id).slice(0, 6);
  return { customer, subscription, recent_tickets: recentTickets };
}

export function resetDemo() {
  seed();
  return { status: 'ok', message: 'Synthetic demo data restored.' };
}

function addStep(thread: ThreadRecord, trace: TraceStep[], node: string, kind: string, title: string, detail: unknown) {
  const step: TraceStep = { id: randomUUID(), at: new Date().toISOString(), node, kind, title, detail };
  trace.push(step);
  thread.steps.push(step);
  return step;
}

function addTool(trace: ToolCall[], tool: string, args: Record<string, unknown>, result: unknown, ok = true) {
  trace.push({ id: randomUUID(), tool, args, result, ok, duration_ms: 140 + Math.round(Math.random() * 260) });
}

function snapshot(thread: ThreadRecord): ThreadState {
  return structuredClone(thread.state);
}

function remainingBillingDays(value: string | null | undefined) {
  if (!value) return 0;
  const parsed = Date.parse(value);
  const reference = Date.parse(`${fixture.reference_date}T00:00:00Z`);
  if (!Number.isFinite(parsed) || !Number.isFinite(reference)) return 0;
  const now = new Date();
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  const due = new Date(parsed + today - reference);
  while (due.getTime() <= now.getTime()) due.setUTCMonth(due.getUTCMonth() + 1);
  const dueDay = Date.UTC(due.getUTCFullYear(), due.getUTCMonth(), due.getUTCDate());
  return Math.min(30, Math.max(0, Math.ceil((dueDay - today) / 86_400_000)));
}

function ensureThread(threadId: string, customerId: string): ThreadRecord {
  const existing = threads.get(threadId);
  if (existing) {
    if (existing.customer_id !== customerId) throw new Error('Thread/customer mismatch');
    return existing;
  }
  const thread: ThreadRecord = { thread_id: threadId, customer_id: customerId, status: 'open', messages: [], state: initialState(), steps: [], updated_at: new Date().toISOString() };
  threads.set(threadId, thread);
  return thread;
}

function createEscalation(thread: ThreadRecord, category: Category, confidence: number, reason: string, action: Record<string, unknown>, summary: string) {
  const customer = customers.find((row) => row.customer_id === thread.customer_id)!;
  const escalationId = `ESC-${randomUUID().slice(0, 8).toUpperCase()}`;
  const record: Escalation = {
    escalation_id: escalationId, customer_id: thread.customer_id, ticket_id: `TICK-${randomUUID().slice(0, 8).toUpperCase()}`,
    category, confidence, reasoning: reason, proposed_action: action, conversation_summary: summary,
    status: 'pending', decision: null, decision_note: null, customer_message: 'A human specialist is reviewing your request.',
    created_at: new Date().toISOString(), resolved_at: null, thread_id: thread.thread_id, customer_company_name: customer.company_name,
  };
  escalations.set(escalationId, record);
  thread.status = 'escalated';
  thread.state.resolution_status = 'escalated';
  thread.state.escalation_reason = reason;
  return record;
}

function makeEvent(event: AgentEvent['event'], data: Record<string, unknown>): AgentEvent { return { event, data }; }

export function runMockTurn(input: { thread_id: string; customer_id: string; message: string }): AgentEvent[] {
  const { thread_id: threadId, customer_id: customerId, message } = input;
  const customer = customers.find((row) => row.customer_id === customerId);
  if (!customer || !isDemoCustomer(customerId)) throw new Error('Customer is not available for chat.');
  const thread = ensureThread(threadId, customerId);
  if (thread.status === 'escalated') throw new Error('This thread is waiting for a human specialist.');
  const start = new Date().toISOString();
  const text = message.trim();
  thread.messages.push({ id: randomUUID(), role: 'user', content: text, at: start });
  thread.state.turn_count += 1;
  thread.updated_at = start;

  const traceSteps: TraceStep[] = [];
  const toolCalls: ToolCall[] = [];
  const events: AgentEvent[] = [];
  const emitStep = (node: string, kind: string, title: string, detail: unknown) => {
    const step = addStep(thread, traceSteps, node, kind, title, detail);
    events.push(makeEvent('step', step as unknown as Record<string, unknown>));
  };
  const tools = (tool: string, args: Record<string, unknown>, result: unknown, ok = true) => addTool(toolCalls, tool, args, result, ok);
  const normalized = text.toLowerCase();
  const greeting = /^(hi|hello|hey|good morning|good afternoon|good evening)[!.\s]*$/i.test(text);
  const humanAsk = /\b(human|person|representative|agent please|talk to someone)\b/i.test(text);
  const vague = /^(help|it doesn't work|something is wrong|not sure|can you help)[!.\s]*$/i.test(text);
  const toolFailure = /simulate (a )?tool failure|tool error|test error recovery/i.test(text);
  const isDowngrade = customerId === 'CUST-0006' && /team|downgrad/i.test(normalized);
  const isUpgrade = customerId === 'CUST-0002' && /business|upgrad/i.test(normalized);
  const asksRefund = /refund/i.test(normalized) || Boolean(thread.pending_refund_amount);
  const refundMatch = normalized.match(/\$\s?(\d+(?:\.\d{1,2})?)/);
  const explicitRefundAmount = refundMatch ? Number(refundMatch[1]) : (customerId === 'CUST-0022' && /15/.test(normalized) ? 15 : null);
  const isCancel = /cancel|cancell|won't be charged|not be charged/i.test(normalized);
  const isTechnical = /monitor|flap|pagerduty|webhook|incident|alert/i.test(normalized);
  const isGoodwill = /(goodwill|credit).*(downtime|outage)|(?:downtime|outage).*(credit|goodwill)/i.test(normalized);
  const clarificationAnswer = thread.state.clarify_attempts > 0 && /^(about\s+)?(billing|technical|refund)\b/i.test(text.trim());
  const acceptRetentionOffer = Boolean(thread.pending_retention_offer) && /accept (the )?(discount|offer)|keep my account/i.test(normalized);
  const confirmCancellation = Boolean(thread.pending_cancel_confirmation) && /\b(yes|confirm|confirmed)\b/i.test(normalized) && /cancel|cancellation|subscription/i.test(normalized);

  emitStep('context_manager', 'context', 'Customer context loaded', { customer_id: customerId, company: customer.company_name, account_status: customer.account_status });

  if (greeting) {
    thread.state.category = 'other'; thread.state.confidence = 0.99; thread.state.resolution_status = 'resolved'; thread.status = 'resolved';
    emitStep('router', 'classification', 'Greeting recognized', { categories: ['other'], confidence: 0.99, reasoning: 'This is a greeting and can use a canned reply.', is_smalltalk: true });
    emitStep('dispatch', 'dispatch', 'Canned response selected', { category: 'other' });
    events.push(makeEvent('message', { role: 'assistant', content: `Hello! I’m here to help ${customer.company_name}. What can I help you with today?` }));
  } else if (humanAsk) {
    thread.state.category = 'other'; thread.state.confidence = 0.98;
    emitStep('router', 'classification', 'Human requested', { categories: ['other'], confidence: 0.98, reasoning: 'The customer explicitly asked to speak with a person.', wants_human: true });
    emitStep('dispatch', 'dispatch', 'Escalating to a human specialist', { category: 'other' });
    const escalation = createEscalation(thread, 'other', 0.98, 'customer_requested_human', { type: 'human_handoff' }, 'The customer asked to speak with a human specialist.');
    emitStep('escalate', 'escalation', 'Human review requested', { reason: 'customer_requested_human', escalation_id: escalation.escalation_id });
    events.push(makeEvent('escalated', { escalation_id: escalation.escalation_id, reason: 'customer_requested_human' }));
    events.push(makeEvent('message', { role: 'assistant', content: 'I’ve passed this conversation to a human specialist. They’ll review your request and reply here.' }));
  } else if (acceptRetentionOffer) {
    const sub = subscriptions.find((row) => row.customer_id === customerId);
    if (!sub) {
      events.push(makeEvent('message', { role: 'assistant', content: 'I could not find an active subscription to update. I have not changed your account.' }));
    } else {
      const expires = new Date(); expires.setMonth(expires.getMonth() + 3);
      sub.discount_percent = 10; sub.discount_expires_at = expires.toISOString(); sub.retention_offer_used = true;
      thread.pending_retention_offer = false; thread.pending_cancel_confirmation = false;
      thread.state.category = 'billing'; thread.state.confidence = 0.96; thread.state.resolution_status = 'resolved'; thread.status = 'resolved';
      emitStep('router', 'classification', 'Retention offer accepted', { categories: ['billing'], confidence: 0.96, reasoning: 'The customer accepted the offered 10% discount for three months.' });
      emitStep('dispatch', 'dispatch', 'Billing specialist selected', { category: 'billing' });
      emitStep('billing', 'tool_call', 'Retention discount applied', { tool: 'apply_discount', args: { customer_id: customerId, percent: 10, months: 3 } });
      tools('apply_discount', { customer_id: customerId, percent: 10, months: 3 }, { status: 'applied', percent: 10, months: 3 });
      emitStep('billing_tools', 'tool_result', 'Discount applied', { tool: 'apply_discount', ok: true, result: { percent: 10, months: 3 } });
      events.push(makeEvent('message', { role: 'assistant', content: 'Your 10% retention discount has been applied for the next 3 months. No plan change or cancellation was made.' }));
    }
  } else if (confirmCancellation) {
    const sub = subscriptions.find((row) => row.customer_id === customerId);
    if (!sub) {
      events.push(makeEvent('message', { role: 'assistant', content: 'I could not find an active subscription to cancel. I have not changed your account.' }));
    } else {
      sub.status = 'cancelled'; sub.cancelled_at = new Date().toISOString(); customer.account_status = 'cancelled';
      thread.pending_cancel_confirmation = false; thread.pending_retention_offer = false;
      thread.state.category = 'billing'; thread.state.confidence = 0.98; thread.state.resolution_status = 'resolved'; thread.status = 'resolved';
      emitStep('router', 'classification', 'Cancellation confirmed', { categories: ['billing'], confidence: 0.98, reasoning: 'The customer explicitly confirmed cancellation.' });
      emitStep('dispatch', 'dispatch', 'Billing specialist selected', { category: 'billing' });
      emitStep('billing', 'tool_call', 'Subscription cancelled', { tool: 'cancel_subscription', args: { customer_id: customerId } });
      tools('cancel_subscription', { customer_id: customerId }, { status: 'cancelled', future_billing_stopped: true });
      emitStep('billing_tools', 'tool_result', 'Cancellation recorded', { tool: 'cancel_subscription', ok: true, result: { status: 'cancelled' } });
      events.push(makeEvent('message', { role: 'assistant', content: 'Your subscription has been cancelled and future billing has stopped. No refund was issued.' }));
    }
  } else if (clarificationAnswer) {
    const category = normalized.includes('refund') ? 'refund' : normalized.includes('technical') ? 'technical' : 'billing';
    thread.state.category = category; thread.state.pending_categories = []; thread.state.confidence = 0.84; thread.state.resolution_status = 'open'; thread.status = 'open';
    emitStep('router', 'classification', 'Clarified intent reclassified', { categories: [category], confidence: 0.84, reasoning: 'The customer selected a category in response to the one allowed clarifying question.' });
    emitStep('dispatch', 'dispatch', `${category[0].toUpperCase()}${category.slice(1)} specialist selected`, { category });
    const tool = category === 'technical' ? 'check_known_incidents' : category === 'refund' ? 'get_invoice_history' : 'get_subscription';
    const result = category === 'technical' ? { open_incidents: incidents.filter((row) => row.status === 'open').length } : category === 'refund' ? { invoice_history_available: true } : { plan: customer.tier, account_status: customer.account_status };
    emitStep(`${category}_tools`, 'tool_call', 'Account context checked', { tool, args: { customer_id: customerId } });
    tools(tool, { customer_id: customerId }, result);
    emitStep(`${category}_tools`, 'tool_result', 'Account context loaded', { tool, ok: true, result });
    events.push(makeEvent('message', { role: 'assistant', content: `Thank you. I’ve routed this to our ${category} specialist for review. The conversation will stay open here.` }));
  } else if (vague && thread.state.clarify_attempts === 0) {
    thread.state.category = 'other'; thread.state.pending_categories = ['billing', 'technical', 'refund']; thread.state.confidence = 0.61; thread.state.clarify_attempts += 1;
    emitStep('router', 'classification', 'Intent needs clarification', { categories: ['other'], confidence: 0.61, reasoning: 'There is not enough detail to choose a specialist.', wants_human: false });
    emitStep('router', 'clarification', 'One clarifying question asked', { question: 'Is this about billing, a technical issue, or a refund?' });
    events.push(makeEvent('message', { role: 'assistant', content: 'I can help. Is this about billing, a technical issue, or a refund?' }));
  } else if (toolFailure) {
    thread.state.category = 'technical'; thread.state.confidence = 0.89;
    emitStep('router', 'classification', 'Technical issue classified', { categories: ['technical'], confidence: 0.89, reasoning: 'The message is exercising a recoverable tool-error scenario.' });
    emitStep('dispatch', 'dispatch', 'Technical specialist selected', { category: 'technical' });
    emitStep('technical', 'tool_call', 'Known incident lookup started', { tool: 'check_known_incidents', args: { status: 'open' } });
    tools('check_known_incidents', { status: 'open' }, { error: 'Temporary CRM timeout' }, false);
    emitStep('technical_tools', 'tool_result', 'Incident lookup failed safely', { tool: 'check_known_incidents', ok: false, result: 'Temporary CRM timeout' });
    thread.state.resolution_status = 'open'; thread.status = 'open';
    events.push(makeEvent('error', { message: 'The incident service is temporarily unavailable. Your message is safe; retry in a moment or ask for a human specialist.', retryable: true }));
    events.push(makeEvent('message', { role: 'assistant', content: 'I couldn’t verify known incidents because the CRM timed out. I have not changed your account. You can retry, or ask me to bring in a human specialist.' }));
  } else if (isGoodwill) {
    thread.state.category = 'billing'; thread.state.confidence = 0.86; thread.state.resolution_status = 'open'; thread.status = 'open';
    emitStep('router', 'classification', 'Downtime goodwill request classified', { categories: ['billing'], confidence: 0.86, reasoning: 'Goodwill credits for downtime are handled by Billing, not Refunds.' });
    emitStep('dispatch', 'dispatch', 'Billing specialist selected', { category: 'billing' });
    const incident = incidents.find((row) => row.status === 'open' || row.status === 'resolved');
    emitStep('billing', 'tool_call', 'Goodwill credit review requested', { tool: 'review_goodwill_credit', args: { customer_id: customerId, incident_id: incident?.incident_id ?? null } });
    tools('review_goodwill_credit', { customer_id: customerId, incident_id: incident?.incident_id ?? null }, { status: 'review_required', credit_applied: false });
    emitStep('billing_tools', 'tool_result', 'Billing review queued; no credit applied', { tool: 'review_goodwill_credit', ok: true, result: { status: 'review_required', credit_applied: false } });
    events.push(makeEvent('message', { role: 'assistant', content: 'I’ve routed the downtime goodwill-credit request to Billing for review. I have not applied a credit or issued a refund.' }));
  } else if (isDowngrade || isUpgrade) {
    const nextTier = isDowngrade ? 'team' : 'business';
    const category: Category = 'billing';
    const sub = subscriptions.find((row) => row.customer_id === customerId)!;
    thread.state.category = category; thread.state.confidence = 0.96;
    emitStep('router', 'classification', 'Billing request classified', { categories: [category], confidence: 0.96, reasoning: isDowngrade ? 'The customer requested a plan downgrade.' : 'The customer requested a plan upgrade.' });
    emitStep('dispatch', 'dispatch', 'Billing specialist selected', { category });
    emitStep('billing', 'tool_call', 'Subscription lookup', { tool: 'get_subscription', args: { customer_id: customerId } });
    tools('get_subscription', { customer_id: customerId }, { tier: sub.tier, price_monthly: sub.price_monthly, status: sub.status });
    emitStep('billing_tools', 'tool_result', 'Subscription found', { tool: 'get_subscription', ok: true, result: { tier: sub.tier, price_monthly: sub.price_monthly } });
    emitStep('billing', 'tool_call', isDowngrade ? 'Plan downgrade' : 'Plan upgrade', { tool: 'change_plan', args: { customer_id: customerId, new_tier: nextTier } });
    const tier = fixture.tiers[nextTier];
    const daysRemaining = remainingBillingDays(sub.next_billing_date);
    const oldPrice = sub.price_monthly;
    const amount = Number((Math.abs(tier.price_monthly - oldPrice) * daysRemaining / 30).toFixed(2));
    sub.tier = nextTier as Subscription['tier']; sub.price_monthly = tier.price_monthly; sub.monitor_limit = tier.monitor_limit;
    customer.tier = nextTier as Customer['tier'];
    if (isDowngrade) sub.account_balance = Number(((sub.account_balance ?? 0) + amount).toFixed(2));
    const result = { status: 'success', tier: nextTier, price_monthly: tier.price_monthly, prorated_amount: amount, account_balance: sub.account_balance ?? 0, simulated_only: true, credit_timing: isDowngrade ? 'applied to next invoice; no charge today' : 'prorated difference due immediately; simulated only' };
    tools('change_plan', { customer_id: customerId, new_tier: nextTier }, result);
    emitStep('billing_tools', 'tool_result', 'Plan updated successfully', { tool: 'change_plan', ok: true, result });
    thread.state.resolution_status = 'resolved'; thread.status = 'resolved';
    const reply = isDowngrade
      ? `You’re now on the Team plan at $99/month. $${amount.toFixed(2)} of unused Business value has been credited to your account balance for the next invoice; there is no charge today.`
      : `Your plan is now Business at $299/month. A prorated difference of $${amount.toFixed(2)} is due immediately in this demo; no real payment was processed.`;
    events.push(makeEvent('message', { role: 'assistant', content: reply }));
  } else if (asksRefund) {
    thread.state.category = 'refund'; thread.state.confidence = 0.94;
    emitStep('router', 'classification', 'Refund request classified', { categories: ['refund'], confidence: 0.94, reasoning: 'The customer requested a refund.' });
    emitStep('dispatch', 'dispatch', 'Refund specialist selected', { category: 'refund' });
    const amount = explicitRefundAmount ?? thread.pending_refund_amount ?? 299;
    if (amount < 100 && !thread.pending_refund_amount && !/\b(yes|confirm|correct|exactly)\b/i.test(normalized)) {
      thread.pending_refund_amount = amount;
      thread.state.resolution_status = 'open'; thread.status = 'open';
      emitStep('refund', 'clarification', 'Exact amount confirmation requested', { question: `Please confirm that $${amount.toFixed(2)} is the exact refund amount you want.` });
      events.push(makeEvent('message', { role: 'assistant', content: `I can request a $${amount.toFixed(2)} refund. Please confirm that this is the exact amount you want.` }));
    } else if (amount >= 100) {
      emitStep('refund', 'tool_call', 'Refund held for review', { tool: 'prepare_refund', args: { customer_id: customerId, amount } });
      tools('prepare_refund', { customer_id: customerId, amount }, { status: 'pending_review', amount });
      const escalation = createEscalation(thread, 'refund', 0.94, 'refund_exceeds_threshold', { tool: 'issue_refund', args: { customer_id: customerId, amount, currency: 'USD' }, status: 'pending_review' }, `The customer requested a $${amount} refund. The agent prepared the request; it has not been issued.`);
      emitStep('escalate', 'escalation', 'Manager review required', { reason: 'refund_exceeds_threshold', escalation_id: escalation.escalation_id });
      events.push(makeEvent('escalated', { escalation_id: escalation.escalation_id, reason: 'refund_exceeds_threshold' }));
      events.push(makeEvent('message', { role: 'assistant', content: `I prepared a $${amount} refund request for manager review. No refund has been issued yet.` }));
    } else {
      const confirmed = Boolean(thread.pending_refund_amount) || /\b(yes|confirm|correct|exactly)\b/i.test(normalized);
      if (!confirmed) {
        thread.pending_refund_amount = amount;
        events.push(makeEvent('message', { role: 'assistant', content: `I can request a $${amount.toFixed(2)} refund. Please confirm that this is the exact amount you want.` }));
      } else {
        thread.pending_refund_amount = undefined;
        tools('issue_refund', { customer_id: customerId, amount }, { status: 'approved', amount });
        emitStep('refund', 'tool_call', 'Refund issued within policy', { tool: 'issue_refund', args: { customer_id: customerId, amount } });
        emitStep('refund_tools', 'tool_result', 'Refund approved', { tool: 'issue_refund', ok: true, result: { status: 'approved', amount } });
        thread.state.resolution_status = 'resolved'; thread.status = 'resolved';
        events.push(makeEvent('message', { role: 'assistant', content: `Your $${amount.toFixed(2)} refund was approved and issued.` }));
      }
    }
  } else if (isCancel) {
    const sub = subscriptions.find((row) => row.customer_id === customerId);
    thread.state.category = 'billing'; thread.state.confidence = 0.88;
    emitStep('router', 'classification', 'Cancellation request classified', { categories: ['billing'], confidence: 0.88, reasoning: 'The customer asked about ending a subscription.' });
    let prompt = 'Please reply “yes, cancel” if you confirm that you want your subscription cancelled.';
    if (sub?.status === 'trialing') prompt = 'Your trial is active and no payment has been captured. If you want me to cancel the trial to prevent future billing, please reply “yes, cancel”.';
    else if (sub && !sub.retention_offer_used) {
      thread.pending_retention_offer = true;
      prompt = 'Before cancelling, I can offer 10% off for 3 months. Reply “accept discount” to take the offer, or “yes, cancel” to confirm cancellation.';
    }
    thread.pending_cancel_confirmation = true;
    emitStep('refund', 'clarification', 'Explicit cancellation confirmation required', { question: prompt });
    thread.state.clarify_attempts += 1;
    events.push(makeEvent('message', { role: 'assistant', content: prompt }));
  } else if (isTechnical) {
    thread.state.category = 'technical'; thread.state.confidence = 0.87;
    emitStep('router', 'classification', 'Technical request classified', { categories: ['technical'], confidence: 0.87, reasoning: 'The message concerns a monitor or integration.' });
    emitStep('dispatch', 'dispatch', 'Technical specialist selected', { category: 'technical' });
    emitStep('technical', 'tool_call', 'Known incidents checked', { tool: 'check_known_incidents', args: { status: 'open' } });
    const active = incidents.find((row) => row.status === 'open');
    tools('check_known_incidents', { status: 'open' }, { match: active?.title ?? null });
    emitStep('technical_tools', 'tool_result', 'Incident lookup complete', { tool: 'check_known_incidents', ok: true, result: { match: active?.title ?? 'No matching incident' } });
    thread.state.resolution_status = active ? 'open' : 'resolved'; thread.status = thread.state.resolution_status;
    events.push(makeEvent('message', { role: 'assistant', content: active ? `I checked the known incidents. ${active.customer_facing_note} I have not changed any account settings.` : 'I checked the known incidents and found no matching outage. I can create a support ticket if you share the affected monitor or endpoint.' }));
  } else {
    thread.state.category = 'other'; thread.state.confidence = 0.68;
    if (thread.state.clarify_attempts < 1) {
      thread.state.clarify_attempts += 1; thread.state.pending_categories = ['billing', 'technical', 'refund'];
      emitStep('router', 'classification', 'Request needs clarification', { categories: ['other'], confidence: 0.68, reasoning: 'The request does not yet point to one specialist.' });
      emitStep('router', 'clarification', 'One clarifying question asked', { question: 'Is this about billing, a technical issue, or a refund?' });
      events.push(makeEvent('message', { role: 'assistant', content: 'Is this about billing, a technical issue, or a refund? A little more detail will help me route it correctly.' }));
    } else {
      emitStep('router', 'classification', 'Clarification exhausted', { categories: ['other'], confidence: 0.42, reasoning: 'The request remains unclear after one clarification.' });
      const escalation = createEscalation(thread, 'other', 0.42, 'clarification_exhausted', { type: 'human_review' }, 'The request remained unclear after one clarifying question.');
      emitStep('escalate', 'escalation', 'Escalating after clarification', { reason: 'clarification_exhausted', escalation_id: escalation.escalation_id });
      events.push(makeEvent('escalated', { escalation_id: escalation.escalation_id, reason: 'clarification_exhausted' }));
      events.push(makeEvent('message', { role: 'assistant', content: 'I still want to make sure this gets to the right person. I’ve passed it to a human specialist.' }));
    }
  }

  const state = snapshot(thread);
  events.push(makeEvent('state', state as unknown as Record<string, unknown>));
  const assistantEvent = [...events].reverse().find((event) => event.event === 'message');
  const assistantContent = assistantEvent?.data.content;
  if (typeof assistantContent === 'string') {
    const assistant: ThreadMessage = {
      id: randomUUID(), role: 'assistant', content: assistantContent, at: new Date().toISOString(),
      trace: { steps: structuredClone(traceSteps), toolCalls: structuredClone(toolCalls), state, startedAt: start, finishedAt: new Date().toISOString() },
    };
    thread.messages.push(assistant);
  }
  thread.updated_at = new Date().toISOString();
  events.push(makeEvent('done', {}));
  return events;
}

export function decideEscalation(input: { escalationId: string; action: DecisionAction; customerMessage?: string; note?: string }) {
  const escalation = escalations.get(input.escalationId);
  if (!escalation) return null;
  if (escalation.status !== 'pending') return escalation;
  escalation.status = 'resolved'; escalation.decision = input.action; escalation.customer_message = input.customerMessage ?? escalation.customer_message;
  escalation.decision_note = input.note ?? null; escalation.resolved_at = new Date().toISOString();
  const thread = threads.get(escalation.thread_id);
  if (thread) {
    const content = input.action === 'reject'
      ? (input.customerMessage || 'A human specialist reviewed the request. Please reply if you would like help with another option.')
      : (input.customerMessage || 'A human specialist reviewed your request and approved the proposed action.');
    thread.messages.push({ id: randomUUID(), role: 'human', content, at: new Date().toISOString() });
    thread.status = input.action === 'reject' ? 'resolved' : 'resolved';
    thread.state.resolution_status = 'resolved'; thread.state.escalation_reason = null;
    thread.updated_at = new Date().toISOString();
  }
  return escalation;
}

export function clearResolvedEscalations() {
  return [...escalations.values()].filter((row) => row.status === 'resolved');
}
