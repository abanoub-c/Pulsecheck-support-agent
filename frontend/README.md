# Pulsecheck Support

Pulsecheck Support is a responsive multi-agent customer-support operations demo for a fictional SaaS company that sells API and uptime monitoring to developer teams. It is designed as a portfolio and freelance case study using synthetic data.

## Stack

React + TypeScript + Vite, React Router, Express BFF, Tailwind CSS semantic tokens, Zod, Recharts, `react-markdown` + DOMPurify, Vitest and Playwright. IBM Plex Sans/Mono and Lucide React are self-hosted through package dependencies. No platform or builder badge is included in the source, HTML or UI.

## Run locally

```bash
pnpm install
cp .env.example .env
pnpm dev
```

Open `http://localhost:3000`. The BFF listens on `0.0.0.0` and serves the Vite app in development. `GET /_app/health` is an unauthenticated runtime health endpoint; `GET /api/health` reports agent readiness.

## Mock mode

Preview is designed to work without external services. `MOCK_API=true` is the default and keeps synthetic customer, ticket, subscription, incident, thread and escalation state in the running Node process. `POST /api/demo/reset` restores the initial fixture, clears generated chats and decisions, and restores the seeded $299 refund-review conversation and escalation. In live backend mode, it also clears transcript rows and LangGraph checkpoints before reseeding the CRM. The five demo paths are available through sample prompts:

1. Crestpoint Systems downgrade succeeds and shows billing tool steps.
2. Halcyon Cloud’s $299 refund is prepared and held for manager review.
3. A vague message receives exactly one clarifying question.
4. Asking for a human escalates immediately.
5. “Simulate a tool failure” demonstrates safe recovery.

The shared fixtures contain 25 customers, 25 subscriptions, 55 tickets and 7 incidents. All 25 CRM customers are available in the Chat customer picker; the server validates each customer against its CRM records (or an optional `DEMO_CUSTOMER_IDS` restriction). State is intentionally in-memory in mock mode and returns to its fixture baseline after a server restart; the CRM owns persistence when configured.

## Environment

See `.env.example` for the safe defaults. `AGENT_API_URL` and `CRM_API_URL` are server-only. `MAX_MESSAGE_CHARS` defaults to 500 and `RATE_LIMIT_MESSAGES_PER_HOUR` defaults to 30. The BFF validates inputs with Zod, allow-lists chat customer IDs, rate-limits messages/resets, sets security headers, sanitizes agent Markdown in the browser, and never sends internal service URLs or API keys to the client.

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

Open `http://localhost:3000`. The Python service reads `GROQ_API_KEY` and the CRM database configuration from the repository root `.env`. `frontend/.env` contains only the Node BFF's service URLs, port, and matching internal-service key. In live mode, chat, thread replay, escalations and human decisions use LangGraph; clients, incidents, ticket analytics and customer details use the CRM database. Demo reset reseeds the CRM and clears the agent's in-process thread logs. Copy `.env.example` to `.env` to use the standalone mock instead.

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

Set the prompted `PULSECHECK_DATABASE_URL` and `GROQ_API_KEY` on `pulsecheck-agent`. Set `CORS_ORIGINS` on `pulsecheck-bff` to the Vercel site origin, for example `https://your-project.vercel.app`. Separate multiple allowed site origins with commas. The Blueprint generates `INTERNAL_API_KEY` for the agent and passes the same value to the BFF. Render may assign a different service hostname if a name is unavailable; use the actual `pulsecheck-bff` URL in the next step.

### 3. Vercel

Create a Vercel project from this repository with the project root set to `frontend`. Use the Vite build (`pnpm build`) and output directory `dist`. Set this build environment variable to the BFF's public Render origin, with no `/api` suffix:

```text
VITE_API_BASE_URL=https://your-pulsecheck-bff.onrender.com
```

Redeploy after changing this value because Vite embeds it in the browser bundle. `frontend/vercel.json` supplies the SPA route fallback so direct links such as `/chat` work.

### What persists

- `conversations` and `conversation_messages` hold the customer-facing history and execution traces. The Chat page can list and reopen conversations for the selected customer.
- LangGraph's Postgres checkpointer holds the agent state needed to resume a thread after the Render service restarts.
- Local SQLite development keeps the transcript in SQLite but uses an in-memory graph checkpointer. Set `PULSECHECK_DATABASE_URL` to Neon/PostgreSQL on Render to enable durable graph checkpoints.
- Mock mode remains process-local and is intended for previews, not shared production history.

The app has no sign-in or staff/customer authorization yet. Treat this deployment as a synthetic-data demo; add authentication and access control before storing real customer conversations. CORS restricts browser origins but does not authenticate API callers.

## Checks and build

```bash
pnpm typecheck
pnpm test
pnpm build
pnpm start
```

The production container builds the Vite output and runs the Express BFF with `PORT` (default 3000). No payment processing, direct Node-to-LLM call or raw model chain-of-thought is included.

## Assumptions

- CRM and agent URLs are not configured in the current workspace, so mock mode is the useful default.
- The managed database stays disabled because the specified architecture gives persistence to the CRM.
- Mock data is shared by one running preview process and is resettable; durable multi-instance production state belongs in the external CRM/agent services.
- The delivered target is a working Preview/checkpoint, not an automatically published public site.
