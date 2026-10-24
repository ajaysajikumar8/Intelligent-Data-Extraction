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
- [x] #1, #4, async queue (ADR-006), backup model, SSRF fix (ADR-007) — done, pushed.
- [x] #14 + #2 free-trial credits + first-run checklist → `docs/adr/008-free-trial-credits.md` (committed).
- [x] #21 + #5/#6/#7 (2026-10-24) → `docs/adr/009-email-verification-and-signup-limits.md`. Trial credits now granted on **email verification** (Resend; no key = link logged), daily grant cap, disposable-domain block, per-IP/per-domain signup + resend rate limits (in-process), `/verify-email` page + unverified banner. #5 login hint only after typing; #6 field-level plain-language errors (backend handler + `ApiError.fieldErrors`); #7 `.test` rejection is intended, message friendlier. Schema: `User.emailVerifiedAt`, `Workspace.trialGrantedAt` (`db push` done; 417 existing users backfilled verified). 120/120 tests, flow verified live in browser. Committed (not pushed). Issues #2, #5, #6, #7, #14, #21 closed 2026-10-24. Dev ports: backend 8005, frontend 5178.
- [x] #15 + #9 + #8 (2026-10-24, merged PR #22, closed): mobile drawer, app name via `lib/brand.ts` ("Intelligent Data Extraction" placeholder — real brand name still a product decision), Templates add-feedback (name-matched; backend still allows duplicate copies).
- [x] #10 batch upload (2026-10-24, on main, issue closed) → `docs/adr/010-batch-upload.md`. Client-side: 2–20 files → one `/ingest` each, 3 in flight (`useBatchSubmit`, `BatchPanel`); server cap `EXTRACTION_MAX_IN_FLIGHT_PER_WORKSPACE`=25 (429). 122/122 tests; UI verified in Playwright with failing docs (no AI key) — success path with live Gemini not re-verified. Trial-credit pre-check added (batch limited to remaining credits). Unsubmitted files live only in the open tab. Logs page shows batch docs as plain rows (no batch grouping). Live Gemini was overloaded (AI_BUSY) when tested, so no live success run yet.
- [x] #16 "Try again" (2026-10-24, branch `feat/retry-failed-extractions`) → `docs/adr/011-retry-failed-extractions.md`. `POST /logs/{id}/retry` retries in place (text only; files not stored); UI on Submit + Logs drawer. 127/127 tests. #17 deliberately not built: `BAD_AI_OUTPUT` was 1/301 in dev data (issue says measure first) — reopen if it shows up in real use.
- [~] #11 review screen (2026-10-24, branch `feat/review-correct-flow`) → `docs/adr/012-review-screen-for-needs-review.md`. Field-by-field `ReviewForm` + "Approve as is"; `/correct` is now NEEDS_REVIEW-only, atomic, skips no-op learning examples. 131/131 tests. **Open:** Excel (.xlsx) + Tally export (needs product decisions; .xlsx needs a new npm package). Issue #11 stays open.
- Local QA: `backend/.env` has relaxed signup limits (50/hour per IP and per domain; defaults 5 and 3) — local only, remove before deploying. Backend restarted 2026-10-24 on :8005 (log in scratchpad).
- [x] #12 (2026-10-25) → `docs/adr/013-record-key-source-and-model.md`. `DocumentLog.apiKeySource` + `modelUsed` (schema pushed to dev DB; **prod needs the same push**). 136/136 tests. Shown in the Logs drawer. Old rows stay NULL.
- [x] #18 (2026-10-25): built a Logs badge, then **removed it** — product call: users can check Logs; not worth the code or polling. Closed as not planned. Revisit email/browser notifications only if real users ask. Open gap noticed: leaving Submit mid-batch drops files not yet uploaded (they live only in the tab).
- [ ] **Before launch:** set `RESEND_API_KEY` + `EMAIL_FROM` (verified domain) and `TRUSTED_PROXY_HOPS=1` on the host; Gmail `+alias` farming and shared-store rate limits are known gaps (ADR-009); no alerting on `TRIAL_CAP_REACHED`/`RATE_LIMITED` logs yet.
- [ ] Test workspace "Verify All Workspace" is on the Pro plan (rollback: planId -> free). Dev DB holds ~20 throwaway QA users/workspaces.
- [ ] Backlog (GitHub): new #15 phone layout, #16 "Try again", #17 re-ask on bad AI output, #19 durable worker, #20 egress restrictions (before prod); #12 extended (record model used). No plan-change path (billing unbuilt).
- [ ] Private items (not in repo): pricing/billing, target customer, 3-5 user interviews, real extraction-quality test on sample invoices.
