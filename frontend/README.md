# Pulsecheck Support

Pulsecheck Support is a responsive multi-agent customer-support operations demo for a fictional SaaS company that sells API and uptime monitoring to developer teams. It is designed as a portfolio and freelance case study using synthetic data.

## Stack

React + TypeScript + Vite, React Router, Express BFF, Tailwind CSS semantic tokens, Zod, Recharts, `react-markdown` + DOMPurify, Vitest and Playwright. IBM Plex Sans/Mono and Lucide React are self-hosted through package dependencies. No platform or builder badge is included in the source, HTML or UI.

## Run locally

```bash
# Run from the repository root once to create the shared local settings file.
cp .env.example .env

# Then enter frontend to install and run the UI/BFF.
cd frontend
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The BFF listens on `0.0.0.0` and serves the Vite app in development. `GET /_app/health` is an unauthenticated runtime health endpoint; `GET /api/health` reports agent readiness.

## Mock mode

Set `MOCK_API=true` to run without external services; this keeps synthetic customer, ticket, subscription, incident, thread and escalation state in the running Node process. `POST /api/demo/reset` restores the initial fixture, clears generated chats and decisions, and restores the seeded $299 refund-review conversation and escalation. In live backend mode, it also clears transcript rows and LangGraph checkpoints before reseeding the CRM. The five demo paths are available through sample prompts:

1. Crestpoint Systems downgrade succeeds and shows billing tool steps.
2. Halcyon Cloud’s $299 refund is prepared and held for manager review.
3. A vague message receives exactly one clarifying question.
4. Asking for a human escalates immediately.
5. “Simulate a tool failure” demonstrates safe recovery.

The shared fixtures contain 25 customers, 25 subscriptions, 55 tickets and 7 incidents. All 25 CRM customers are available in the Chat customer picker; the server validates each customer against its CRM records (or an optional `DEMO_CUSTOMER_IDS` restriction). State is intentionally in-memory in mock mode and returns to its fixture baseline after a server restart; the CRM owns persistence when configured.

## Environment

See the repository-root `.env.example` for the complete variable list. Keep the single local `.env` in the repository root; the Python service, agent, Node BFF, and Vite all load settings from there. `AGENT_API_URL`, `CRM_API_URL`, and `INTERNAL_API_KEY` are server-only. Deployment platforms should receive their values through Render or Vercel environment settings.

All agent nodes use the shared factory in [`agent/llm_config.py`](../agent/llm_config.py). Change `LLM_PROVIDER`, `LLM_MODEL`, the provider key, and optional `LLM_*` settings in the root `.env`; the router, specialists, and summarizer pick them up after the Python service restarts. Supported providers are Groq, OpenAI, Anthropic, and OpenAI-compatible endpoints. Provider packages are listed in the root `requirements.txt`.

## Python CRM and agent mode

The local workspace is configured to use the combined FastAPI service in the repository root (`MOCK_API=false`). Start the Python service from the repository root in one terminal:

```powershell
uvicorn service:app --host 127.0.0.1 --port 8001 --reload
```

In a second terminal, start the UI/BFF from `frontend`:

```powershell
cd frontend
pnpm dev
```

Open `http://localhost:3000`. The Python service and frontend use the same repository-root `.env`; `AGENT_PORT` and `FRONTEND_PORT` keep their local ports separate. Set `MOCK_API=true` to use the standalone mock, or set `MOCK_API=false` and provide a valid `GROQ_API_KEY` to use the real agent and CRM. In live mode, chat, thread replay, escalations and human decisions use LangGraph; clients, incidents, ticket analytics and customer details use the CRM database. Demo reset reseeds the CRM and clears the agent's in-process thread logs.

The CRM's customer list and ticket analytics endpoints provide the projections the UI needs. For a deployed setup, configure the same `INTERNAL_API_KEY` in both services and use the public URL of the combined FastAPI service for the BFF's `AGENT_API_URL` and `CRM_API_URL` values.

**Production difference:** the production customer ID must come from a verified server login/session, never from an untrusted browser-selected value; this demo intentionally has no login wall.

## Production deployment: Neon + Render + Vercel

The deployment uses one Neon PostgreSQL database, two Render web services, and the Vite UI on Vercel. The Express BFF is required: it validates browser requests and adds the private service key before calling the Python agent/CRM.

### 1. Neon

Create a Neon database and copy its PostgreSQL connection string. Keep the SSL option (`sslmode=require`) in the URL. Render's Python service uses the same `PULSECHECK_DATABASE_URL` for CRM records, conversation transcripts, and LangGraph checkpoints. On first startup it creates the CRM/conversation tables and the checkpointer creates its own tables. The database role must be allowed to create tables.

### 2. Render

Create a Blueprint from the repository root using [`render.yaml`](../render.yaml). It defines:

- `pulsecheck-agent`: the combined FastAPI agent and CRM service.
- `pulsecheck-bff`: the Express API service that Vercel calls.

Set the prompted `PULSECHECK_DATABASE_URL` to the Neon connection URL (including `sslmode=require`) and set `GROQ_API_KEY` on `pulsecheck-agent`. The Blueprint uses the root `Dockerfile` for the FastAPI + agent service and `frontend/Dockerfile` for the Express BFF. It generates `INTERNAL_API_KEY` for the agent and passes the same value to the BFF. Set `CORS_ORIGINS` on `pulsecheck-bff` to the Vercel site origin, for example `https://your-project.vercel.app`; separate multiple origins with commas. The model provider and name default to Groq and `openai/gpt-oss-20b`; change `LLM_PROVIDER` and `LLM_MODEL` in Render if you switch providers, and add that provider's API key in Render's environment settings. Use the actual BFF URL in the next step.

The Blueprint enables `PULSECHECK_ENABLE_ADMIN=1` so the Reset Demo Data control can reseed the CRM and delete saved chat checkpoints. Keep this deployment on synthetic demo data: the app does not yet authenticate staff, so anyone who can reach the reset endpoint can restore the demo state.

### 3. Vercel

Create a Vercel project from this repository with the project root set to `frontend`. `frontend/vercel.json` sets the Vite build command, frozen pnpm install, `dist` output, and SPA route fallback. Set this build environment variable to the BFF's public Render origin, with no `/api` suffix:

```text
VITE_API_BASE_URL=https://your-pulsecheck-bff.onrender.com
```

Redeploy after changing this value because Vite embeds it in the browser bundle. `frontend/vercel.json` supplies the SPA route fallback so direct links such as `/chat` work.

### Render Free cold starts

Render Free web services can spin down after inactivity. The first request wakes the BFF and agent; allow roughly a minute for them to start. The UI retries safe data reads during transient network, 502, 503, or 504 errors, and Chat waits up to 85 seconds for `/api/health` to report the agent ready before it sends a message. It never automatically repeats chat, escalation-decision, or reset writes. A persistent error after this window points to a deployment or environment setting problem rather than normal sleep.

### What persists

- `conversations` and `conversation_messages` hold the customer-facing history and execution traces. The Chat page can list and reopen conversations for the selected customer.
- LangGraph's Postgres checkpointer holds the agent state needed to resume a thread after the Render service restarts.
- Local SQLite development keeps the transcript in SQLite but uses an in-memory graph checkpointer. Set `PULSECHECK_DATABASE_URL` to Neon/PostgreSQL on Render to enable durable graph checkpoints.
- Mock mode remains process-local and is intended for previews, not shared production history.

The app has no sign-in or staff/customer authorization yet. This deployment is suitable for synthetic demo data; add authentication and access control before storing real customer conversations. CORS restricts browser origins but does not authenticate API callers.

## Checks and build

```bash
pnpm typecheck
pnpm test
pnpm build
pnpm start
```

The production container builds the Vite output and runs the Express BFF with `PORT` (default 3000). No payment processing, direct Node-to-LLM call or raw model chain-of-thought is included.
