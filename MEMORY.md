# Project Memory — Intelligent Data Extraction

> Living log of decisions and current state. Read this first every session. Update after every task.
> For architecture/deployment details → see `docs/`.

---

## Decision Log

- [2026-07-25] — Env var architecture (Independent service env files) → `docs/adr/001-env-var-strategy.md`
- [2026-07-24] — Docs structure (`README`, `docs/`, `docs/adr/`) → self-evident from repo layout
- [2026-07-24] — AI agent context files (`CLAUDE.md`, `.agents/AGENTS.md`) → self-evident
- [2026-07-26] — Email ingestion has two modes: automated (OAuth webhook) and manual (user pastes text + attaches files via `/submit` dashboard screen). Both hit the same `/api/ingest` endpoint. Architecture doc updated.
- [2026-07-28] — Formulated 6-Phase Technical Implementation Plan for step-by-step modular development & vibe coding alignment → `implementation_plan.md`
- [2026-08-01] — Phase 1 complete: FastAPI scaffold with CORS, /health, pydantic-settings config, requirements.txt
- [2026-08-02] — Documented and explained backend requirements.txt package stack and architectural purpose
- [2026-07-28] — Accepted Manual Ingestion First (Vertical Slice Strategy) → `docs/adr/002-manual-first-vertical-slice.md`
- [2026-08-10] — Prisma moved into `backend/prisma/` — it is exclusively a backend concern (Python client, DATABASE_URL in backend/.env). All prisma commands run from `backend/`.
- [2026-08-12] — Phase 2 complete: Prisma schema synced, Python client generated, db.py lifespan integrated in main.py, and Pydantic API schemas built in app/models/schemas.py.
- [2026-08-17] — Explicit DB Pre-Seeding & Startup Verification Guard → `docs/adr/003-explicit-db-seeding-preflight-guard.md`
- [2026-08-17] — Phase 3 complete: Created `app/db/seed.py`, core security module (bcrypt/JWT), auth & workspace dependencies (`get_current_workspace` dual auth), signup/login/me/workspace endpoints, lifespan pre-flight seed guard, and comprehensive pytest test suite (3/3 passing).
- [2026-08-20] — Phase 4 complete: Gemini service wrapper, 3-stage extraction pipeline (classify → extract → validate), Template CRUD, dual-mode ingest endpoint (JSON + file), quota check — 10/10 tests passing.
- [2026-08-23] — Switched frontend framework from Next.js to Vite + React for `frontend/` (dashboard portal). Future public site (landing page, blog) will be a separate package using Next.js or Astro. → `docs/adr/004-vite-react-dashboard.md`
- [2026-08-23] — Phase 5 complete: Full Vite + React dashboard built (Login, Signup, Dashboard, Submit, Logs, Templates, Settings). ThemeContext with system/light/dark mode + FOUC prevention. Design token system in tokens.css. GET /ingest backend companion route added. Zero TS errors, clean build.
- [2026-08-23] — Fixed Pydantic v2 UserWarning for `TemplateCreate` and `TemplateUpdate` by using `schema_` field attribute with `alias="schema"` and `populate_by_name=True`.
- [2026-08-23] — Fixed `POST /api/v1/ingest/json` to receive JSON body (`IngestJsonPayload`) matching frontend client payload.
- [2026-08-23] — Configured `GEMINI_MODEL` setting in `config.py` defaulting to `gemini-3.6-flash` (upgraded from deprecated legacy `gemini-1.5-flash`).
- [2026-08-23] — Enhanced Submit Page UX: explicit schema template selector dropdown, zero-template empty state banner, matched template result badges, and backend template_id override.
- [2026-08-23] — Built custom `TemplateSelect` UI component with glassmorphism popover backdrop, option card field list preview, AI intent classifier highlight, and click-outside popover dismissal.
- [2026-08-24] — Verified PostgreSQL database integrity (all 21 workspaces, 21 users, 7 templates intact); restarted backend server on port 8000.
- [2026-08-30] — Added hybrid ingestion route `POST /ingest/submit` (multipart). Accepts optional text body + optional file attachment in a single request. Gemini processes both sources together via new `generate_with_text_and_file()`. Old `/ingest/json` and `/ingest/file` kept for backward compat. Frontend Submit page gains a third "Text + File" tab.

- [2026-08-31] — Phase 6 complete: Async webhook dispatcher for outbound delivery, inbound generic + SendGrid adapters with secret URL tokens, webhook CRUD & delivery audit logs. Fully tested and integrated.
- [2026-09-02] — Upgraded `POST /api/v1/inbound/{inbound_secret}` into a Universal Inbound Adapter. Automatically normalizes field aliases and subject lines across SendGrid, Mailgun, Postmark, AWS SES, Zapier, Make, and custom webhooks without requiring provider-specific endpoints or vendor lock-in.
- [2026-09-03] — Added "Inbound Webhook" section to the Settings page UI. Exposes the inbound URL, provides rotation capabilities via the `POST /webhooks/inbound/rotate` endpoint, and adds integration instructions for no-code tools and cURL.
- [2026-09-03] — Created "Integrations" UI page to allow users to create and monitor outbound webhooks (including a ping tool and delivery history viewer). Added client-side CSV/JSON data export capabilities to the "Logs" page.
- [2026-09-04] — Streamlined the "Submit Document" UI by merging the three input tabs into a single unified form where both text and file attachments are optional but supported together.
- [2026-09-05] — Completed full technical audit and implemented all fixes for technical debt, error handling, types, testing, pagination, and UX issues identified in the audit report. Codebase is now robust and production-ready.
- [2026-09-07] — Removed dedicated `/inbound/sendgrid/{secret}` route. Its two unique behaviours (attachment2 support and unsupported-MIME skip) were ported into the universal `/{secret}` adapter via a new `_resolve_file()` helper. Any new provider is supported by adding a field alias — no new route needed.
- [2026-09-07] — Executed full end-to-end backend test suite (29/29 tests passed in 25.98s) and frontend TypeScript verification (0 errors). Confirmed complete system stability.
- [2026-09-16] — Implemented "Template Library" feature using a Configuration-as-Code architecture. Pre-built templates are stored in a static backend registry instead of polluting the Postgres database. Users can duplicate these templates directly into their workspace via the frontend UI.

---

## To-Do (6-Phase Execution Roadmap)

### ✅ Completed Setup
- [x] Independent Env var architecture (`backend/.env.example`, `frontend/.env.example`)
- [x] AI agent context files (`CLAUDE.md`, `.agents/AGENTS.md`)
- [x] Docs structure (`docs/architecture.md`, `docs/deployment.md`, `docs/adr/`)
- [x] Document manual submission channel + dashboard screen inventory in `docs/architecture.md`
- [x] Create 6-Phase Technical Implementation Plan (`implementation_plan.md`)

### ✅ Phase 1: Backend Scaffolding & Core Gateway
- [x] Create `backend/requirements.txt` & `backend/.env`
- [x] Build `backend/app/main.py` with FastAPI, CORS, and `/health` check
- [x] Build `backend/app/core/config.py` for settings

### ✅ Phase 2: Database Schema & Data Models
- [x] Create `backend/prisma/schema.prisma` — reviewed, finalised, indexes added
- [x] Run initial `prisma db push` & `prisma generate` (from `backend/` directory)
- [x] Integrate Prisma async client in `backend/app/core/db.py` & `main.py` lifespan
- [x] Build Pydantic API schemas in `backend/app/models/schemas.py`

### ✅ Phase 3: Authentication & Multi-Tenant Isolation
- [x] Database seeding script `backend/app/db/seed.py` (`Plan` tiers) + pre-flight startup guard in `main.py`
- [x] Implement JWT security helpers in `backend/app/core/security.py` (bcrypt & JWT)
- [x] Implement FastAPI auth dependencies `backend/app/core/auth.py` (dual JWT & API Key auth)
- [x] Build Auth endpoints `backend/app/api/auth.py` (signup, login, me)
- [x] Build Workspace endpoints `backend/app/api/workspaces.py` (details, update name, rotate API key, list members)
- [x] Register `api_router` in `backend/app/main.py` and verify test suite (3 passing tests)

### ✅ Phase 4: AI Extraction Engine (Gemini)
- [x] Integrate Gemini client service `backend/app/services/gemini_service.py`
- [x] Build 3-stage pipeline in `backend/app/services/extraction_pipeline.py`
- [x] Create consolidated ingestion endpoint `backend/app/api/ingest.py`
- [x] Create Template management endpoints `backend/app/api/templates.py`

### ✅ Phase 5: Vite + React Frontend Dashboard & Manual Ingestion UI
- [x] Scaffold Vite + React (TypeScript) application in `frontend/`
- [x] Design system: CSS variables, global tokens, Inter font, dark/light/system theme
- [x] Auth pages, app shell, ThemeContext
- [x] Dashboard, Submit (Manual Ingestion), Logs, Templates, and Settings pages
- [x] Built custom `TemplateSelect` UI component and dual-mode inputs

### ✅ Phase 6: Async Webhook Delivery & Audit Trail
- [x] Add WebhookDelivery and WebhookEndpoint models to schema
- [x] Implement async webhook dispatcher `backend/app/services/webhook_dispatcher.py` (HMAC signatures, delivery logs)
- [x] Implement outbound Webhook CRUD API `backend/app/api/webhooks.py`
- [x] Implement detailed audit log API `backend/app/api/logs.py`
- [x] Implement inbound generic and SendGrid adapters `backend/app/api/inbound.py`
- [x] Complete end-to-end integration tests (17 passing tests)
