export type Category = 'billing' | 'technical' | 'refund' | 'other';
export type ThreadStatus = 'open' | 'resolved' | 'escalated';
export type AccountStatus = 'active' | 'past_due' | 'trialing' | 'cancelled';
export type DecisionAction = 'approve' | 'edit' | 'reject';

export interface Customer {
  customer_id: string;
  company_name: string;
  contact_name: string;
  contact_email: string;
  signup_date: string;
  tier: 'starter' | 'team' | 'business';
  account_status: AccountStatus;
}

export interface Subscription {
  subscription_id: string;
  customer_id: string;
  tier: 'starter' | 'team' | 'business';
  monitor_limit: number;
  monitors_used: number;
  price_monthly: number;
  account_balance?: number;
  discount_percent?: number;
  discount_expires_at?: string | null;
  retention_offer_used?: boolean;
  status: AccountStatus;
  created_at?: string;
  next_billing_date: string | null;
  trial_end_date: string | null;
  cancelled_at: string | null;
  failed_payment_count: number;
  payment_method_last4: string;
}

export interface Ticket {
  ticket_id: string;
  customer_id: string;
  category: Category;
  subject: string;
  status: string;
  created_at: string;
}

export interface Incident {
  incident_id: string;
  title: string;
  status: 'open' | 'resolved';
  started_at: string;
  resolved_at?: string | null;
  customer_facing_note: string;
}

export interface TraceStep {
  id: string;
  at: string;
  node: string;
  kind: string;
  title: string;
  detail: unknown;
}

export interface ToolCall {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  result: unknown;
  ok: boolean;
  duration_ms: number;
}

export interface ThreadState {
  category: Category | null;
  pending_categories: Category[];
  confidence: number | null;
  clarify_attempts: number;
  turn_count: number;
  resolution_status: ThreadStatus;
  escalation_reason: string | null;
}

export interface ThreadMessage {
  id: string;
  role: 'user' | 'assistant' | 'human';
  content: string;
  at: string;
  trace?: {
    steps: TraceStep[];
    toolCalls: ToolCall[];
    state: ThreadState;
    startedAt: string;
    finishedAt: string;
  };
}

export interface ThreadRecord {
  thread_id: string;
  customer_id: string;
  status: ThreadStatus;
  messages: ThreadMessage[];
  state: ThreadState;
  steps: TraceStep[];
  pending_refund_amount?: number;
  pending_cancel_confirmation?: boolean;
  pending_retention_offer?: boolean;
  updated_at: string;
}

export interface Escalation {
  escalation_id: string;
  customer_id: string;
  ticket_id: string;
  category: Category;
  confidence: number;
  reasoning: string;
  proposed_action: Record<string, unknown>;
  conversation_summary: string;
  status: 'pending' | 'resolved';
  decision: DecisionAction | null;
  decision_note: string | null;
  customer_message: string | null;
  created_at: string;
  created_at_time?: string | null;
  resolved_at: string | null;
  thread_id: string;
  customer_company_name: string;
}

export interface AgentEvent {
  event: 'step' | 'message' | 'state' | 'escalated' | 'error' | 'done';
  data: Record<string, unknown>;
}
