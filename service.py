"""
Pulsecheck service: ONE FastAPI app that
  * mounts the CRM API at /crm   (your existing backend/app/main.py)
  * serves the agent API at /api (chat streaming, threads, escalations, decisions, dashboard)
and keeps your existing design: Postgres checkpointer (Neon) with a lifespan, retry on connect.

Belongs at: the project root.
Local run (no Postgres needed, uses an in-memory checkpointer and the CRM's SQLite):
    uvicorn service:app --port 8001 --reload        (set CRM_API_URL=http://127.0.0.1:8001/crm in .env)
Render:  start command  uvicorn service:app --host 0.0.0.0 --port $PORT

Differences from your previous service.py (all deliberate):
  1. seed_database() runs in the lifespan. Starlette does NOT run a mounted sub-app's startup hooks,
     so without this the CRM tables would never be created or seeded when mounted at /crm.
  2. PULSECHECK_DATABASE_URL is optional. If it is not a postgres URL the service falls back to
     MemorySaver, so local development works without Neon.
  3. /crm is guarded. The CRM has no auth (cancel, refund and reseed endpoints), so it only accepts
     calls from this machine (the agent's own tools) or requests carrying X-Internal-Key.
  4. The /api routes the web app needs (contract in the builder brief, section 7.2 and addendum 13).

Environment:
    GROQ_API_KEY            used by the agent nodes
    PULSECHECK_DATABASE_URL Neon/Postgres URL (CRM tables AND graph checkpoints); unset = SQLite + memory
    CRM_API_URL             how the agent reaches the CRM. Default http://127.0.0.1:$PORT/crm (right on Render;
                            locally set it to your uvicorn port, e.g. http://127.0.0.1:8001/crm)
    INTERNAL_API_KEY        shared secret; the Node server sends it as X-Internal-Key. REQUIRED when deployed.
    ALLOWED_ORIGINS         CORS origins (default http://localhost:3000)
    DEMO_CUSTOMER_IDS       allow-list of customer ids the chat accepts
    MAX_MESSAGE_CHARS       default 500
"""

from __future__ import annotations

import hmac
import json
import os
import queue
import re
import sys
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional
    pass

ROOT = os.path.dirname(os.path.abspath(__file__))
# main.py imports `routes.seed_data` / `models` relative to backend/app, so make that folder importable.
sys.path.insert(0, os.path.join(ROOT, "backend", "app"))

PORT = os.getenv("PORT", "8000")
CRM_API_URL = os.getenv("CRM_API_URL", f"http://127.0.0.1:{PORT}/crm").rstrip("/")
os.environ.setdefault("API_BASE", CRM_API_URL)  # agent/graph.py and agent/tools.py read API_BASE at import time

import requests  # noqa: E402
from fastapi import Depends, FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from agent.graph import builder  # noqa: E402
from agent.state import new_support_state  # noqa: E402
from backend.app.main import app as crm_app, seed_database  # noqa: E402

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "500"))
MAX_THREADS = int(os.getenv("MAX_THREADS", "500"))
KEEPALIVE_SECONDS = 10
DEMO_CUSTOMER_IDS = {
    c.strip()
    for c in os.getenv(
        "DEMO_CUSTOMER_IDS",
        "CUST-0006,CUST-0002,CUST-0022,CUST-0012,CUST-0005,CUST-0014,CUST-0019,CUST-0010",
    ).split(",")
    if c.strip()
}
THREAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
LOOPBACK = {"127.0.0.1", "::1", "localhost"}
SPECIALIST_LABELS = {"billing": "Billing specialist", "technical": "Technical specialist", "refund": "Refund specialist"}
STATE_KEYS = ("category", "pending_categories", "confidence", "clarify_attempts", "turn_count",
              "resolution_status", "escalation_reason")
WAITING_NOTICE = ("Your request is with a human specialist. Their reply will appear here as soon as "
                  "it is ready.")
DEFAULT_APPROVE = "A specialist reviewed your request and approved it. Thanks for your patience."
DEFAULT_REJECT = ("A specialist reviewed your request and could not approve it. Reply here if you "
                  "would like to talk it through.")


# ---------------------------------------------------------------------------
# Checkpointer + lifespan
# ---------------------------------------------------------------------------
def _checkpointer_url(url: str) -> str:
    return url.replace("postgresql+psycopg2://", "postgresql://").replace("postgres://", "postgresql://")


def _connect_checkpointer():
    """Postgres (Neon) when PULSECHECK_DATABASE_URL is a postgres URL, otherwise in-memory."""
    url = os.getenv("PULSECHECK_DATABASE_URL", "")
    if not url.startswith(("postgresql", "postgres")):
        return None, MemorySaver()

    from langgraph.checkpoint.postgres import PostgresSaver
    from tenacity import retry, stop_after_attempt, wait_exponential

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=15))
    def connect():
        ctx = PostgresSaver.from_conn_string(_checkpointer_url(url))
        saver = ctx.__enter__()
        saver.setup()  # idempotent: creates the checkpoint tables on first run only
        return ctx, saver

    return connect()


@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_database()  # mounted sub-apps do not run their own startup hooks
    if not INTERNAL_API_KEY and os.getenv("PORT"):
        print("WARNING: INTERNAL_API_KEY is not set on a deployed service; /api is open to anyone.")
    ctx, saver = _connect_checkpointer()
    app.state.saver = saver
    app.state.graph = builder.compile(checkpointer=saver)
    yield
    if ctx is not None:
        ctx.__exit__(None, None, None)


app = FastAPI(title="Pulsecheck", lifespan=lifespan)


class CrmGuard:
    """The CRM has no auth of its own. Allow /crm only from this machine (the agent's tools call it over
    127.0.0.1, with no X-Forwarded-For) or with the internal key. Pure ASGI so SSE responses are not buffered."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/crm"):
            headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
            has_key = bool(INTERNAL_API_KEY) and hmac.compare_digest(headers.get("x-internal-key", ""), INTERNAL_API_KEY)
            host = (scope.get("client") or ("", 0))[0]
            local = host in LOOPBACK and "x-forwarded-for" not in headers
            if not (has_key or local):
                await JSONResponse({"detail": "The CRM is internal."}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(CrmGuard)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["*"], allow_headers=["*"])
app.mount("/crm", crm_app)


def G() -> Any:
    return app.state.graph


def require_key(x_internal_key: str = Header(default="")) -> None:
    if INTERNAL_API_KEY and not hmac.compare_digest(x_internal_key, INTERNAL_API_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Key")


# ---------------------------------------------------------------------------
# Per-process logs (messages/steps for the UI). The conversation itself lives in the checkpointer.
# ---------------------------------------------------------------------------
class Runtime:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.threads: dict[str, dict[str, Any]] = {}
        self.escalation_threads: dict[str, str] = {}  # fallback only; the CRM row also stores thread_id
        self.busy: set[str] = set()

    def claim(self, thread_id: str) -> bool:
        with self.lock:
            if thread_id in self.busy:
                return False
            self.busy.add(thread_id)
            return True

    def release(self, thread_id: str) -> None:
        with self.lock:
            self.busy.discard(thread_id)


RT = Runtime()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b if isinstance(b, str) else str(b.get("text", "")) for b in content
                        if isinstance(b, (str, dict)))
    return "" if content is None else str(content)


def sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, ensure_ascii=False)}\n\n"


def _step(node: str, kind: str, title: str, detail: dict) -> tuple[str, dict]:
    return "step", {"id": uuid.uuid4().hex[:8], "at": _now(), "node": node, "kind": kind,
                    "title": title, "detail": detail}


def _message(content: str, by: str = "agent") -> tuple[str, dict]:
    return "message", {"role": "assistant", "content": content, "by": by, "at": _now()}


def crm(method: str, path: str, **kwargs: Any) -> requests.Response:
    try:
        return requests.request(method, f"{CRM_API_URL}{path}", timeout=10, **kwargs)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CRM unreachable: {e}") from e


def _snapshot(thread_id: str):
    snap = G().get_state({"configurable": {"thread_id": thread_id}})
    interrupts = [i for t in snap.tasks for i in (getattr(t, "interrupts", None) or ())]
    return snap, interrupts


def _load_thread(thread_id: str, customer_id: Optional[str] = None) -> Optional[dict]:
    """Return the thread log. After a restart the checkpoint may still exist (Postgres), so rebuild the
    visible messages from it. With customer_id given, create a fresh log when nothing exists yet."""
    th = RT.threads.get(thread_id)
    if th is not None:
        return th
    values = dict(G().get_state({"configurable": {"thread_id": thread_id}}).values or {})
    if values:
        msgs = []
        for m in values.get("messages", []):
            text = _text(getattr(m, "content", "")).strip()
            if isinstance(m, HumanMessage) and text:
                msgs.append({"role": "user", "content": text, "at": None, "by": "customer"})
            elif isinstance(m, AIMessage) and text and not m.tool_calls:
                msgs.append({"role": "assistant", "content": text, "at": None, "by": "agent"})
        th = {"customer_id": values.get("customer_id"), "created_at": time.time(), "started": True,
              "messages": msgs, "steps": [], "escalation_id": values.get("escalation_id")}
    elif customer_id is not None:
        th = {"customer_id": customer_id, "created_at": time.time(), "started": False,
              "messages": [], "steps": [], "escalation_id": None}
    else:
        return None
    with RT.lock:
        if len(RT.threads) >= MAX_THREADS:
            RT.threads.pop(min(RT.threads, key=lambda t: RT.threads[t]["created_at"]), None)
        RT.threads[thread_id] = th
    return th


def _tool_payload(raw: str) -> tuple[bool, Any]:
    try:
        parsed: Any = json.loads(raw)
    except (ValueError, TypeError):
        parsed = raw
    ok = not (isinstance(parsed, dict) and "error" in parsed)
    if isinstance(parsed, (dict, list)) and len(json.dumps(parsed, default=str)) > 2000:
        parsed = {"truncated": True, "preview": json.dumps(parsed, default=str)[:1500]}
    elif isinstance(parsed, str) and len(parsed) > 2000:
        parsed = parsed[:2000] + "..."
    return ok, parsed


def events_for(node: str, update: dict) -> list[tuple[str, dict]]:
    """Translate one LangGraph node update into the UI's step/message events."""
    out: list[tuple[str, dict]] = []
    msgs = update.get("messages") or []

    if node == "router":
        rec = next((a for a in update.get("actions_taken", []) if a.get("node") == "router"), None)
        result = (rec or {}).get("result") or {}
        conf = update.get("confidence")
        reasoning = update.get("classification_reasoning")
        reason = update.get("escalation_reason")
        if result.get("action") == "stayed_with_active_category":
            cat = result.get("category")
            out.append(_step(node, "classification", f"Follow-up message: staying with the {cat} specialist",
                             {"categories": [cat], "confidence": conf, "reasoning": reasoning, "continued": True}))
        else:
            cats = result.get("category") or []
            if reason == "tool_call_failed" and not cats:
                title = "Classification failed, handing over to a human"
            else:
                shown = ", ".join(cats) if cats else "unknown"
                title = f"Classified as {shown}" + (f" (confidence {conf:.2f})" if isinstance(conf, (int, float)) else "")
            out.append(_step(node, "classification", title, {
                "categories": cats, "confidence": conf, "reasoning": reasoning,
                "wants_human": reason == "customer_requested_human",
                "is_smalltalk": bool(msgs) and not update.get("clarify_attempts") and not reason,
            }))
        for m in msgs:
            if isinstance(m, AIMessage) and _text(m.content).strip():
                text = _text(m.content).strip()
                if update.get("clarify_attempts"):
                    out.append(_step(node, "clarification", "Asking one clarifying question", {"question": text}))
                else:
                    out.append(_step(node, "reply", "Greeting answered without a specialist", {"preview": text[:160]}))
                out.append(_message(text))

    elif node == "dispatch":
        cat = update.get("category")
        out.append(_step(node, "dispatch", f"Next specialist: {cat}" if cat else "No more specialists queued",
                         {"category": cat, "remaining": update.get("pending_categories", [])}))

    elif node in SPECIALIST_LABELS:
        label = SPECIALIST_LABELS[node]
        for m in msgs:
            if not isinstance(m, AIMessage):
                continue
            for tc in m.tool_calls or []:
                out.append(_step(node, "tool_call", f"{label} calls {tc.get('name')}",
                                 {"tool": tc.get("name"), "args": tc.get("args", {})}))
            text = _text(m.content).strip()
            if text and not m.tool_calls:
                out.append(_step(node, "reply", f"{label} replied", {"preview": text[:160]}))
                out.append(_message(text))

    elif node.endswith("_tools"):
        for m in msgs:
            if isinstance(m, ToolMessage):
                ok, result = _tool_payload(_text(m.content))
                out.append(_step(node, "tool_result", f"{m.name} {'returned' if ok else 'failed'}",
                                 {"tool": m.name, "ok": ok, "result": result}))

    elif node == "escalate":  # only reached after a human decision resumes the thread
        for m in msgs:
            if isinstance(m, AIMessage) and _text(m.content).strip():
                text = _text(m.content).strip()
                out.append(_step(node, "reply", "A human specialist replied", {"preview": text[:160]}))
                out.append(_message(text, by="human"))
    return out


def _record(th: dict, event: str, data: dict) -> None:
    if event == "step":
        th["steps"].append(data)
    elif event == "message":
        th["messages"].append({"role": data["role"], "content": data["content"], "at": data["at"], "by": data["by"]})


def _state_view(values: dict, interrupts: list) -> dict:
    view = {k: values.get(k) for k in STATE_KEYS}
    payload = interrupts[0].value if interrupts and isinstance(interrupts[0].value, dict) else {}
    if not view["escalation_reason"]:
        view["escalation_reason"] = payload.get("escalation_reason")
    return view


def _latest_pending_escalation(customer_id: str) -> Optional[str]:
    try:
        r = requests.get(f"{CRM_API_URL}/escalations", params={"status": "pending", "customer_id": customer_id}, timeout=10)
        rows = r.json() if r.ok else []
        return rows[0]["escalation_id"] if rows else None
    except (requests.RequestException, ValueError, KeyError):
        return None


# ---------------------------------------------------------------------------
# POST /api/chat  (Server-Sent Events)
# ---------------------------------------------------------------------------
class ChatRequest(BaseModel):
    thread_id: str
    customer_id: str
    message: str = Field(min_length=1)


def _pump(graph: Any, input_: Any, config: dict, q: "queue.Queue[tuple[str, Any]]") -> None:
    try:
        for chunk in graph.stream(input_, config, stream_mode="updates"):
            q.put(("chunk", chunk))
        q.put(("end", None))
    except Exception as e:  # noqa: BLE001
        q.put(("error", e))


def _error_event(e: Exception) -> tuple[str, dict]:
    s = str(e).lower()
    if "429" in s or "rate limit" in s or "rate_limit" in s:
        return "error", {"message": "The model is rate limited right now. Please try again in a moment.", "retryable": True}
    return "error", {"message": "Something went wrong while the agent was working. Please try again.", "retryable": True}


def chat_stream(thread_id: str, customer_id: str, text: str) -> Iterator[str]:
    th = _load_thread(thread_id, customer_id)
    th["messages"].append({"role": "user", "content": text, "at": _now(), "by": "customer"})

    # A thread that is paused for a human must not receive new input (it would orphan the pause).
    if th["started"]:
        snap, interrupts = _snapshot(thread_id)
        if interrupts:
            ev, data = _message(WAITING_NOTICE)
            _record(th, ev, data)
            yield sse(ev, data)
            yield sse("state", _state_view(snap.values, interrupts))
            yield sse("done", {})
            return

    if not RT.claim(thread_id):
        yield sse("error", {"message": "The agent is still working on your previous message.", "retryable": True})
        yield sse("done", {})
        return

    try:
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
        if th["started"]:
            input_: Any = {"messages": [HumanMessage(content=text)]}
        else:
            input_ = new_support_state(thread_id, customer_id, HumanMessage(content=text))
            th["started"] = True

        q: queue.Queue = queue.Queue()
        threading.Thread(target=_pump, args=(G(), input_, config, q), daemon=True).start()
        while True:
            try:
                kind, payload = q.get(timeout=KEEPALIVE_SECONDS)
            except queue.Empty:
                yield ": keepalive\n\n"  # keeps proxies from closing a slow stream
                continue
            if kind == "chunk":
                for node, update in payload.items():
                    if node.startswith("__") or not isinstance(update, dict):
                        continue
                    for ev, data in events_for(node, update):
                        _record(th, ev, data)
                        yield sse(ev, data)
            elif kind == "error":
                ev, data = _error_event(payload)
                yield sse(ev, data)
                yield sse("done", {})
                return
            else:
                break

        snap, interrupts = _snapshot(thread_id)
        values = dict(snap.values)
        if interrupts:
            payload = interrupts[0].value if isinstance(interrupts[0].value, dict) else {}
            esc_id = payload.get("escalation_id") or _latest_pending_escalation(customer_id)
            reason = payload.get("escalation_reason") or values.get("escalation_reason")
            if esc_id:
                RT.escalation_threads[esc_id] = thread_id
                th["escalation_id"] = esc_id
            ev, data = _step("escalate", "escalation", "Escalated to a human specialist",
                             {"reason": reason, "escalation_id": esc_id})
            _record(th, ev, data)
            yield sse(ev, data)
            yield sse("escalated", {"escalation_id": esc_id, "reason": reason, "thread_id": thread_id})
        yield sse("state", _state_view(values, interrupts))
        yield sse("done", {})
    finally:
        RT.release(thread_id)


@app.post("/api/chat")
def chat(body: ChatRequest, _: None = Depends(require_key)) -> StreamingResponse:
    text = body.message.strip()
    if not THREAD_ID_RE.match(body.thread_id):
        raise HTTPException(status_code=422, detail="thread_id must be 8-64 characters: letters, digits, - or _")
    if body.customer_id not in DEMO_CUSTOMER_IDS:
        raise HTTPException(status_code=403, detail="Unknown demo customer")
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=422, detail=f"message must be 1-{MAX_MESSAGE_CHARS} characters")
    existing = _load_thread(body.thread_id)
    if existing and existing["customer_id"] and existing["customer_id"] != body.customer_id:
        raise HTTPException(status_code=409, detail="This thread belongs to a different customer")
    return StreamingResponse(
        chat_stream(body.thread_id, body.customer_id, text),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Threads, escalations, dashboard, health, reset
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    try:
        crm_ok = requests.get(f"{CRM_API_URL}/health", timeout=2).ok
    except requests.RequestException:
        crm_ok = False
    return {"status": "ok", "agent": "ready", "crm": "ok" if crm_ok else "unreachable"}


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str, _: None = Depends(require_key)) -> dict:
    th = _load_thread(thread_id)
    if th is None:
        raise HTTPException(status_code=404, detail="Unknown thread")
    values: dict = {}
    interrupts: list = []
    if th["started"]:
        snap, interrupts = _snapshot(thread_id)
        values = dict(snap.values)
    status = "escalated" if interrupts else values.get("resolution_status", "open")
    return {"thread_id": thread_id, "customer_id": th["customer_id"], "status": status,
            "messages": th["messages"], "steps": th["steps"], "state": _state_view(values, interrupts),
            "escalation_id": th["escalation_id"]}


_company_cache: dict[str, Any] = {"at": 0.0, "names": {}}


def _company_names() -> dict[str, str]:
    if time.time() - _company_cache["at"] > 60:
        try:
            rows = requests.get(f"{CRM_API_URL}/customers", timeout=10).json()
            _company_cache["names"] = {r["customer_id"]: r["company_name"] for r in rows}
            _company_cache["at"] = time.time()
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass
    return _company_cache["names"]


def _escalation_thread(esc: dict) -> Optional[str]:
    action = esc.get("proposed_action")
    return (action.get("thread_id") if isinstance(action, dict) else None) or RT.escalation_threads.get(esc["escalation_id"])


@app.get("/api/escalations")
def list_escalations(status: str = Query(default="pending"), _: None = Depends(require_key)) -> list[dict]:
    r = crm("GET", "/escalations", params={"status": status})
    if not r.ok:
        raise HTTPException(status_code=502, detail=f"CRM error {r.status_code}")
    names = _company_names()
    rows = []
    for row in r.json():
        action = row.get("proposed_action")
        shown = {k: v for k, v in action.items() if k != "thread_id"} if isinstance(action, dict) else action
        rows.append({**row, "proposed_action": shown or None, "thread_id": _escalation_thread(row),
                     "company_name": names.get(row["customer_id"])})
    return rows


class DecisionBody(BaseModel):
    action: Literal["approve", "edit", "reject"]
    customer_message: Optional[str] = Field(default=None, max_length=1000)
    note: Optional[str] = Field(default=None, max_length=500)


@app.post("/api/escalations/{escalation_id}/decision")
def decide(escalation_id: str, body: DecisionBody, _: None = Depends(require_key)) -> dict:
    r = crm("GET", "/escalations", params={"status": "pending"})
    esc = next((e for e in (r.json() if r.ok else []) if e["escalation_id"] == escalation_id), None)
    if esc is None:
        raise HTTPException(status_code=404, detail="No pending escalation with that id")

    # Resume the paused conversation FIRST: the escalate node re-runs from the top on resume and looks for
    # its still-pending CRM row; resolving the row before this would make it create a duplicate.
    thread_id = _escalation_thread(esc)
    resumed = False
    th = _load_thread(thread_id) if thread_id else None
    if th is not None and th["started"]:
        _, interrupts = _snapshot(thread_id)
        if interrupts and RT.claim(thread_id):
            try:
                approved = body.action in ("approve", "edit")
                message = (body.customer_message or "").strip() or (DEFAULT_APPROVE if approved else DEFAULT_REJECT)
                resume = {"action": "approve" if approved else "reject", "customer_message": message}
                config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
                for chunk in G().stream(Command(resume=resume), config, stream_mode="updates"):
                    for node, update in chunk.items():
                        if node.startswith("__") or not isinstance(update, dict):
                            continue
                        for ev, data in events_for(node, update):
                            _record(th, ev, data)
                resumed = True
            except Exception as e:  # noqa: BLE001
                raise HTTPException(status_code=500, detail=f"Could not resume the conversation: {e}") from e
            finally:
                RT.release(thread_id)

    d = crm("PATCH", f"/escalations/{escalation_id}/decision", json={"decision": body.action, "note": body.note})
    if not d.ok:
        raise HTTPException(status_code=d.status_code, detail=d.json().get("detail", "CRM rejected the decision"))

    refund_updated = False
    action = esc.get("proposed_action")
    refund_id = action.get("refund_id") if isinstance(action, dict) else None
    if refund_id and body.action in ("approve", "reject"):
        rr = crm("PATCH", f"/refunds/{refund_id}", json={"action": body.action, "note": body.note})
        refund_updated = rr.ok
    return {"escalation_id": escalation_id, "decision": body.action, "resumed": resumed,
            "refund_updated": refund_updated}


@app.get("/api/dashboard/summary")
def dashboard_summary(_: None = Depends(require_key)) -> dict:
    def count(path: str, params: dict) -> Optional[int]:
        try:
            r = requests.get(f"{CRM_API_URL}{path}", params=params, timeout=10)
            return len(r.json()) if r.ok else None
        except (requests.RequestException, ValueError):
            return None

    return {"awaiting_review": count("/escalations", {"status": "pending"}),
            "refunds_pending_review": count("/refunds", {"status": "pending_review"}),
            "open_incidents": count("/incidents", {"status": "open"})}


@app.post("/api/demo/reset")
def demo_reset(_: None = Depends(require_key)) -> dict:
    r = crm("POST", "/admin/reseed")
    if r.status_code == 404:
        raise HTTPException(status_code=403, detail="Reset is disabled on this CRM (PULSECHECK_ENABLE_ADMIN=0)")
    if not r.ok:
        raise HTTPException(status_code=502, detail=f"CRM error {r.status_code}")
    saver = getattr(app.state, "saver", None)
    delete = getattr(saver, "delete_thread", None)
    for tid in list(RT.threads):
        if delete:
            try:
                delete(tid)
            except Exception:  # noqa: BLE001
                pass
    with RT.lock:
        RT.threads.clear()
        RT.escalation_threads.clear()
    _company_cache["at"] = 0.0
    return {"status": "reseeded"}