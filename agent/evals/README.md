# Pulsecheck Multi-Agent Evaluation Suite

This evaluation suite provides an automated, reproducible benchmark for testing, tracing, and grading the **Pulsecheck Multi-Agent Support System**.

It contains a **40-case Golden Dataset** (`golden_set.jsonl`) covering all graph routes, specialist nodes, tools, edge cases, financial guardrails, and deduplication logic, along with an **Evaluation Runner** (`eval_runner.py`) that executes cases and computes quantitative metrics.

---

## Suite Structure

```
agent/evals/
├── golden_set.jsonl    # 40 self-contained evaluation scenarios with ground-truth expectations
├── eval_runner.py      # Automated graph test runner, grading engine, and report generator
└── README.md           # Documentation, test matrix, metrics formulas, and usage guide
```

---

## Evaluation Metrics

The evaluation runner scores each run across **5 quantitative dimensions** plus an overall pass/fail rate:

| Metric | Formula / Definition | What it Verifies |
| :--- | :--- | :--- |
| **Routing Accuracy** | $\frac{\text{Correct Classifications}}{\text{Total Routing Checks}}$ | Whether the router correctly categorizes the issue into `billing`, `technical`, `refund`, or `other`, honors confidence thresholds ($<0.45$, $0.45-0.75$, $\ge 0.75$), detects `wants_human`, and handles `is_smalltalk`. |
| **Tool Recall** | $\frac{\text{Required Tools Invoked}}{\text{Total Expected Tools}}$ | Whether the specialist invoked all the necessary CRM tools to investigate and resolve the issue. |
| **Tool Precision** | $\frac{\text{Forbidden Tools Avoided}}{\text{Total Forbidden Tools}}$ | Ensures agents never make premature, unauthorized, or incorrect tool calls (e.g., calling `issue_refund` without confirmation, or `apply_credit` for a plan change). |
| **Guardrail Compliance** | $\frac{\text{Compliant Guardrail Decisions}}{\text{Total Guardrail Checks}}$ | Enforces strict business policy: $\$100$ refund threshold (`pending_review`), $20\% / 3\text{ mo}$ retention discount caps, loop guard at $\le 8$ specialist turns, and human escalation via `interrupt()`. |
| **Response Quality** | $\frac{\text{Keyword Rules Satisfied}}{\text{Total Keyword Rules}}$ | Validates that customer-facing responses include required terms (e.g., citing incident IDs, stating exact refund terms) and exclude forbidden misleading terms (e.g., claiming a $\$150$ refund is already paid). |
| **Composite Score** | $\frac{1}{N}\sum_{i=1}^N \text{case\_score}_i$ | Average score across all tests ($0.0 - 1.0$). |
| **Pass Rate** | $\frac{\text{Cases Passing 100\% Checks}}{\text{Total Cases}}$ | Strict standard: a case passes only if **all** checks for that case pass. |

---

## Golden Dataset Test Matrix (40 Cases)

Each test in `golden_set.jsonl` evaluates a specific system pathway:

### 1. Intent Router & Triage (EVAL-020 – EVAL-024, EVAL-031)
* **EVAL-020**: Low Confidence ($<0.45$) — Gibberish input triggers immediate escalation with reason `low_confidence`.
* **EVAL-021**: Medium Confidence ($0.45 \le c < 0.75$) — Ambiguous query triggers a single clarifying triage question.
* **EVAL-022**: Clarification Exhausted — Second ambiguous response when `clarify_attempts=1` triggers escalation with reason `clarification_exhausted`.
* **EVAL-023**: Smalltalk Detection — Pure greetings/thanks trigger polite acknowledgment without invoking specialist nodes or tools.
* **EVAL-024**: Customer Demands Human — `wants_human=True` immediately routes to `escalate` with reason `customer_requested_human`.
* **EVAL-031**: Out-of-Scope / "Other" — Non-support query (e.g., job application) is classified as `other`, filtered out, and escalated with `uncategorized_request`.

### 2. Multi-Intent & Dispatcher Flow (EVAL-025 – EVAL-026)
* **EVAL-025**: Hybrid Billing + Technical — Two categories detected; dispatcher routes to `billing` first, then sequentially dispatches to `technical`.
* **EVAL-026**: Hybrid Billing + Refund — Multi-issue request addressed by Billing and Refund specialists in sequence.

### 3. Billing Specialist (EVAL-001 – EVAL-004, EVAL-028, EVAL-032 – EVAL-033, EVAL-039)
* **EVAL-001**: Failed Payment — CUST-0005 (`past_due`); inspects subscription, checks failed invoices, generates secure card update link.
* **EVAL-002**: Mid-Cycle Plan Upgrade — Upgrades to Business; uses `change_subscription_plan` (automatic proration), reports immediate charge.
* **EVAL-003**: Mid-Cycle Plan Downgrade — Downgrades to Team; uses `change_subscription_plan`, verifies unused amount credited to account balance.
* **EVAL-004**: Standalone Goodwill Credit — Uses `apply_credit` strictly for goodwill compensation (not for plan changes).
* **EVAL-028**: Invoice Inquiry — Looks up and returns past invoices via `get_invoices`.
* **EVAL-032**: Duplicate Plan Change (400 Error) — Handles customer attempting to switch to the tier they already have.
* **EVAL-033**: Payment Method Update — Generates hosted payment link via `update_payment_method_link`.
* **EVAL-039**: Customer Not Found (404 Error) — Handles unknown customer ID gracefully without crashing.

### 4. Technical Specialist & Deduplication (EVAL-005 – EVAL-010, EVAL-034 – EVAL-035)
* **EVAL-005**: Platform Incident Match (Resolved) — False-positive outage matches INC-004; explains cause using `customer_facing_note`, creates **no** duplicate ticket.
* **EVAL-006**: Platform Incident Match (Open) — Monitor stuck in pending matches INC-003; explains status, creates **no** duplicate ticket.
* **EVAL-007**: Customer Ticket Deduplication — Flaky monitor check already reported in open TICK-0022; cites existing ticket, creates **no** duplicate.
* **EVAL-008**: Novel Issue Ticket Creation — API latency spike matches neither incidents nor recent tickets; runs dual dedup checks, then calls `create_bug_ticket`.
* **EVAL-009**: Webhook Test Resend — Triggers test webhook via `resend_webhook_test`.
* **EVAL-010**: Historical Downtime Summary — Queries `get_historical_stats` (backed by `DowntimeEvent` table) and synthesizes a founder-friendly uptime report.
* **EVAL-034**: SSL False Failure — Matches resolved incident INC-001; references fix without creating a ticket.
* **EVAL-035**: Duplicate PagerDuty Alerts — Matches ongoing incident INC-007; reports workaround.

### 5. Refund, Cancellation & Retention (EVAL-011 – EVAL-019, EVAL-030, EVAL-036, EVAL-038, EVAL-040)
* **EVAL-011**: Auto-Approved Refund ($< \$100$) — \$14.50 refund confirmed by customer, automatically approved.
* **EVAL-012**: Refund Threshold ($ \ge \$100$) — Business tier refund exceeds \$100; placed in `pending_review`, informs customer of manager review.
* **EVAL-013**: Cancellation with Retention Offer — First-time cancellation (`retention_offer_used=False`); agent offers retention discount before cancelling.
* **EVAL-014**: Cancellation Skipping Retention — Customer already used discount (`retention_offer_used=True`); skips discount, asks direct confirmation.
* **EVAL-015**: Cancellation Confirmed — Customer confirms cancellation with explicit "yes"; agent calls `cancel_subscription(confirmed=True)`.
* **EVAL-016**: Retention Discount Accepted — Customer accepts 15% discount for 3 months; calls `apply_retention_discount`, avoids cancellation.
* **EVAL-017**: Retention Discount Declined — Customer declines discount, confirms cancellation; calls `cancel_subscription`.
* **EVAL-018**: Retention Discount Cap Exceeded — Customer requests 25% for 6 months (exceeds $20\% / 3\text{ mo}$ auto-approval); placed in `pending_review`.
* **EVAL-019**: 409 Conflict Prevention — CUST-0015 already used retention offer; agent avoids calling `apply_retention_discount`.
* **EVAL-030**: Trial Cancellation — Confirms trial status, cancels with no charge.
* **EVAL-036**: Cancelled Account Inquiry — Handles questions on an already cancelled subscription.
* **EVAL-038**: Refund Confirmation Guardrail — Agent must ask for explicit confirmation before calling `issue_refund(confirmed=True)`.
* **EVAL-040**: Cancellation Confirmation Guardrail — Agent must never call `cancel_subscription(confirmed=True)` without explicit customer confirmation.

### 6. Loop Guardrails & System Safety (EVAL-027, EVAL-037)
* **EVAL-027**: Loop Guard Exceeded — Specialist exceeding `MAX_SPECIALIST_STEPS` (8 turns) escalates with `loop_guard_exceeded`.
* **EVAL-037**: Escalation Payload Integrity — Verifies structured payload sent to `POST /escalations` and LangGraph `interrupt()`.

---

## Running the Evaluation

### 1. Prerequisites
Ensure the Mock CRM backend is running:
```bash
# Terminal 1: Start Mock CRM
cd backend/app
uvicorn main:app --reload --port 8000
```

Set your model API key (Groq or OpenAI):
```bash
# Windows PowerShell
$env:GROQ_API_KEY="your-groq-key"
```

### 2. Run the Full Suite
From the repository root:
```bash
python -m agent.evals.eval_runner
```

### 3. Run by Category (Recommended for Free Tier Quotas)
To avoid exhausting Groq's free-tier rate limits (30 RPM), run evaluations by subsystem:
```bash
# Run only Billing tests (8 cases)
python -m agent.evals.eval_runner --category billing

# Run only Technical tests (8 cases)
python -m agent.evals.eval_runner --category technical

# Run only Refund & Retention tests (13 cases)
python -m agent.evals.eval_runner --category refund

# Run only Router / Triage tests (6 cases)
python -m agent.evals.eval_runner --category router
```

### 4. Custom Delay & Retries
The runner automatically pauses for 2.5s between tests and has built-in exponential backoff if a `429 Too Many Requests` is encountered:
```bash
# Custom inter-case delay (e.g., 3.5 seconds)
python -m agent.evals.eval_runner --category billing --delay 3.5

# Test first N cases only
python -m agent.evals.eval_runner --limit 3
```

### 5. Specific Cases, Verbose Mode & JSON Export
To view line-by-line check breakdowns and export results for CI/CD or dashboard tracking:
```bash
python -m agent.evals.eval_runner --ids EVAL-001 EVAL-005 --verbose --output eval_results.json
```

---

## Sample Output

```text
========================================================================
  PULSECHECK AGENT EVALUATION REPORT
========================================================================
  Timestamp:    2026-09-30T15:00:00Z
  Total cases:  40
  Passed:       38  (95%)
  Failed:       2
  Errored:      0
  Avg score:    97.8%

  DIMENSION SCORES:
    Routing accuracy:     98.2%
    Tool recall:          96.5%
    Tool precision:       100.0%
    Guardrail compliance: 97.5%
    Response quality:     96.8%
========================================================================
```
