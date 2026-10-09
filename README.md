# Pulsecheck Multi-Agent Support System — Project Brief

You're picking up an in-progress build. This document is the ground truth for
what's designed, what's actually applied, and what's still open. Status
markers: ✅ confirmed applied by the developer · 🟡 designed/recommended in a
prior session but not confirmed applied · ⚠️ a bug that was specifically
found and fixed — do not reintroduce it.

---

## 1. Project overview

**Pulsecheck** is a mock SaaS company (API/uptime monitoring for dev teams) —
a synthetic scenario built specifically to justify a multi-agent support
system for a portfolio/freelance (Upwork) case study. Not a real product;
all data is seeded/synthetic.

- Tiers: Starter ($29/mo, 5 monitors), Team ($99/mo, 25 monitors),
  Business ($299/mo, 100 monitors).
- Ticket categories: `billing`, `technical`, `refund`, `other`.

## 2. Tech stack

- **Orchestration:** LangGraph (Python), `StateGraph` with conditional edges.
- **LLM:** `ChatGroq`, model `"openai/gpt-oss-20b"`, `temperature=0`, via
  `GROQ_API_KEY`. Used in every node's own file (no shared LLM instance).
- **Backend:** FastAPI + SQLAlchemy. SQLite locally
  (`PULSECHECK_DATABASE_URL`, default `sqlite:///./pulsecheck.db`).
- **Local dev:** `langgraph dev` / Studio, driven by `langgraph.json` →
  `agent/graph.py:graph`. `.langgraph_api/` is the dev server's own local
  checkpoint store — don't touch it directly.
- **Planned production (🟡 designed, not yet built):** a single merged
  FastAPI service (`service.py` — does not exist yet, needs creating at
  repo root) that mounts `backend/app/main.py` as a sub-app and adds an
  agent chat endpoint on top of `builder.compile(checkpointer=...)`.
  Deploy target: Render (free web service — sleeps after 15 min idle, full
  cold restart ~30–60s). DB target: **Neon Postgres**, chosen specifically
  over Render's own free Postgres (which expires and is deleted after
  **30 days**, not 90 — this was corrected mid-project). Neon's free tier
  has no expiry, autosuspends after 5 min idle, wakes in ms–seconds.

## 3. Repo structure (as of this session)

```
pulsecheck-support-agent/
├── agent/
│   ├── nodes/
│   │   ├── router.py
│   │   ├── dispatch.py
│   │   ├── context_manager.py
│   │   ├── billing.py
│   │   ├── technical.py
│   │   └── refund.py
│   ├── graph.py
│   ├── state.py
│   ├── tools.py
│   ├── guardrails.py      # 🟡 proposed (gated-action policy) — NOT applied
│   └── test.py             # local CLI harness (SqliteSaver-based)
├── backend/app/
│   ├── main.py              # ALL CRM endpoints live here — flat structure,
│   │                         # no services/ or routes/ split. Don't invent one.
│   └── models.py
├── langgraph.json
├── .langgraph_api/          # local dev persistence, don't edit
└── service.py                # 🟡 planned prod entrypoint — NOT created yet
```

**Important:** there is no `services/` folder and no per-resource route
files (`routes/subscriptions.py` etc.) — everything backend-side is in one
`main.py`. This was a real confusion earlier in the build; don't reintroduce
a split structure without checking first.

## 4. Graph architecture (current agreed design)

```
START → context_manager → router ─┬─(pending_categories)→ dispatch ─┬→ billing ──→ billing_tools ─┐
                                    └─(escalated)──────────→ escalate │                              │
                                                                       ├→ technical → technical_tools─┤
                                                                       ├→ refund → refund_tools ───────┤
                                                                       └(queue empty)→ END             │
                                                                                                        │
                    (each specialist loops back to dispatch when done, or to escalate on guard/status) ┘
```

`escalate` is reachable from `router`, `dispatch`, and every specialist —
it's a standing option every node can reach for, not just a router decision.

### Node-by-node

**`context_manager`** (runs first, every turn; no LLM call unless summarizing)
- Stamps `last_activity_at` to now — every single turn.
- Resets `turn_count = 0` every run ⚠️ (fixed a bug where this never reset,
  causing stale escalations on unrelated later messages).
- If gap since previous `last_activity_at` ≥ `SESSION_GAP_HOURS` (env var,
  default 1h) **and** `customer_id` is set: injects a `SystemMessage` noting
  the gap, prior `conversation_summary` if any, and a live
  `get_recent_tickets.invoke({"customer_id": ..., "days": 14})` lookup —
  deliberately a fresh CRM call, not just replayed chat, so it stays
  accurate even after old messages have been trimmed away.
- If `len(messages) > MAX_RAW_MESSAGES` (default 20): summarizes everything
  except the last `KEEP_RECENT_MESSAGES` (default 8) into
  `conversation_summary` via a cheap LLM call, then removes the summarized
  messages from persisted state via `RemoveMessage(id=...)`.
  ⚠️ The trim cut point must be advanced past any leading `ToolMessage`s
  before cutting, or the kept window can start with an orphaned tool
  result and break the next LLM call.

**`router`**
- Single structured-output LLM call.
- Schema (✅ applied — renamed from earlier buggy singular `category`):
  `categories: list[Literal["billing","technical","refund","other"]]`,
  `confidence: float`, `reasoning: str`.
- 🟡 Recommended-but-unconfirmed additions to the schema:
  `wants_human: bool` (explicit request for a human — routed straight to
  escalate with `escalation_reason="customer_requested_human"`, bypassing
  the confidence tiers) and `is_smalltalk: bool` (greetings/thanks with no
  request — short-circuits to a canned reply, no specialist, no escalation).
  **Check whether these were actually added before assuming they exist.**
- Confidence tiers:
  - `< 0.45` → escalate, `escalation_reason="low_confidence"`.
  - `0.45–0.75` → ask ONE clarifying question (`clarify_attempts == 0`),
    else escalate as `clarification_exhausted` on the second miss.
  - `≥ 0.75` → populate `pending_categories` (filtered, deduped, `"other"`
    dropped); if the filtered list is empty, escalate as
    `uncategorized_request` (🟡 this literal value — confirm it was added
    to `EscalationReason` in `state.py`).
- ⚠️ Resets `clarify_attempts = 0` on BOTH a successful classification and
  an escalation — without this, the one-question limit becomes "one
  question ever in this thread's lifetime" instead of per-issue.
- 🟡 Recommended: pass `conversation_summary` + last 3–4 messages (not just
  the single latest message) into the classification call, so a reply like
  "billing" to the clarifying question has context to resolve against.
  Confirm whether this was applied.

**`dispatch`** (non-LLM, pure state logic)
- Pops the next category off `pending_categories` into `category`.
- Resets `turn_count = 0` for the new specialist — critical for hybrid
  tickets so specialist #2 doesn't inherit specialist #1's tool-call budget.
- When the queue empties without an escalation, sets
  `resolution_status = "resolved"`.

**`billing` / `technical` / `refund`**
- Each binds its own tool list + system prompt, appends one `AIMessage`,
  increments `turn_count`.

**`billing_tools` / `technical_tools` / `refund_tools`**
- Plain `ToolNode` wrappers.

**`escalate`**
- Builds a payload (category, confidence, reasoning, proposed_action,
  conversation summary) and `POST`s it to `/escalations`.
- ⚠️ Guarded against `interrupt()`'s replay-on-resume duplicate-POST bug:
  everything before `interrupt()` re-runs from the top when a paused node
  resumes, so it does a `GET /escalations?status=pending&customer_id=`
  pre-check for an existing row (matched on `ticket_id`) before creating
  a new one.
- Calls `interrupt(payload)`, pausing the graph (state frozen by the
  checkpointer until a human resumes via `Command(resume={...})`).
- On resume: answers any dangling `tool_calls` from the last `AIMessage`
  with placeholder `ToolMessage`s ⚠️ (otherwise the next LLM call 400s on
  an unanswered tool call), sets `resolution_status` from the decision,
  and clears `pending_categories`, `category`, `clarify_attempts`,
  `escalation_reason`.
- 🟡 The full "propose → execute-on-approval" wiring (a `gate_node` that
  intercepts specific tool calls and only executes them after admin
  approval, via `agent/guardrails.py`) was **designed but explicitly NOT
  applied** — see §7.

### Routing functions (in `graph.py`)
- `route_after_router`: escalated → `escalate`; `pending_categories`
  non-empty → `dispatch`; else `END`.
- `route_after_dispatch`: escalated → `escalate`; else route on `category`;
  else `END`.
- `route_specialist`: escalated → `escalate`; last message has pending
  `tool_calls` → matching `_tools` node, UNLESS `turn_count >=
  MAX_SPECIALIST_STEPS` (env var, default 8) → `escalate` instead; else →
  `dispatch`. ⚠️ This replaced an earlier version that checked a stale,
  never-reset `turn_count > 4` against the whole thread's history instead
  of the current specialist's own run.

## 5. State schema (`agent/state.py`)

```python
class SupportState(TypedDict):
    thread_id: str
    customer_id: Optional[str]
    messages: Annotated[list[BaseMessage], add_messages]
    category: Optional[TicketCategory]
    pending_categories: list[TicketCategory]
    confidence: Optional[float]
    classification_reasoning: Optional[str]
    clarify_attempts: int
    turn_count: int
    ticket_id: Optional[str]
    refund_id: Optional[str]
    escalation_id: Optional[str]
    resolution_status: ResolutionStatus  # "open" | "resolved" | "escalated"
    escalation_reason: Optional[EscalationReason]
    proposed_action: Optional[dict[str, Any]]
    actions_taken: Annotated[list[ActionRecord], operator.add]
    last_activity_at: Optional[str]       # added this session
    conversation_summary: Optional[str]   # added this session
```

`EscalationReason` literal — confirm current full set includes:
`low_confidence`, `clarification_exhausted`, `refund_exceeds_threshold`,
`tool_call_failed`, `customer_requested_human`, `loop_guard_exceeded`, and
🟡 `uncategorized_request` (recommended addition, confirm it's there) and
🟡 `requires_human_approval` (only relevant if §7's gate-node pattern gets
built later — not needed for the currently-applied design).

## 6. Tools & backend endpoints

### Billing agent
| Tool | Backend endpoint | Notes |
|---|---|---|
| `get_subscription` | `GET /subscriptions/{customer_id}` | now also returns `account_balance`, `discount_percent`, `discount_expires_at`, `retention_offer_used` |
| `get_invoices` | `GET /invoices/{customer_id}` | unchanged |
| `update_payment_method_link` | — (stub, returns a fake hosted-payment-page URL) | intentionally a stub — avoids PCI scope |
| `change_subscription_plan` | `POST /subscriptions/{customer_id}/change-plan` | real proration math: downgrade → credits `account_balance` (applied automatically to next invoice, `immediate_charge=0`); upgrade → charges the prorated difference immediately via a new `Invoice` row |
| `apply_credit` | `POST /subscriptions/{customer_id}/credit` | goodwill credits ONLY — prompt explicitly forbids using this for plan changes. ⚠️ **No amount ceiling yet** — open item, see §8 |

### Technical agent
| Tool | Backend endpoint | Notes |
|---|---|---|
| `check_known_incidents` | `GET /incidents?status=` | platform-wide dedup check |
| `get_monitor_status` | — | current-status check (not historical) |
| `resend_webhook_test` | — | |
| `create_bug_ticket` | `POST /tickets` | only after BOTH dedup checks below miss |
| `get_recent_tickets` | `GET /tickets?customer_id=&category=&days=&limit=` | per-customer dedup check — param is `days`, NOT `hours` (a real bug where the tool passed `hours` and the endpoint silently ignored it, falling back to its `days=3` default) |
| `get_historical_stats` | `GET /monitors/{customer_id}/stats?days=` | downtime/failure report. **Requires a `DowntimeEvent` model + seed data — NOT YET ADDED to `models.py`/seed data.** This tool will fail against the current schema until that table exists. |

### Refund agent
| Tool | Backend endpoint | Notes |
|---|---|---|
| `get_subscription` | shared with billing | |
| `issue_refund` | `POST /refunds` | $100 auto-approval threshold, server-enforced (`status="pending_review"` at/above). 🟡 A `confirmed: bool` argument (agent must ask "I'll refund $X, confirm?" before calling with `confirmed=True`) was **recommended but not confirmed applied** — confirm before assuming it's live. |
| `apply_retention_discount` | `POST /subscriptions/{customer_id}/retention-discount` | new tool. Caps: `discount_percent` 5–25, `duration_months` 1–6. Auto-approved only if ≤20% AND ≤3 months, else `pending_review`. **One-time use per subscription** via `retention_offer_used` flag — a second attempt on the same account is rejected (409). |
| `cancel_subscription(customer_id, confirmed: bool)` | `POST /subscriptions/{customer_id}/cancel` | ✅ **APPLIED.** Backend rejects the call (400) unless `confirmed=True`. Prompt requires the agent to ask a direct yes/no confirmation question in-conversation and only pass `confirmed=True` after an explicit yes. This is the customer-facing confirmation pattern the developer chose to use — see §7 for why this is a different mechanism than admin approval. |

Refund agent's prompt-level (not code-enforced) cancellation policy:
check `retention_offer_used` first — if `True`, just confirm and cancel;
if `False`, offer `apply_retention_discount` before allowing cancellation,
and only proceed to cancel if the customer declines the offer.

### Backend model fields added this session — verify present in `models.py`
- `Subscription.account_balance` (Numeric(10,2), default 0.00)
- `Subscription.discount_percent`, `discount_expires_at`, `retention_offer_used`
- ⚠️ **Migration gotcha:** `Base.metadata.create_all()` (used in
  `seed_database()`) creates missing *tables*, not missing *columns* on
  existing tables. If `pulsecheck.db` already exists on disk from before
  these fields were added, they won't appear — delete the file and let it
  reseed, or these fields will silently 500/KeyError.

## 7. Human-in-the-loop — two distinct mechanisms, don't conflate them

This was a real point of confusion mid-project — the developer initially
asked for one thing, I built the other, and we corrected it. Keep these
separate going forward:

1. **Customer-facing confirmation** (✅ what's actually built) — synchronous,
   same turn, no graph pause. Pattern: a `confirmed: bool` tool argument
   the backend rejects unless `True`; the prompt requires the LLM to ask
   the customer directly and only pass `True` after an explicit yes.
   Currently applied to `cancel_subscription` only. This is what "human in
   the loop" means in this project's current state — **the human being
   asked is the CUSTOMER**, not an ops reviewer.

2. **Admin/ops approval** (🟡 designed, exists structurally via
   `escalate_node` + `interrupt()`, but the specific "gate a tool call
   before it executes, pause, resume with execution" wiring — described as
   `agent/guardrails.py` + a `gate_node` intercepting `route_specialist` —
   was proposed in full and the developer explicitly said they did **not**
   apply it, preferring the simpler customer-confirmation pattern for now.
   Don't assume this exists. If asked to build it later, the design already
   exists in this project's history: a `gated_reason(tool_name, args)`
   policy function, a `gate` node between a specialist and its `_tools`
   node that intercepts flagged calls, escalates with
   `proposed_action` populated, and `escalate_node` executing the actual
   tool call only after `interrupt()` returns an "approve"/"edit" decision.

The `$100`/`pending_review` refund threshold and the `20%`/`3mo` discount
cap are still enforced server-side regardless — that part doesn't depend
on either mechanism above; it's the backend rejecting/flagging the row
based on the amount, independent of who confirmed what.

## 8. Open items (recommended in chat, not confirmed applied)

Roughly in order of how much they'd bite in a demo:

1. `get_historical_stats` needs its backing `DowntimeEvent` table + seed
   data — currently no data source for it.
2. `issue_refund` doesn't yet have the `confirmed` gate `cancel_subscription`
   has — an agent could currently issue a refund without ever stating the
   amount back to the customer for confirmation.
3. `apply_credit` (goodwill credits) has no amount ceiling at all — unlike
   refunds and discounts, there's no threshold that routes a large one to
   review.
4. Router's classifier still may only see the latest message, not
   `conversation_summary` + recent turns — worth confirming, since it
   affects the clarify-question reply flow specifically.
5. `wants_human` / `is_smalltalk` classifier fields — confirm whether these
   were added; without them, an explicit "let me talk to a human" or a
   plain "thanks" both get routed through the normal confidence-tier logic
   instead of handled directly.
6. `service.py` (production entrypoint), Render deployment, Neon migration —
   all designed, none built yet.
7. Ops dashboard's Approve/Edit/Reject buttons need to call
   `Command(resume={"action": ..., "customer_message": ...})` — dashboard
   file itself hasn't been reviewed in this session.
8. Original build plan's eval harness (`agent/evals/golden_set.jsonl` +
   accuracy scoring), Docker/docker-compose, and LangSmith tracing are all
   still per the original plan — not touched in this session, status
   unknown.

## 9. Structural bugs fixed this session (context — don't reintroduce)

- `graph.py` missing `import os` (crashed on import).
- `route_specialist` never checked `resolution_status == "escalated"` —
  specialist-initiated escalations (e.g. refund over threshold) were
  silently dropped, falling through to `END` instead.
- `router_node` wrote `state["category"]` as a bare string/list mismatch
  against the dispatch-queue design — fixed by having router populate
  `pending_categories` only, and `dispatch_node` set `category`.
- Escalation `POST` could fire twice per escalation due to `interrupt()`
  replaying the node from the top on resume — fixed with a pre-check GET.
- `pending_categories` could go stale across an aborted/escalated ticket
  and leak into a later, unrelated turn — fixed by explicitly clearing it
  in every terminal branch (escalation, clarify-exhausted, smalltalk).
- `turn_count` never reset, causing later unrelated messages in the same
  thread to hit a stale loop-guard threshold — fixed by resetting per
  graph-run (in `context_manager`) and per specialist hand-off (in
  `dispatch`).
- `clarify_attempts` never reset after a successful classification or an
  escalation, effectively becoming "one clarifying question ever" per
  thread instead of per issue.

---

*This document reflects the state of the project as of the session that
produced it. If you're an agent picking this up: verify the 🟡 items
against the actual current files before building on top of them — don't
assume a recommendation became code just because it's described here.*