# Pulsecheck Support — Implementation Plan

**Status:** Approved by the user; implementation and acceptance checks are complete.

## Scope and approach

Build the requested four-page support-demo application as a greenfield React/TypeScript + Vite frontend with an Express BFF in the same Node process. The configured Webdev project has `server: true`, `database: false`, and Preview port `3000`; preserve those settings. Serve the Vite frontend and BFF together in development, listening on `0.0.0.0:3000`, and serve the compiled frontend from Express in production. Keep browser calls on relative `/api/...` paths. Do not add real sign-in, direct browser-to-Python calls, Node-side LLM calls, payment processing, or Python-service changes.

The local environment currently has no `CRM_API_URL` or `AGENT_API_URL`, and no CRM service is listening on port 8000. Therefore set the usable demo default to `MOCK_API=true`; implement the specified BFF contracts and a mock CRM/agent adapter with the five required scenarios. Keep optional server-side adapters for the real services when their URLs are configured. The mock’s seeded data and escalation/thread state will be shared within the running Node process and resettable by `POST /api/demo/reset`; without the external CRM or a persistent database, that mock state returns to its fixture baseline after a server restart. The supplied spec treats the CRM as the real persistence owner, so do not enable the managed database unless the user changes that requirement.

Copy/port the project’s shared synthetic seed data into typed application fixtures, preserving its 25 customers, 25 subscriptions, 55 tickets and 7 incidents. Make all 25 CRM customers available in the Chat picker and validate selected IDs against CRM records; an optional `DEMO_CUSTOMER_IDS` environment value may narrow that set. Map the existing ticket states (`resolved`, `open`, `escalated`) to solved/unsolved as specified. All demo data remains synthetic.

## Design system

- **Design movement:** warm humanist, Swiss-influenced service-console UI: disciplined information hierarchy and operational precision softened by stone surfaces and terracotta actions.
- **Core principles:** calm and trustworthy; make handoffs and tool actions legible; dense data stays grouped and scannable; controls remain accessible and predictable.
- **Color philosophy:** stone neutrals carry the 60% canvas / 30% surface-and-text roles; terracotta is the 10% action accent. Semantic success, danger, warning and info colors communicate state, always paired with labels. Use the exact Light/Dark CSS tokens and accessible text variants in the build prompt, not ad-hoc component hex values.
- **Layout paradigm:** persistent 256px sidebar collapsing to a 64px rail; a stable operational workspace for Dashboard and Analytics; horizontally scrollable, locally contained Clients table; focused 760px Chat column. No top header.
- **Signature elements:** terracotta focus/action color; warm stone canvas/surface planes; IBM Plex Mono execution traces and IDs.
- **Interaction philosophy:** explicit human review actions, visible focus, progressive disclosure for the audit trail, clear loading/empty/error states, and no raw chain-of-thought.
- **Animation:** restrained 150–220ms ease-out state transitions and subtle sidebar width changes; honor `prefers-reduced-motion` and avoid animation that blocks interaction.
- **Typography:** self-host IBM Plex Sans for UI and IBM Plex Mono for tool traces, IDs and numbers. Follow the prompt’s body/small/label sizes and clear hierarchy.
- **Brand essence:** “A clear, accountable support-operations demo that shows how specialist agents hand off decisions to humans.” Personality: calm, precise, accountable.
- **Brand voice:** direct and transparent. Examples: “Waiting for human review.” and “4 steps · 2 tools · View execution trace.”
- **Wordmark / logo concept:** show only the product name **Pulsecheck Support** with a small Lucide Activity mark in the sidebar; do not add builder/platform branding. Use a matching product mark for project metadata as required by the Webdev workspace, separate from the app UI.
- **Signature brand color:** terracotta `#C2410C` in Light mode and `#FB923C` in Dark mode.

Design read: multi-page SaaS support demo for recruiters, clients and support-ops reviewers; greenfield; warm, humanist operational console. Dials: visual variance 3/10, motion 3/10, information density 7/10, asset dependence 2/10, brand fidelity to the supplied UI specification 8/10. The design is intentionally data- and interaction-led; do not add stock illustrations or decorative hero imagery.

## Application structure

```text
index.html
public/
  manus-routes.json
  pulsecheck-mark.svg
src/
  main.tsx
  App.tsx
  components/
    AppSidebar.tsx
    AppShell.tsx
    chat/            # execution trace
    ui/              # buttons, chips, dialogs, toasts, skeletons, empty/error states
  pages/             # Dashboard, Clients, Chat, Analytics
  lib/               # typed API client, SSE parser, URL-state helpers, formatters
  styles/            # semantic CSS variables and Tailwind mapping
server/
  index.ts            # Express + Vite middleware in dev; static serving in production
  routes/             # health, chat, threads, escalations, customers, analytics, reset
  services/           # CRM/agent adapters, mock orchestration, session/thread state
  data/seed-data.json # port of supplied fixtures
  middleware/         # Zod validation, allowlist, rate limits, security headers
app.config.ts         # project logo metadata required by Webdev
tests/
  unit/               # SSE parser, validation, mappings, business-rule helpers
  e2e/                # key user paths with Playwright
README.md
.env.example
package.json + pinned pnpm lock/config
Dockerfile
```

The route manifest declares `/`, `/dashboard`, `/clients`, `/chat`, and `/analytics`, with `/` opening the Dashboard. Keep route titles and the manifest synchronized with the source router. Use the official IBM Plex family and Lucide React package; use only imported icons needed by the interface.

## Build workflow after plan approval

1. Create `TODO.md` with outcome-sized items containing the prompt’s concrete acceptance clauses; keep all required behavior, values, copy, states and exceptions explicit.
2. Register TypeScript diagnostics through the project’s managed `runtime/post-edit` configuration before writing application source. Pin pnpm and declare reviewed install-script policy before dependency installation.
3. Add the route manifest and project metadata, convert the shared fixture data, then build the Express BFF contracts and mock scenarios. Implement input validation, allowlisted chat IDs, rate limiting, cold-start handling, SSE streaming and mock reset behavior.
4. Implement the four pages and shared sidebar/theme, then wire the API client, URL-backed Clients state, human decision flow and accessible chart/table views.
5. Add README setup/env/mock/deployment notes, `.env.example`, a production Dockerfile, and an unauthenticated health route. Keep secrets server-side and keep mock mode usable without credentials. Prepare the project’s matching container deployment declaration once the service is listening, but do not publish it unless requested; auto-publish is currently off.
6. Run unit/type/build checks and the prompt’s explicit acceptance pass: exercise key flows and responsive layouts at 360px, 900px and 1440px, check keyboard use, trace the refund/escalation/approval path, and inspect key states. Use the smallest repairs needed for any failure.
7. Save the completed source to the initialized Manus project’s canonical `main` checkpoint and provide its Preview URL. Do not claim public publication unless a publish result confirms it.

## Confirmed assumptions

- Run the mock as the default because no service URLs are configured; retain adapters for later CRM/agent connection.
- Leave the managed database disabled because the supplied architecture assigns persistence to the CRM. Mock mutations are shared only while the single preview process is running and reset to fixtures after restart.
- Deliver a live Preview and checkpoint, not a public publication, because the request asks to execute the build prompt but does not ask to publish.
