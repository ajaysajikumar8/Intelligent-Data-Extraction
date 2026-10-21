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

### 🚧 Phase 7: BYOAK (Bring Your Own API Key) — see `docs/adr/005-byoak-key-management.md`
- [x] Encrypt Gemini key at rest (Fernet, `ENCRYPTION_KEY`) + live validation on save
- [x] `PUT/DELETE /api/v1/workspaces/current/gemini-key`, `PUT /api/v1/workspaces/current/platform-fallback` (paid-plan gated)
- [x] Wire `ingest.py` → pipeline key/fallback routing; fix pipeline bugs blocking it (`_call_with_fallback`, `api_key` plumbing, `confidenceScores` write)
- [x] Settings UI: AI Integration section (key save/remove, fallback toggle)
- [x] Verified end-to-end against live Gemini
- [ ] Record `api_key_source` on `DocumentLog` (workspace key vs. platform vs. mid-run fallback)
- [ ] "Upgrade" flow for the free-plan fallback block (currently just a toast)

### 📋 Phase 8: Product review fixes (2026-10-15 new-user walkthrough)
Backlog tracked as GitHub issues, milestone "First-run experience": [#1–#13](https://github.com/ajaysajikumar8/Intelligent-Data-Extraction/issues). Labels: `bug`/`ux`/`product`/`tech-debt` + `p0`/`p1`/`p2`.
- [x] #1 Logs/Submit now show the real failure reason (2026-10-21): `frontend/src/lib/failure.ts` `describeFailure()` normalises the 3 `validationErrors` shapes (`[{field,message}]`, `{error}`, `{pipeline_error}`). Verified in a real browser (Playwright, no-key workspace, light theme). Uncommitted, no frontend test runner yet.
- [x] Submit toast now reflects status (SUCCESS / NEEDS_REVIEW / UNMATCHED / FAILED with real reason); verified in browser. Submit button disabled with no templates is correct (extraction needs a template) — only first-run guidance is missing → #2.
- [ ] Found while verifying #1: Logs.tsx uses ~12 undefined CSS vars (`--bg-card`, `--text-color`… vs `--color-*` in tokens.css); React missing-`key` warning at Logs.tsx:125.
- [ ] P0 blockers: #2 (first-run checklist), #14 (first-run access decision)
- [ ] Private items (not in repo): pricing and billing, target customer and job, 3–5 user interviews, real extraction-quality test with a Gemini key on sample invoices
