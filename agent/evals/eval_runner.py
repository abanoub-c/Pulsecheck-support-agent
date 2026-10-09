"""
Pulsecheck agent evaluation runner.

Belongs at: agent/evals/eval_runner.py        Dataset: agent/evals/golden_set.jsonl

What it does
------------
* Lints the dataset first: typos in expected-keys, tool names, roles or state
  overrides are errors, never silent passes.
* Resets the CRM to its seed state before EVERY case (POST /admin/reseed), so
  one case's refunds/cancellations can't contaminate the next.
* Runs each case through the graph with an in-memory checkpointer, so
  escalations (interrupt()) pause cleanly and the paused state can be read.
* Scores routing, tool use, guardrails, responses and state. The JSON report
  keeps a full transcript per case for error analysis.

Usage (project root, backend running on :8000, GROQ_API_KEY in .env):
    python -m agent.evals.eval_runner --lint            # dataset check only, no LLM calls
    python -m agent.evals.eval_runner                   # everything
    python -m agent.evals.eval_runner --ids EVAL-003 EVAL-011 -v
    python -m agent.evals.eval_runner --area refund --output reports/refund.json

Case schema
-----------
End-to-end case: id, name, area, customer_id (or null), messages
[{"role": "human"|"ai", "content": ...}] (must end with a human message),
optional initial_state_overrides, expected, notes.
Unit case: "type": "unit", state {...}, expected {"route": ...} -- calls
route_specialist directly (no LLM, no backend).

`expected` keys (all optional):
  router_category [..]            router's categories must include these
  router_confidence_min / _max    float bounds
  specialist str|null             specialist that ran (null = none)
  specialists_visited [..]        exact set of specialists that ran
  tools_called / tools_not_called [tool names]
  tool_args {tool: {arg: value}}  some call must match; "~text" = substring,
                                  numbers compare within 0.01
  tool_result_contains {tool: text}
  tool_order [tool names]         first calls must occur in this order
  max_tool_calls int
  response_must_contain_any [[alt, alt], ...]   every inner list needs a hit
  response_must_not_contain [text, ...]
  ai_message_count int            final (non-tool-call) AI messages produced
  escalated bool, escalation_reason str, escalation_reason_in [..]
  resolution_status, clarify_attempts, pending_categories_empty
  escalation_payload_fields [..]  keys present in the interrupt() payload
  crm_escalation_count int        pending escalation rows for the customer
  guardrail str                   free-text note, not scored
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Windows consoles choke on emoji / non-ASCII without this.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

try:  # optional: load GROQ_API_KEY from .env
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

if not os.getenv("GROQ_API_KEY"):
    sys.exit("GROQ_API_KEY is not set. Put it in a .env file at the project root (never hardcode it).")

import requests  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402

from agent.graph import builder, route_specialist  # noqa: E402
from agent.nodes.billing import BILLING_TOOLS  # noqa: E402
from agent.nodes.refund import REFUND_TOOLS  # noqa: E402
from agent.nodes.technical import TECHNICAL_TOOLS  # noqa: E402
from agent.state import new_support_state  # noqa: E402

# interrupt() needs a checkpointer; the runner compiles its own copy of the graph.
GRAPH = builder.compile(checkpointer=MemorySaver())

API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")
MAX_ATTEMPTS = 4  # per case, only retried on 429s
SPECIALISTS = ("billing", "technical", "refund")
KNOWN_TOOLS = {t.name for t in (*BILLING_TOOLS, *TECHNICAL_TOOLS, *REFUND_TOOLS)}
STATE_KEYS = set(new_support_state("x").keys())

E2E_KEYS = {
    "router_category", "router_confidence_min", "router_confidence_max",
    "specialist", "specialists_visited",
    "tools_called", "tools_not_called", "tool_args", "tool_result_contains",
    "tool_order", "max_tool_calls",
    "response_must_contain_any", "response_must_not_contain", "ai_message_count",
    "escalated", "escalation_reason", "escalation_reason_in", "resolution_status",
    "clarify_attempts", "pending_categories_empty",
    "escalation_payload_fields", "crm_escalation_count",
    "guardrail",
}
UNIT_KEYS = {"route"}


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class Check:
    name: str
    dimension: str  # routing | tool_recall | tool_precision | guardrail | response | state
    passed: bool
    expected: Any = None
    actual: Any = None
    detail: str = ""


@dataclass
class CaseResult:
    eval_id: str
    name: str
    area: str
    passed: bool = False
    score: float = 0.0
    checks: list[Check] = field(default_factory=list)
    error: Optional[str] = None
    duration_s: float = 0.0
    response: str = ""
    final_state: dict = field(default_factory=dict)
    tool_calls: list[dict] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)


@dataclass
class Run:
    values: dict
    new_messages: list
    interrupted: bool
    payload: Optional[dict]
    tool_calls: list[dict]
    tool_results: list[dict]
    ai_texts: list[str]


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def text_of(content: Any) -> str:
    """Message content can be a str or a list of blocks; always return str."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b if isinstance(b, str) else str(b.get("text", ""))
            for b in content
            if isinstance(b, (str, dict))
        )
    return "" if content is None else str(content)


def short(x: Any, n: int = 140) -> str:
    s = x if isinstance(x, str) else json.dumps(x, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def is_rate_limit(e: Exception) -> bool:
    s = str(e).lower()
    return "429" in s or "rate limit" in s or "rate_limit" in s or "too many requests" in s


def http_get(path: str, **params: Any) -> Any:
    r = requests.get(f"{API_BASE}{path}", params=params or None, timeout=15)
    r.raise_for_status()
    return r.json()


_reseed_enabled = True


def reseed() -> bool:
    """Reset the CRM to seed data. Returns False if the endpoint isn't available."""
    global _reseed_enabled
    if not _reseed_enabled:
        return False
    try:
        r = requests.post(f"{API_BASE}/admin/reseed", timeout=60)
    except requests.RequestException as e:
        raise RuntimeError(f"Backend unreachable at {API_BASE}: {e}") from e
    if r.status_code == 404:
        print("⚠  POST /admin/reseed returned 404 - cases will NOT be isolated from each other.")
        _reseed_enabled = False
        return False
    r.raise_for_status()
    return True


# ---------------------------------------------------------------------------
# Dataset loading + lint
# ---------------------------------------------------------------------------
def load_cases(path: Path) -> list[dict]:
    cases = []
    with open(path, "r", encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                cases.append(json.loads(line))
            except json.JSONDecodeError as e:
                sys.exit(f"❌ {path.name} line {n}: invalid JSON ({e})")
    return cases


def lint(cases: list[dict]) -> list[str]:
    errs: list[str] = []
    seen: set[str] = set()
    for i, c in enumerate(cases, 1):
        cid = c.get("id", f"<case #{i}>")

        def err(msg: str, cid: str = cid) -> None:
            errs.append(f"{cid}: {msg}")

        if cid in seen:
            err("duplicate id")
        seen.add(cid)
        for k in ("id", "name", "area", "expected"):
            if k not in c:
                err(f"missing '{k}'")
        exp = c.get("expected", {})

        if c.get("type") == "unit":
            if "state" not in c:
                err("unit case needs 'state'")
            if "route" not in exp:
                err("unit case needs expected.route")
            for k in set(exp) - UNIT_KEYS:
                err(f"unsupported key '{k}' in unit case")
            continue

        if "customer_id" not in c:
            err("missing 'customer_id' (use null for an anonymous customer)")
        msgs = c.get("messages") or []
        if not msgs:
            err("no messages")
        else:
            if any(m.get("role") not in ("human", "ai") or not str(m.get("content", "")).strip() for m in msgs):
                err("every message needs role human|ai and non-empty content")
            if msgs[0].get("role") != "human" or msgs[-1].get("role") != "human":
                err("messages must start and end with a human message")
        for k in set(exp) - E2E_KEYS:
            err(f"unsupported expected key '{k}'")
        for k in set(c.get("initial_state_overrides", {})) - STATE_KEYS:
            err(f"initial_state_overrides has unknown state field '{k}'")
        tools = set(exp.get("tools_called", [])) | set(exp.get("tools_not_called", []))
        tools |= set(exp.get("tool_order", [])) | set(exp.get("tool_args", {})) | set(exp.get("tool_result_contains", {}))
        for t in sorted(tools - KNOWN_TOOLS):
            err(f"unknown tool '{t}'")
        for alts in exp.get("response_must_contain_any", []):
            if not isinstance(alts, list) or not alts or not all(isinstance(a, str) for a in alts):
                err("response_must_contain_any must be a list of non-empty string lists")
        if not any(k in exp for k in E2E_KEYS - {"guardrail"}):
            err("expected has no scored keys (case would pass vacuously)")
    return errs


# ---------------------------------------------------------------------------
# Backend preflight: does the seed data match what the dataset assumes?
# ---------------------------------------------------------------------------
def _sub(cid: str) -> dict:
    return http_get(f"/subscriptions/{cid}")


def _future(d: Optional[str]) -> bool:
    return d is not None and date.fromisoformat(d) > date.today()


def _incident_ids(status: str) -> set[str]:
    return {i["incident_id"] for i in http_get("/incidents", status=status)}


SEED_FACTS = [
    ("CUST-0006 is on Business (EVAL-003/015)", lambda: _sub("CUST-0006")["tier"] == "business"),
    ("CUST-0006 retention_offer_used = true (EVAL-014/015)", lambda: _sub("CUST-0006")["retention_offer_used"] is True),
    ("CUST-0006 next_billing_date is in the future (proration)", lambda: _future(_sub("CUST-0006")["next_billing_date"])),
    ("CUST-0002 is on Team (EVAL-002/032)", lambda: _sub("CUST-0002")["tier"] == "team"),
    ("CUST-0002 next_billing_date is in the future (proration)", lambda: _future(_sub("CUST-0002")["next_billing_date"])),
    ("CUST-0012 is on Business (EVAL-012)", lambda: _sub("CUST-0012")["tier"] == "business"),
    ("CUST-0022 is on Starter (EVAL-011/038)", lambda: _sub("CUST-0022")["tier"] == "starter"),
    ("CUST-0019 retention_offer_used = false", lambda: _sub("CUST-0019")["retention_offer_used"] is False),
    ("CUST-0021 retention_offer_used = false", lambda: _sub("CUST-0021")["retention_offer_used"] is False),
    ("CUST-0015 retention_offer_used = true", lambda: _sub("CUST-0015")["retention_offer_used"] is True),
    ("CUST-0010 status = trialing", lambda: _sub("CUST-0010")["status"] == "trialing"),
    ("CUST-0018 status = cancelled", lambda: _sub("CUST-0018")["status"] == "cancelled"),
    ("CUST-0004 has at least one invoice (EVAL-028)", lambda: len(http_get("/invoices/CUST-0004")) > 0),
    (
        "TICK-0022 is inside the 14-day window for CUST-0014 (EVAL-007)",
        lambda: "TICK-0022" in {t["ticket_id"] for t in http_get("/tickets", customer_id="CUST-0014", days=14)},
    ),
    (
        "CUST-0002 has 3 downtime events in the last 30 days (EVAL-010)",
        lambda: http_get("/monitors/CUST-0002/stats", days=30)["total_events"] == 3,
    ),
    ("INC-003 and INC-007 are status=open", lambda: {"INC-003", "INC-007"} <= _incident_ids("open")),
    ("INC-001 is status=resolved", lambda: "INC-001" in _incident_ids("resolved")),
    (
        "INC-004 is open or resolved (the tool can only filter those two)",
        lambda: "INC-004" in (_incident_ids("open") | _incident_ids("resolved")),
    ),
    (
        "CUST-9999 does not exist (EVAL-039)",
        lambda: requests.get(f"{API_BASE}/subscriptions/CUST-9999", timeout=15).status_code == 404,
    ),
]


def preflight(cases: list[dict], check_seed: bool) -> bool:
    try:
        requests.get(f"{API_BASE}/health", timeout=5).raise_for_status()
    except Exception as e:
        print(f"❌ Backend not reachable at {API_BASE}: {e}\n   Start it with: uvicorn main:app (from backend/app)")
        return False
    if reseed():
        print("✓ CRM reseeded")
    if not check_seed:
        return True
    problems = 0
    for desc, fn in SEED_FACTS:
        try:
            ok = bool(fn())
        except Exception as e:  # noqa: BLE001
            ok, desc = False, f"{desc} [{type(e).__name__}: {short(str(e), 60)}]"
        if not ok:
            problems += 1
            print(f"⚠  seed mismatch: {desc}")
    ids = sorted({c["customer_id"] for c in cases if c.get("customer_id") and c["customer_id"] != "CUST-9999"})
    for cid in ids:
        try:
            http_get(f"/customers/{cid}")
        except Exception:  # noqa: BLE001
            problems += 1
            print(f"⚠  seed mismatch: customer {cid} does not exist")
    print(f"✓ seed check: {'all facts hold' if not problems else f'{problems} mismatch(es) - affected cases will fail for data reasons, not agent reasons'}")
    return True


# ---------------------------------------------------------------------------
# Running a case
# ---------------------------------------------------------------------------
def build_state(case: dict) -> tuple[dict, int]:
    msgs = case["messages"]
    state = new_support_state(
        thread_id=f"eval-{case['id']}-{uuid.uuid4().hex[:8]}",
        customer_id=case.get("customer_id"),
        first_message=HumanMessage(content=msgs[0]["content"]),
    )
    state.update(case.get("initial_state_overrides", {}))
    for m in msgs[1:]:
        cls = HumanMessage if m["role"] == "human" else AIMessage
        state["messages"].append(cls(content=m["content"]))
    return state, len(state["messages"])


def execute_graph(case: dict) -> Run:
    for attempt in range(1, MAX_ATTEMPTS + 1):
        reseed()
        state, n_seed = build_state(case)
        config = {"configurable": {"thread_id": state["thread_id"]}, "recursion_limit": 40}
        try:
            GRAPH.invoke(state, config)
        except Exception as e:  # noqa: BLE001
            if is_rate_limit(e) and attempt < MAX_ATTEMPTS:
                wait = attempt * 20
                print(f"\n     [429 rate limit - cooling down {wait}s, retry {attempt}/{MAX_ATTEMPTS - 1}]", flush=True)
                time.sleep(wait)
                continue
            raise

        snap = GRAPH.get_state(config)
        interrupts = [i for t in snap.tasks for i in (getattr(t, "interrupts", None) or ())]
        values = dict(snap.values)
        new_msgs = [m for m in values.get("messages", [])[n_seed:] if not isinstance(m, SystemMessage)]

        tool_calls, tool_results, ai_texts = [], [], []
        for m in new_msgs:
            if isinstance(m, AIMessage):
                for tc in m.tool_calls or []:
                    tool_calls.append({"name": tc.get("name"), "args": tc.get("args", {})})
                if not m.tool_calls and text_of(m.content).strip():
                    ai_texts.append(text_of(m.content).strip())
            elif isinstance(m, ToolMessage):
                tool_results.append({"name": m.name, "content": text_of(m.content)})
        payload = interrupts[0].value if interrupts else None
        return Run(values, new_msgs, bool(interrupts), payload if isinstance(payload, dict) else None,
                   tool_calls, tool_results, ai_texts)
    raise RuntimeError("unreachable")


def specialists_visited(actions: list[dict]) -> list[str]:
    out = set()
    for a in actions:
        node = a.get("node")
        if node in SPECIALISTS:
            out.add(node)
        elif node == "dispatch":
            cat = (a.get("arguments") or {}).get("category")
            if cat in SPECIALISTS:
                out.add(cat)
    return sorted(out)


def args_match(actual: dict, wanted: dict) -> bool:
    for k, w in wanted.items():
        a = actual.get(k)
        if isinstance(w, str) and w.startswith("~"):
            if w[1:].lower() not in str(a).lower():
                return False
        elif isinstance(w, (int, float)) and not isinstance(w, bool):
            try:
                if abs(float(a) - float(w)) > 0.01:
                    return False
            except (TypeError, ValueError):
                return False
        elif a != w:
            return False
    return True

_CHAR_MAP = {
    **dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2212"), "-"),  # all dash variants
    **dict.fromkeys(map(ord, "\u2018\u2019\u02bc"), "'"),                    # curly single quotes
    **dict.fromkeys(map(ord, "\u201c\u201d"), '"'),                           # curly double quotes
    ord("\u00a0"): " ",                                                       # non-breaking space
}


def norm(s: str) -> str:
    return s.translate(_CHAR_MAP).lower()

def evaluate(case: dict, run: Run) -> list[Check]:
    exp = case["expected"]
    checks: list[Check] = []

    def add(name: str, dim: str, passed: bool, expected: Any = None, actual: Any = None) -> None:
        checks.append(Check(name, dim, bool(passed), expected, actual))

    v = run.values
    actions = v.get("actions_taken", [])
    called = {c["name"] for c in run.tool_calls} | {r["name"] for r in run.tool_results if r["name"]}
    response = "\n\n".join(run.ai_texts)
    rlow = norm(response) 
    escalated = run.interrupted or v.get("resolution_status") == "escalated"
    reason = v.get("escalation_reason") or (run.payload or {}).get("escalation_reason")

    # --- routing ---
    if "router_category" in exp:
        rec = next((a for a in actions if a.get("node") == "router"), None)
        got = ((rec or {}).get("result") or {}).get("category")
        got = [got] if isinstance(got, str) else got
        add("router_category", "routing", got is not None and set(exp["router_category"]) <= set(got),
            exp["router_category"], got)
    conf = v.get("confidence")
    if "router_confidence_min" in exp:
        add("confidence_min", "routing", conf is not None and conf >= exp["router_confidence_min"],
            f">= {exp['router_confidence_min']}", conf)
    if "router_confidence_max" in exp:
        add("confidence_max", "routing", conf is not None and conf <= exp["router_confidence_max"],
            f"<= {exp['router_confidence_max']}", conf)
    visited = specialists_visited(actions)
    if "specialist" in exp:
        want = exp["specialist"]
        add("specialist", "routing", (not visited) if want is None else (want in visited), want, visited)
    if "specialists_visited" in exp:
        add("specialists_visited", "routing", set(exp["specialists_visited"]) == set(visited),
            sorted(exp["specialists_visited"]), visited)

    # --- tools ---
    for t in exp.get("tools_called", []):
        add(f"tool_called:{t}", "tool_recall", t in called, True, t in called)
    for t in exp.get("tools_not_called", []):
        add(f"tool_not_called:{t}", "tool_precision", t not in called, False, t in called)
    if "max_tool_calls" in exp:
        add("max_tool_calls", "tool_precision", len(run.tool_calls) <= exp["max_tool_calls"],
            f"<= {exp['max_tool_calls']}", len(run.tool_calls))
    if "tool_order" in exp:
        names = [c["name"] for c in run.tool_calls]
        idx = [names.index(t) if t in names else None for t in exp["tool_order"]]
        ok = None not in idx and all(a < b for a, b in zip(idx, idx[1:]))
        add("tool_order", "guardrail", ok, exp["tool_order"], names)
    for tool, wanted in exp.get("tool_args", {}).items():
        calls = [c for c in run.tool_calls if c["name"] == tool]
        add(f"tool_args:{tool}", "guardrail", any(args_match(c["args"], wanted) for c in calls),
            wanted, [c["args"] for c in calls])
    for tool, needle in exp.get("tool_result_contains", {}).items():
        results = [r["content"] for r in run.tool_results if r["name"] == tool]
        add(f"tool_result:{tool}", "guardrail", any(norm(needle) in norm(r) for r in results),
            needle, [short(r, 100) for r in results])

    # --- response ---
    for alts in exp.get("response_must_contain_any", []):
        add("response_any:" + "|".join(alts), "response", any(a.lower() in rlow for a in alts),
                alts, short(response, 160))
    for bad in exp.get("response_must_not_contain", []):
        add(f"response_excludes:{bad}", "response", norm(bad) not in rlow, f"no '{bad}'", short(response, 160))
    if "ai_message_count" in exp:
        add("ai_message_count", "response", len(run.ai_texts) == exp["ai_message_count"],
            exp["ai_message_count"], len(run.ai_texts))

    # --- escalation / state ---
    if "escalated" in exp:
        add("escalated", "guardrail", escalated == exp["escalated"], exp["escalated"], escalated)
    if "escalation_reason" in exp:
        add("escalation_reason", "guardrail", reason == exp["escalation_reason"], exp["escalation_reason"], reason)
    if "escalation_reason_in" in exp:
        add("escalation_reason", "guardrail", reason in exp["escalation_reason_in"], exp["escalation_reason_in"], reason)
    if "resolution_status" in exp:
        add("resolution_status", "state", v.get("resolution_status") == exp["resolution_status"],
            exp["resolution_status"], v.get("resolution_status"))
    if "clarify_attempts" in exp:
        add("clarify_attempts", "state", v.get("clarify_attempts", 0) == exp["clarify_attempts"],
            exp["clarify_attempts"], v.get("clarify_attempts", 0))
    if exp.get("pending_categories_empty"):
        add("pending_categories_empty", "state", not v.get("pending_categories"), [], v.get("pending_categories"))
    if "escalation_payload_fields" in exp:
        keys = set((run.payload or {}).keys())
        missing = [f for f in exp["escalation_payload_fields"] if f not in keys]
        add("escalation_payload_fields", "guardrail", run.interrupted and not missing,
            exp["escalation_payload_fields"], sorted(keys) if run.interrupted else "graph did not pause")
    if "crm_escalation_count" in exp:
        try:
            n: Any = len(http_get("/escalations", status="pending", customer_id=case["customer_id"]))
        except Exception as e:  # noqa: BLE001
            n = f"error: {short(str(e), 80)}"
        add("crm_escalation_count", "guardrail", n == exp["crm_escalation_count"], exp["crm_escalation_count"], n)
    return checks


def run_unit(case: dict) -> list[Check]:
    st = dict(case["state"])
    if st.pop("last_has_tool_call", False):
        st["messages"] = [AIMessage(content="", tool_calls=[
            {"name": "get_subscription", "args": {"customer_id": "CUST-0001"}, "id": "call_1"}])]
    else:
        st["messages"] = [AIMessage(content="All done.")]
    got = route_specialist(st)
    want = case["expected"]["route"]
    return [Check("route", "routing", got == want, want, got)]


def render_transcript(msgs: list) -> list[str]:
    out = []
    for m in msgs:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls or []:
                out.append(f"AI -> TOOL {tc.get('name')}({json.dumps(tc.get('args', {}), default=str)})")
            t = text_of(m.content).strip()
            if t:
                out.append(f"AI: {t}")
        elif isinstance(m, ToolMessage):
            out.append(f"TOOL[{m.name}]: {short(text_of(m.content), 300)}")
        elif isinstance(m, HumanMessage):
            out.append(f"HUMAN: {text_of(m.content)}")
    return out


def run_case(case: dict) -> CaseResult:
    res = CaseResult(eval_id=case["id"], name=case["name"], area=case.get("area", ""))
    t0 = time.time()
    try:
        if case.get("type") == "unit":
            res.checks = run_unit(case)
        else:
            run = execute_graph(case)
            res.checks = evaluate(case, run)
            res.response = "\n\n".join(run.ai_texts)
            res.tool_calls = run.tool_calls
            res.transcript = render_transcript(run.new_messages)
            res.final_state = {
                k: run.values.get(k)
                for k in ("resolution_status", "escalation_reason", "category", "pending_categories",
                          "confidence", "clarify_attempts", "turn_count")
            }
            res.final_state["interrupted"] = run.interrupted
            res.final_state["interrupt_payload"] = run.payload
        res.score = sum(c.passed for c in res.checks) / len(res.checks) if res.checks else 0.0
        res.passed = bool(res.checks) and all(c.passed for c in res.checks)
    except Exception as e:  # noqa: BLE001
        res.error = f"{type(e).__name__}: {short(str(e), 400)}"
    res.duration_s = time.time() - t0
    return res


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def build_report(results: list[CaseResult]) -> dict:
    n = len(results)
    passed = sum(r.passed for r in results)
    errored = sum(1 for r in results if r.error)
    dims: dict[str, list[bool]] = defaultdict(list)
    areas: dict[str, list[bool]] = defaultdict(list)
    failing = Counter()
    for r in results:
        areas[r.area].append(r.passed)
        for c in r.checks:
            dims[c.dimension].append(c.passed)
            if not c.passed:
                failing[c.name.split(":")[0]] += 1
    rate = lambda xs: (sum(xs) / len(xs)) if xs else None  # noqa: E731
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_cases": n,
        "passed": passed,
        "failed": n - passed - errored,
        "errored": errored,
        "pass_rate": passed / n if n else 0.0,
        "avg_score": sum(r.score for r in results) / n if n else 0.0,
        "dimensions": {d: rate(v) for d, v in sorted(dims.items())},
        "by_area": {a: {"passed": sum(v), "total": len(v)} for a, v in sorted(areas.items())},
        "top_failing_checks": failing.most_common(10),
        "cases": [asdict(r) for r in results],
    }


def pct(x: Optional[float]) -> str:
    return "  n/a" if x is None else f"{x:.0%}"


def print_report(rep: dict) -> None:
    print("\n" + "=" * 72)
    print("  PULSECHECK AGENT EVALUATION REPORT")
    print("=" * 72)
    print(f"  Cases: {rep['total_cases']}   passed: {rep['passed']} ({rep['pass_rate']:.0%})   "
          f"failed: {rep['failed']}   errored: {rep['errored']}   avg score: {rep['avg_score']:.0%}")
    print("\n  Dimensions:")
    for d, v in rep["dimensions"].items():
        print(f"    {d:<15} {pct(v)}")
    print("\n  By area:")
    for a, s in rep["by_area"].items():
        print(f"    {a:<12} {s['passed']}/{s['total']}")
    if rep["top_failing_checks"]:
        print("\n  Most common failing checks:")
        for name, count in rep["top_failing_checks"]:
            print(f"    {count:>3}  {name}")
    bad = [c for c in rep["cases"] if not c["passed"]]
    if bad:
        print("\n  Failing cases: " + ", ".join(c["eval_id"] for c in bad))
    print("=" * 72)


def print_case(r: CaseResult, verbose: bool) -> None:
    if r.error:
        print(f"      💥 {r.error}")
    for c in r.checks:
        if not c.passed:
            print(f"      ✗ {c.name}: expected {short(c.expected, 80)} | got {short(c.actual, 100)}")
    if verbose or r.error is None and not r.passed and r.transcript:
        for line in r.transcript:
            print(f"        {short(line, 200)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    global _reseed_enabled
    ap = argparse.ArgumentParser(description="Run the Pulsecheck agent evaluation")
    ap.add_argument("--ids", nargs="+", help="run only these eval ids")
    ap.add_argument("--area", help="run only one area (billing, technical, refund, router, hybrid, escalation, regression, unit)")
    ap.add_argument("--limit", "-n", type=int, help="run at most N cases")
    ap.add_argument("--delay", type=float, default=2.5, help="seconds between cases (Groq free-tier rate limits)")
    ap.add_argument("--output", "-o", help="write the full JSON report here")
    ap.add_argument("--golden-set", help="path to golden_set.jsonl")
    ap.add_argument("--lint", action="store_true", help="validate the dataset and exit (no LLM / backend)")
    ap.add_argument("--no-reseed", action="store_true", help="do not call /admin/reseed between cases")
    ap.add_argument("--skip-seed-check", action="store_true", help="skip the seed-data assumptions check")
    ap.add_argument("--verbose", "-v", action="store_true", help="print the transcript of every case")
    args = ap.parse_args()

    path = Path(args.golden_set) if args.golden_set else Path(__file__).parent / "golden_set.jsonl"
    if not path.exists():
        sys.exit(f"❌ golden set not found: {path}")
    cases = load_cases(path)
    errs = lint(cases)
    if errs:
        print("❌ dataset lint failed:")
        for e in errs:
            print("   -", e)
        sys.exit(2)
    print(f"✓ dataset lint passed ({len(cases)} cases)")
    if args.lint:
        return

    if args.ids:
        cases = [c for c in cases if c["id"] in set(args.ids)]
    if args.area:
        cases = [c for c in cases if c.get("area") == args.area]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        sys.exit("❌ no cases matched the filters")

    if args.no_reseed:
        _reseed_enabled = False
    if any(c.get("type") != "unit" for c in cases):
        if not preflight(cases, check_seed=not args.skip_seed_check):
            sys.exit(2)

    print(f"\n🧪 running {len(cases)} case(s)\n")
    results: list[CaseResult] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} {case['name']}", flush=True)
        r = run_case(case)
        results.append(r)
        icon = "✅" if r.passed else ("💥" if r.error else "❌")
        print(f"    {icon} {r.score:.0%}  {r.duration_s:.1f}s")
        print_case(r, args.verbose)
        if args.delay > 0 and i < len(cases) and case.get("type") != "unit":
            time.sleep(args.delay)

    rep = build_report(results)
    print_report(rep)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(rep, indent=2, default=str, ensure_ascii=False), encoding="utf-8")
        print(f"  📄 report saved to {out}")
    sys.exit(0 if rep["passed"] == rep["total_cases"] else 1)


if __name__ == "__main__":
    main()