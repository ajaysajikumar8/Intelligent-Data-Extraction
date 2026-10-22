# Project Memory — Intelligent Data Extraction

> Living log of decisions and current state. Read this first every session. Update after every task.
> For architecture/deployment details → see `docs/`.

---

## Decision Log

> Entries older than the current phase are condensed to keep this file small. Full narrative detail for any entry still lives in git commit history (`git log -p -- MEMORY.md`) and in `docs/adr/`.

- [2026-07-24 → 2026-08-20] — Phases 0–4 complete (docs structure, env vars, agent context files, FastAPI scaffold, Prisma schema, auth/multi-tenancy, Gemini 3-stage extraction pipeline). → `docs/adr/001`–`003`.
- [2026-08-23 → 2026-08-30] — Phase 5 complete: Vite + React dashboard (all core pages), hybrid `/ingest/submit` (text+file) endpoint, TemplateSelect UI, Gemini model config fixes. → `docs/adr/004-vite-react-dashboard.md`
- [2026-08-31 → 2026-09-16] — Phase 6 complete: async webhook dispatcher, Universal Inbound Adapter (multi-provider), Integrations/Logs UI, full technical audit + fixes, Template Library (config-as-code). 29/29 backend tests, 0 TS errors.
- [2026-10-15] — BYOAK (Bring Your Own API Key) core implemented and verified end-to-end against live Gemini → `docs/adr/005-byoak-key-management.md`. Also fixed three pre-existing pipeline crash bugs and a regressed `GEMINI_MODEL` value.
- [2026-10-15] — Consolidated agent context files to a single source of truth: `.agents/AGENTS.md` is now the only real file. `CLAUDE.md`, `.clinerules`, and root `AGENTS.md` are symlinks to it — zero copy-paste drift across Claude Code, Cline, Antigravity/Cursor/Copilot/Codex/Windsurf. Verified via md5sum + live edit propagation test.
- [2026-10-15] — Archived stale `MEMORY.md` decision log entries (10.9KB → 3.4KB) and added a hard token-budget rule to `.agents/AGENTS.md` (archive when >~150 lines/5KB) so this file stays small going forward — see `## MEMORY.md Housekeeping` there.

---

## To-Do (6-Phase Execution Roadmap)

### ✅ Completed Setup + Phases 0–6
> Collapsed (all items done, stable, no longer iterated on). Full checklist history: `git log -p -- MEMORY.md`.
- [x] Setup: env vars, agent context files, docs structure, implementation plan
- [x] Phase 1: FastAPI scaffold, CORS, `/health`, config
- [x] Phase 2: Prisma schema, async client, Pydantic schemas
- [x] Phase 3: Auth (JWT + API key), workspace endpoints, DB seeding — 3/3 tests passing
- [x] Phase 4: Gemini service, 3-stage extraction pipeline, ingest + template endpoints
- [x] Phase 5: Vite + React dashboard (all core pages), design system, TemplateSelect UI
- [x] Phase 6: Webhook dispatcher, inbound adapters, audit logs — 17/17 tests passing

### 🚧 Phase 7: BYOAK — see `docs/adr/005-byoak-key-management.md`
- [x] Done: Fernet-encrypted key at rest + live validation, key/fallback endpoints (fallback paid-plan gated), pipeline key routing, Settings UI, verified against live Gemini.
- [ ] Record `api_key_source` on `DocumentLog` (#12); "Upgrade" flow for the free-plan fallback block (#13, currently a toast).

### 📋 Phase 8: Product review fixes (2026-10-15 new-user walkthrough)
Backlog = GitHub issues, milestone "First-run experience" ([#1–#14](https://github.com/ajaysajikumar8/Intelligent-Data-Extraction/issues)). Labels: `bug`/`ux`/`product`/`tech-debt` + `p0`/`p1`/`p2`.
- [x] #1 real failure reason in Logs/Submit — pushed (dc74712), closed. `frontend/src/lib/failure.ts` `describeFailure()` maps `validationErrors` shapes.
- [x] #4 (uncommitted) Submit keeps the result on page + JSON/CSV download (`lib/export.ts`, CSV formula-injection guard). Submit toast reflects status. Submit button disabled with no templates is correct (needs a template) — first-run guidance is #2.
- [x] Async extraction + resilience (uncommitted) → `docs/adr/006-async-extraction-queue.md`. `POST /ingest` 202+PENDING; in-process queue; retry/backoff + 60s per-call timeout; classified failures (`failures.py`, `{error, code}`); live `progress` column (additive `prisma db push`); all terminal states fire webhooks; inbound adapters now pass BYOAK key/fallback (was a bug). Frontend: `useDocumentPolling`, `ProgressPanel`, shared `FailureDetails`, Logs auto-refresh, Submit resumes after reload. **API contract change** for API-key callers.
- [x] QA (2026-10-22): backend 55/55, e2e 3/3, ~50 browser scenarios with a scripted fake AI (harness outside repo). Fixed: `GET /logs/{id}` dropped `progress`+`confidenceScores`; raw JSON/parser text on Submit; React key warning; undefined CSS vars in failure box. Real Gemini 503s ("high demand") during testing were handled as designed. A real SUCCESS through the new queue is still unconfirmed (see Next).
- [ ] Test workspace "Verify All Workspace" is on the Pro plan (rollback: planId → free). Local dev DB holds ~15 throwaway QA users/workspaces.
- [ ] Open: P0 #2 (first-run checklist), #14 (first-run access); no plan-change path (billing unbuilt); dashboard unusable on phones (fixed 240px sidebar, ~88–107px overflow at 390px) — file an issue; `docs/architecture.md` has local `file:///` paths (public repo); webhook URLs allow internal hosts (SSRF risk).
- [ ] Private items (not in repo): pricing/billing, target customer, 3–5 user interviews, real extraction-quality test on sample invoices.
