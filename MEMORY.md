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

### 🔲 Phase 4: AI Extraction Engine (Gemini 1.5 Flash)
- [ ] Integrate Gemini client service `backend/app/services/gemini_service.py`
- [ ] Build 3-stage pipeline in `backend/app/services/extraction_pipeline.py`
- [ ] Create dual-mode ingestion endpoint `backend/app/api/ingest.py` (JSON & Multipart)
- [ ] Create Template management endpoints `backend/app/api/templates.py`

### 🔲 Phase 5: Next.js Frontend Dashboard & Manual Ingestion UI
- [ ] Scaffold Next.js application structure in `frontend/`
- [ ] Overview Dashboard (`/`)
- [ ] Manual Ingestion UI (`/submit`) — text paste + file attachment dropzone
- [ ] Live Extraction Logs (`/logs`)
- [ ] Schema Template Manager (`/templates`)
- [ ] Settings & API Keys (`/settings`)

### 🔲 Phase 6: Async Webhook Delivery & Audit Trail
- [ ] Implement async webhook dispatcher `backend/app/services/webhook_dispatcher.py`
- [ ] Implement search & audit log API `backend/app/api/logs.py`
- [ ] End-to-end integration testing

