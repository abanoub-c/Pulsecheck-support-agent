# service.py — new file, repo root
from fastapi import FastAPI
from backend.app.main import app as crm_app
from agent.graph import builder
from langgraph.checkpoint.postgres import PostgresSaver
from tenacity import retry, stop_after_attempt, wait_exponential
import os
from contextlib import asynccontextmanager


def _checkpointer_url() -> str:
    url = os.environ["PULSECHECK_DATABASE_URL"]
    return url.replace("postgresql+psycopg2://", "postgresql://")

@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=2, max=15))
def _connect_checkpointer():
    ctx = PostgresSaver.from_conn_string(_checkpointer_url())
    saver = ctx.__enter__()
    saver.setup()   # idempotent — creates checkpoint tables on first run only
    return ctx, saver

@asynccontextmanager
async def lifespan(app: FastAPI):
    ctx, saver = _connect_checkpointer()
    app.state.graph = builder.compile(checkpointer=saver)
    yield
    ctx.__exit__(None, None, None)


app = FastAPI(title="Pulsecheck", lifespan=lifespan)
app.mount("/crm", crm_app)