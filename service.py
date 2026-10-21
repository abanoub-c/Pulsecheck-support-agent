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
    AGENT_PORT              local Python service port (default 8000; Render injects PORT)
    CRM_API_URL             how the agent reaches the CRM. Defaults to http://127.0.0.1:$AGENT_PORT/crm
    INTERNAL_API_KEY        shared secret; the Node server sends it as X-Internal-Key. REQUIRED when deployed.
    ALLOWED_ORIGINS         CORS origins (default http://localhost:3000)
    DEMO_CUSTOMER_IDS       optional comma-separated restriction; when unset, CRM customers can chat
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
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Iterator, Literal, Optional

ROOT = os.path.dirname(os.path.abspath(__file__))
from project_env import load_project_env

load_project_env()

# main.py imports `routes.seed_data` / `models` relative to backend/app, so make that folder importable.
sys.path.insert(0, os.path.join(ROOT, "backend", "app"))

PORT = os.getenv("PORT", os.getenv("AGENT_PORT", "8000"))
CRM_API_URL = os.getenv("CRM_API_URL", f"http://127.0.0.1:{PORT}/crm").rstrip("/")
os.environ["API_BASE"] = CRM_API_URL  # the combined service always routes agent tools through its mounted CRM

import requests  # noqa: E402
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, StreamingResponse  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import MemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from agent.graph import builder  # noqa: E402
from agent.state import new_support_state  # noqa: E402
from backend.app.main import (  # noqa: E402
    Conversation,
    ConversationMessage,
    Customer,
    SessionLocal,
    app as crm_app,
    seed_database,
)

INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",") if o.strip()]
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "500"))
MAX_THREADS = int(os.getenv("MAX_THREADS", "500"))
KEEPALIVE_SECONDS = 10
DEMO_CUSTOMER_IDS = {
    c.strip()
    for c in os.getenv("DEMO_CUSTOMER_IDS", "").split(",")
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
    return (
        url.replace("postgresql+psycopg2://", "postgresql://")
        .replace("postgresql+psycopg://", "postgresql://")
        .replace("postgres://", "postgresql://")
    )


def _connect_checkpointer():
    """Use durable Neon/Postgres checkpoints in production, memory for local SQLite runs."""
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


def chat_customer_exists(customer_id: str) -> bool:
    if DEMO_CUSTOMER_IDS:
        return customer_id in DEMO_CUSTOMER_IDS
    try:
        response = requests.get(
            f"{CRM_API_URL}/customers/{requests.utils.quote(customer_id, safe='')}",
            headers={"X-Internal-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {},
            timeout=5,
        )
    except requests.RequestException as error:
        raise HTTPException(status_code=503, detail="The CRM customer service is unavailable.") from error
    if response.status_code == 404:
        return False
    if not response.ok:
        raise HTTPException(status_code=503, detail="The CRM customer service could not validate this customer.")
    return True


# ---------------------------------------------------------------------------
# Per-process logs (messages/steps for the UI). The conversation itself lives in the checkpointer.
# ---------------------------------------------------------------------------
class Runtime:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.threads: dict[str, dict[str, Any]] = {}
        self.escalation_threads: dict[str, str] = {}  # fallback only; the CRM row also stores thread_id
        self.busy: set[str] = set()
        self.resetting = False

    def claim(self, thread_id: str) -> bool:
        with self.lock:
            if self.resetting or thread_id in self.busy:
                return False
            self.busy.add(thread_id)
            return True

    def begin_reset(self) -> bool:
        with self.lock:
            if self.resetting or self.busy:
                return False
            self.resetting = True
            return True

    def end_reset(self) -> None:
        with self.lock:
            self.resetting = False

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
        headers = dict(kwargs.pop("headers", {}) or {})
        if INTERNAL_API_KEY:
            headers.setdefault("X-Internal-Key", INTERNAL_API_KEY)
        kwargs["headers"] = headers
        return requests.request(method, f"{CRM_API_URL}{path}", timeout=10, **kwargs)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"CRM unreachable: {e}") from e


def _snapshot(thread_id: str):
    snap = G().get_state({"configurable": {"thread_id": thread_id}})
    interrupts = [i for t in snap.tasks for i in (getattr(t, "interrupts", None) or ())]
    return snap, interrupts


def _as_utc_datetime(value: Any = None) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
    return datetime.now(timezone.utc)


def _json_value(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _saved_thread(thread_id: str) -> Optional[dict]:
    with SessionLocal() as db:
        conversation = db.get(Conversation, thread_id)
        if conversation is None:
            return None
        rows = db.scalars(
            select(ConversationMessage)
            .where(ConversationMessage.thread_id == thread_id)
            .order_by(ConversationMessage.created_at, ConversationMessage.id)
        ).all()
        return {
            "thread_id": conversation.thread_id,
            "customer_id": conversation.customer_id,
            "title": conversation.title,
            "status": conversation.status,
            "escalation_id": conversation.escalation_id,
            "state": conversation.agent_state or {},
            "steps": conversation.trace_steps or [],
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "messages": [
                {"id": row.id, "role": row.role, "content": row.content,
                 "at": row.created_at.isoformat(), "trace": row.trace}
                for row in rows
            ],
        }


def _save_conversation_message(th: dict, message: dict) -> None:
    now = datetime.now(timezone.utc)
    at = _as_utc_datetime(message.get("at"))
    with SessionLocal() as db:
        conversation = db.get(Conversation, th["thread_id"])
        if conversation is None:
            title = message["content"].strip().replace("\n", " ")[:237].strip()
            if len(message["content"].strip()) > 240:
                title = f"{title}…"
            conversation = Conversation(
                thread_id=th["thread_id"], customer_id=th["customer_id"],
                title=title or "Support conversation", status=th.get("status", "open"),
                created_at=at, updated_at=now,
            )
            db.add(conversation)
            db.flush()
        elif conversation.customer_id != th["customer_id"]:
            raise ValueError("This conversation belongs to a different customer.")
        if db.get(ConversationMessage, message["id"]) is None:
            db.add(ConversationMessage(
                id=message["id"], thread_id=th["thread_id"], role=message["role"],
                content=message["content"], trace=_json_value(message["trace"]) if message.get("trace") else None,
                created_at=at,
            ))
        conversation.updated_at = now
        conversation.status = th.get("status", conversation.status)
        if th.get("escalation_id"):
            conversation.escalation_id = th["escalation_id"]
        if th.get("state"):
            conversation.agent_state = _json_value(th["state"])
        db.commit()
        th["updated_at"] = now.isoformat()


def _save_conversation_step(th: dict, step: dict) -> None:
    with SessionLocal() as db:
        conversation = db.get(Conversation, th["thread_id"])
        if conversation is None:
            return
        steps = list(conversation.trace_steps or [])
        if not any(existing.get("id") == step["id"] for existing in steps):
            steps.append(_json_value(step))
            conversation.trace_steps = steps
            db.commit()


def _save_conversation_state(th: dict, state: dict, status: str, escalation_id: Optional[str] = None) -> None:
    now = datetime.now(timezone.utc)
    th["state"] = _json_value(state)
    th["status"] = status
    if escalation_id:
        th["escalation_id"] = escalation_id
    with SessionLocal() as db:
        conversation = db.get(Conversation, th["thread_id"])
        if conversation is None:
            return
        conversation.status = status
        conversation.agent_state = _json_value(state)
        conversation.updated_at = now
        if escalation_id:
            conversation.escalation_id = escalation_id
        db.commit()
        th["updated_at"] = now.isoformat()


def _load_thread(thread_id: str, customer_id: Optional[str] = None) -> Optional[dict]:
    """Load the searchable transcript and resumable LangGraph checkpoint for one thread."""
    th = RT.threads.get(thread_id)
    if th is not None:
        return th
    values = dict(G().get_state({"configurable": {"thread_id": thread_id}}).values or {})
    saved = _saved_thread(thread_id)
    if values:
        msgs = saved["messages"] if saved else []
        if not saved:
            for m in values.get("messages", []):
                text = _text(getattr(m, "content", "")).strip()
                if isinstance(m, HumanMessage) and text:
                    msgs.append({"id": uuid.uuid4().hex, "role": "user", "content": text,
                                 "at": _now(), "by": "customer"})
                elif isinstance(m, AIMessage) and text and not m.tool_calls:
                    msgs.append({"id": uuid.uuid4().hex, "role": "assistant", "content": text,
                                 "at": _now(), "by": "agent"})
        th = {"thread_id": thread_id, "customer_id": values.get("customer_id") or (saved or {}).get("customer_id"),
              "created_at": time.time(), "updated_at": (saved or {}).get("updated_at", _now()),
              "started": True, "messages": msgs,
              "steps": saved["steps"] if saved else [step for msg in msgs for step in (msg.get("trace") or {}).get("steps", [])],
              "pending_steps": [], "escalation_id": values.get("escalation_id") or (saved or {}).get("escalation_id"),
              "state": saved.get("state", {}) if saved else {},
              "status": saved.get("status", values.get("resolution_status", "open")) if saved else values.get("resolution_status", "open")}
        if not saved:
            for message in msgs:
                _save_conversation_message(th, message)
    elif saved:
        th = {"thread_id": thread_id, "customer_id": saved["customer_id"], "created_at": time.time(),
              "updated_at": saved["updated_at"],
              "started": False, "messages": saved["messages"],
              "steps": saved["steps"],
              "pending_steps": [], "escalation_id": saved["escalation_id"], "state": saved["state"],
              "status": saved["status"]}
    elif customer_id is not None:
        th = {"thread_id": thread_id, "customer_id": customer_id, "created_at": time.time(),
              "updated_at": _now(),
              "started": False, "messages": [], "steps": [], "pending_steps": [],
              "escalation_id": None, "state": {}, "status": "open"}
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
        th.setdefault("pending_steps", []).append(data)
        _save_conversation_step(th, data)
    elif event == "message":
        by = data.get("by", "agent")
        at = data.get("at") or _now()
        message = {
            "id": str(data.get("id") or uuid.uuid4().hex),
            "role": "human" if by == "human" else "user" if by == "customer" else data["role"],
            "content": data["content"],
            "at": at,
            "by": by,
        }
        if by == "human" and data.get("content") == th.get("pending_human_message"):
            message["id"] = th.get("pending_human_message_id", message["id"])
        if any(existing.get("id") == message["id"] for existing in th["messages"]):
            return
        if by != "customer":
            message["trace"] = {
                "steps": th.pop("pending_steps", []),
                "toolCalls": [],
                "state": th.get("state") or {
                    "category": None, "pending_categories": [], "confidence": None,
                    "clarify_attempts": 0, "turn_count": 0, "resolution_status": "open",
                    "escalation_reason": None,
                },
                "startedAt": at,
                "finishedAt": at,
            }
        th["messages"].append(message)
        _save_conversation_message(th, message)


def _state_view(values: dict, interrupts: list) -> dict:
    view = {k: values.get(k) for k in STATE_KEYS}
    payload = interrupts[0].value if interrupts and isinstance(interrupts[0].value, dict) else {}
    if not view["escalation_reason"]:
        view["escalation_reason"] = payload.get("escalation_reason")
    return view


def _latest_pending_escalation(customer_id: str) -> Optional[str]:
    try:
        r = requests.get(f"{CRM_API_URL}/escalations", params={"status": "pending", "customer_id": customer_id}, headers={"X-Internal-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {}, timeout=10)
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
    message_id: Optional[str] = Field(default=None, min_length=8, max_length=64)
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


def chat_stream(thread_id: str, customer_id: str, text: str, message_id: Optional[str] = None) -> Iterator[str]:
    th = _load_thread(thread_id, customer_id)
    if not RT.claim(thread_id):
        yield sse("error", {"message": "The agent is busy or the demo is being reset. Please try again.", "retryable": True})
        yield sse("done", {})
        return

    try:
        _record(th, "message", {"id": message_id, "role": "user", "content": text, "at": _now(), "by": "customer"})

        # A thread that is paused for a human must not receive new input (it would orphan the pause).
        if th["started"]:
            snap, interrupts = _snapshot(thread_id)
            if interrupts:
                ev, data = _message(WAITING_NOTICE)
                _record(th, ev, data)
                state = _state_view(snap.values, interrupts)
                _save_conversation_state(th, state, "escalated", th.get("escalation_id"))
                yield sse(ev, data)
                yield sse("state", state)
                yield sse("done", {})
                return

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
        state = _state_view(values, interrupts)
        thread_status = "escalated" if interrupts else state.get("resolution_status") or "open"
        _save_conversation_state(th, state, thread_status, th.get("escalation_id"))
        yield sse("state", state)
        yield sse("done", {})
    finally:
        RT.release(thread_id)


@app.post("/api/chat")
def chat(body: ChatRequest, _: None = Depends(require_key)) -> StreamingResponse:
    text = body.message.strip()
    if not THREAD_ID_RE.match(body.thread_id):
        raise HTTPException(status_code=422, detail="thread_id must be 8-64 characters: letters, digits, - or _")
    if not chat_customer_exists(body.customer_id):
        raise HTTPException(status_code=403, detail="Unknown demo customer")
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=422, detail=f"message must be 1-{MAX_MESSAGE_CHARS} characters")
    existing = _load_thread(body.thread_id)
    if existing and existing["customer_id"] and existing["customer_id"] != body.customer_id:
        raise HTTPException(status_code=409, detail="This thread belongs to a different customer")
    return StreamingResponse(
        chat_stream(body.thread_id, body.customer_id, text, body.message_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


# ---------------------------------------------------------------------------
# Threads, escalations, dashboard, health, reset
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    try:
        crm_ok = requests.get(f"{CRM_API_URL}/health", headers={"X-Internal-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {}, timeout=2).ok
    except requests.RequestException:
        crm_ok = False
    return {"status": "ok", "agent": "ready", "crm": "ok" if crm_ok else "unreachable"}


@app.get("/api/threads/{thread_id}")
def get_thread(thread_id: str, _: None = Depends(require_key)) -> dict:
    if not THREAD_ID_RE.match(thread_id):
        raise HTTPException(status_code=422, detail="Invalid thread_id")
    th = _load_thread(thread_id)
    if th is None:
        raise HTTPException(status_code=404, detail="Unknown thread")
    values: dict = {}
    interrupts: list = []
    if th["started"]:
        snap, interrupts = _snapshot(thread_id)
        values = dict(snap.values)
    status = "escalated" if interrupts else values.get("resolution_status", th.get("status", "open"))
    state = _state_view(values, interrupts) if values else th.get("state", _state_view(values, interrupts))
    return {"thread_id": thread_id, "customer_id": th["customer_id"], "status": status,
            "messages": th["messages"], "steps": th["steps"], "state": state,
            "escalation_id": th["escalation_id"], "updated_at": th.get("updated_at", _now())}


@app.get("/api/customers/{customer_id}/conversations")
def list_customer_conversations(
    customer_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    _: None = Depends(require_key),
) -> dict:
    with SessionLocal() as db:
        if db.get(Customer, customer_id) is None:
            raise HTTPException(status_code=404, detail="Customer not found")
        message_count = (
            select(func.count(ConversationMessage.id))
            .where(ConversationMessage.thread_id == Conversation.thread_id)
            .scalar_subquery()
        )
        last_message = (
            select(ConversationMessage.content)
            .where(ConversationMessage.thread_id == Conversation.thread_id)
            .order_by(ConversationMessage.created_at.desc(), ConversationMessage.id.desc())
            .limit(1)
            .scalar_subquery()
        )
        rows = db.execute(
            select(Conversation, message_count, last_message)
            .where(Conversation.customer_id == customer_id)
            .order_by(Conversation.updated_at.desc(), Conversation.thread_id)
            .limit(limit)
        ).all()
        items = []
        for conversation, count, preview in rows:
            items.append({
                "thread_id": conversation.thread_id,
                "customer_id": conversation.customer_id,
                "title": conversation.title,
                "status": conversation.status,
                "message_count": int(count or 0),
                "last_message_preview": (preview or "")[:180],
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat(),
            })
        return {"items": items}


_company_cache: dict[str, Any] = {"at": 0.0, "names": {}}


def _company_names() -> dict[str, str]:
    if time.time() - _company_cache["at"] > 60:
        try:
            rows = requests.get(f"{CRM_API_URL}/customers", headers={"X-Internal-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {}, timeout=10).json()
            _company_cache["names"] = {r["customer_id"]: r["company_name"] for r in rows}
            _company_cache["at"] = time.time()
        except (requests.RequestException, ValueError, KeyError, TypeError):
            pass
    return _company_cache["names"]


def _escalation_thread(esc: dict) -> Optional[str]:
    action = esc.get("proposed_action")
    return (action.get("thread_id") if isinstance(action, dict) else None) or RT.escalation_threads.get(esc["escalation_id"])


def _complete_escalation_resume(
    thread_id: str, customer_id: str, escalation_id: str, action: str, customer_message: str
) -> None:
    """Finish LangGraph work after the durable review decision has returned to the UI."""
    try:
        th = RT.threads.get(thread_id) or _load_thread(thread_id, customer_id)
        if th is None:
            return

        state = dict(th.get("state") or {})
        state.update({"resolution_status": "resolved", "escalation_reason": None})
        th["pending_human_message"] = customer_message
        th["pending_human_message_id"] = f"decision-{escalation_id}"
        # Keep the thread paused until the graph checkpoint is resumed, but make
        # the human's message visible in the durable transcript right away.
        th["status"] = "escalated"

        if not any(row.get("id") == th["pending_human_message_id"] for row in th["messages"]):
            reply = {"id": th["pending_human_message_id"], "role": "human", "content": customer_message, "at": _now()}
            th["messages"].append(reply)
            _save_conversation_message(th, reply)

        snapshot, interrupts = _snapshot(thread_id) if th["started"] else (None, [])
        if not interrupts:
            _save_conversation_state(th, state, "resolved", escalation_id)
            return

        _save_conversation_state(th, state, "escalated", escalation_id)
        config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 40}
        resume = {"action": "reject" if action == "reject" else "approve", "customer_message": customer_message}
        for chunk in G().stream(Command(resume=resume), config, stream_mode="updates"):
            for node, update in chunk.items():
                if node.startswith("__") or not isinstance(update, dict):
                    continue
                for event, data in events_for(node, update):
                    _record(th, event, data)

        snapshot, interrupts = _snapshot(thread_id)
        values = dict(snapshot.values or {})
        state = _state_view(values, interrupts)
        status = "escalated" if interrupts else state.get("resolution_status") or "resolved"
        _save_conversation_state(th, state, status, escalation_id)
    except Exception as error:  # noqa: BLE001
        print(f"Background escalation resume failed for {escalation_id}: {error}", flush=True)
    finally:
        RT.release(thread_id)


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
def decide(
    escalation_id: str,
    body: DecisionBody,
    background_tasks: BackgroundTasks,
    _: None = Depends(require_key),
) -> dict:
    r = crm("GET", f"/escalations/{escalation_id}")
    if r.status_code == 404:
        raise HTTPException(status_code=404, detail="No escalation with that id")
    if not r.ok:
        raise HTTPException(status_code=502, detail="Could not load the escalation record")
    esc = r.json()
    if esc.get("status") != "pending":
        raise HTTPException(status_code=409, detail=f"Escalation is already {esc.get('status', 'resolved')}.")

    thread_id = _escalation_thread(esc)
    resume_scheduled = bool(thread_id)
    if resume_scheduled and not RT.claim(thread_id):
        raise HTTPException(status_code=409, detail="This conversation is busy. Please retry the decision in a moment.")

    approved = body.action in ("approve", "edit")
    message = (body.customer_message or "").strip() or (DEFAULT_APPROVE if approved else DEFAULT_REJECT)
    try:
        decision = crm("PATCH", f"/escalations/{escalation_id}/decision", json={"decision": body.action, "note": body.note})
        if not decision.ok:
            raise HTTPException(status_code=decision.status_code, detail=decision.json().get("detail", "CRM rejected the decision"))

        refund_updated = False
        proposed_action = esc.get("proposed_action")
        refund_id = proposed_action.get("refund_id") if isinstance(proposed_action, dict) else None
        if refund_id:
            refund_action = "reject" if body.action == "reject" else "approve"
            refund_response = crm("PATCH", f"/refunds/{refund_id}", json={"action": refund_action, "note": body.note})
            refund_updated = refund_response.ok

        if resume_scheduled and thread_id:
            background_tasks.add_task(_complete_escalation_resume, thread_id, esc["customer_id"], escalation_id, body.action, message)

        return {"escalation_id": escalation_id, "decision": body.action, "resumed": False,
                "resume_scheduled": resume_scheduled, "refund_updated": refund_updated}
    except Exception:
        if resume_scheduled and thread_id:
            RT.release(thread_id)
        raise


@app.get("/api/dashboard/summary")
def dashboard_summary(_: None = Depends(require_key)) -> dict:
    def count(path: str, params: dict) -> Optional[int]:
        try:
            r = requests.get(f"{CRM_API_URL}{path}", params=params, headers={"X-Internal-Key": INTERNAL_API_KEY} if INTERNAL_API_KEY else {}, timeout=10)
            return len(r.json()) if r.ok else None
        except (requests.RequestException, ValueError):
            return None

    queries = (
        ("/escalations", {"status": "pending"}),
        ("/refunds", {"status": "pending_review"}),
        ("/incidents", {"status": "open"}),
    )
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        awaiting, refunds, incidents = pool.map(lambda query: count(*query), queries)
    return {"awaiting_review": awaiting, "refunds_pending_review": refunds, "open_incidents": incidents}


@app.post("/api/demo/reset")
def demo_reset(_: None = Depends(require_key)) -> dict:
    # Keep destructive demo reset opt-in in deployed environments. Check this
    # before deleting any LangGraph checkpoints so a disabled reset is a no-op.
    if os.getenv("PULSECHECK_ENABLE_ADMIN", "0") != "1":
        raise HTTPException(status_code=404, detail="Demo reset is disabled")

    if not RT.begin_reset():
        raise HTTPException(status_code=409, detail="Wait for active agent work to finish before resetting demo data.")

    try:
        saver = getattr(app.state, "saver", None)
        delete = getattr(saver, "delete_thread", None)
        thread_ids = set(RT.threads)
        # Every durable chat transcript has a CRM Conversation row with the
        # same thread ID as its LangGraph checkpoint. Read that compact index
        # instead of asking LangGraph to materialize every checkpoint (which
        # can fail or time out on a large Neon checkpoint history).
        try:
            with SessionLocal() as db:
                thread_ids.update(db.scalars(select(Conversation.thread_id)).all())
        except Exception as error:  # noqa: BLE001
            print(f"Could not enumerate saved chat records for demo reset: {error}", flush=True)
            raise HTTPException(status_code=500, detail="Could not read saved chat records; no demo data was reset.") from error

        if thread_ids and not delete:
            raise HTTPException(status_code=500, detail="This checkpointer cannot delete saved threads; no demo data was reset.")
        if delete:
            try:
                for thread_id in thread_ids:
                    delete(thread_id)
            except Exception as error:  # noqa: BLE001
                print(f"Could not clear saved agent checkpoints for demo reset: {error}", flush=True)
                raise HTTPException(status_code=500, detail="Could not clear all saved agent checkpoints; retry the reset.") from error

        # The CRM is mounted inside this same FastAPI app. Reseed it directly
        # instead of making an HTTP request back into this process; the loopback
        # request can time out while Postgres drops and recreates the seed tables.
        try:
            seed_database(force=True)
        except Exception as error:  # noqa: BLE001
            print(f"Could not restore the CRM seed data during demo reset: {error}", flush=True)
            raise HTTPException(status_code=500, detail="Could not restore the CRM database from the original seed data.") from error

        with RT.lock:
            RT.threads.clear()
            RT.escalation_threads.clear()
        _company_cache["at"] = 0.0
        return {"status": "reseeded", "message": "CRM data, chats, escalations, and agent checkpoints were restored to the original demo state."}
    finally:
        RT.end_reset()
