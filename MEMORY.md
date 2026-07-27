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
- [2026-07-28] — Accepted Manual Ingestion First (Vertical Slice Strategy) → `docs/adr/002-manual-first-vertical-slice.md`

---

## To-Do (6-Phase Execution Roadmap)

### ✅ Completed Setup
- [x] Independent Env var architecture (`backend/.env.example`, `frontend/.env.example`)
- [x] AI agent context files (`CLAUDE.md`, `.agents/AGENTS.md`)
- [x] Docs structure (`docs/architecture.md`, `docs/deployment.md`, `docs/adr/`)
- [x] Document manual submission channel + dashboard screen inventory in `docs/architecture.md`
- [x] Create 6-Phase Technical Implementation Plan (`implementation_plan.md`)

### 🔲 Phase 1: Backend Scaffolding & Core Gateway
- [ ] Create `backend/requirements.txt` & `backend/.env.example`
- [ ] Build `backend/app/main.py` with FastAPI, CORS, and `/health` check
- [ ] Build `backend/app/core/config.py` for settings

### 🔲 Phase 2: Database Schema & Data Models
- [ ] Create `prisma/schema.prisma` for Workspaces, Users, Templates, Document Logs, Webhooks
- [ ] Run initial `npx prisma db push`
- [ ] Build Pydantic schemas in `backend/app/models/schemas.py`

### 🔲 Phase 3: Authentication & Multi-Tenant Isolation
- [ ] Implement JWT security helpers in `backend/app/core/security.py`
- [ ] Build Auth endpoints `backend/app/api/auth.py` (signup, login, profile)
- [ ] Build Workspace endpoints `backend/app/api/workspaces.py`

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

