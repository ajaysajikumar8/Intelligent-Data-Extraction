# Project Memory — Intelligent Data Extraction

> Working log: current state, decisions, to-do. Read first, update after every task. Detail lives in `docs/adr/` and `git log -p -- MEMORY.md`.
> Public repo: never put keys, passwords, usernames, IPs or internal URLs here.

## Done (one line each → where the detail is)
- Phases 0–6 (scaffold, schema, auth, 3-stage Gemini pipeline, React dashboard, webhooks, inbound adapters) → ADR 001–004.
- BYOAK + platform fallback → 005. Async queue + backup model → 006. SSRF protection → 007. Free-trial credits → 008. Email verification + signup limits → 009.
- Batch upload (2–20 files, one `/ingest` each, 3 in flight; server cap 25 per workspace; limited to trial credits; survives in-app navigation, "Leave site?" prompt while files are unsent) → 010.
- "Try again" for failed text extractions (retry in place) → 011. Review screen for NEEDS_REVIEW (`ReviewForm`, `/correct` atomic) → 012.
- `DocumentLog.apiKeySource` + `modelUsed` → 013. Prisma migrations (baseline `0_init`) → 014. Activity log, owner-only `GET /activity` + page → 015.
- Production startup checks: `APP_ENV=production` refuses unsafe settings; launch checklist, DB steps, egress, alerts in `docs/deployment.md`.
- Mobile nav drawer, app name via `lib/brand.ts` (placeholder, real brand name undecided), inactive templates stay listed.
- Fixed: API-key-only ingestion returned 401 (`get_optional_user`).
- Dropped on purpose: Logs "finished" badge (#18, not planned); #17 re-ask AI (rare); #23 exports parked (CSV already opens in Excel).

## Open issues
#13 upgrade flow (blocked on billing) · #17 re-ask AI · #19 durable worker · #20 egress rules (needs a host) · #23 Excel/Tally export · #25 CI check schema vs migrations.

## Extraction-quality test (2026-10-25, live Gemini, 14 generated documents)
14/14 routed correctly (non-documents → UNMATCHED), every field right, median 11 s/doc. Synthetic documents are easier than real scans: upper bound.
Findings still to act on:
1. The platform Gemini key is on a free tier (5 req/min, 20 req/day per model): needs a paid tier before launch. 429s are not retried although Google returns a 2–30 s `retryDelay`. `GEMINI_FALLBACK_MODEL` is unset and the configured primary model was overloaded while others worked.
2. Dates are stored exactly as printed (`05/04/2026` is ambiguous): normalise to ISO.
3. A credit note returns positive amounts and has no document-type field.
4. Every field came back "High" confidence, so NEEDS_REVIEW never triggered: confidence is unproven; test messy/ambiguous documents.
Test documents and scorer are not in the repo (could be added as a repeatable eval).

## Before launch / known gaps
- Needs a host + accounts: Resend domain and keys, production variables incl. `APP_ENV=production` and `TRUSTED_PROXY_HOPS=1`, `prisma migrate deploy && python -m app.db.seed` (prod needs the ActivityLog and key-source migrations), egress rules (#20), alerts.
- Local only: `backend/.env` has relaxed signup limits (50/hour): remove before deploying. Dev DB holds many throwaway QA users and fake logs, plus a test workspace on the Pro plan (rollback: planId → free). Dev ports: backend 8005, frontend 5178.
- Accepted gaps: Gmail `+alias` trial farming; rate limits and queue are per process (run one instance); unsent batch files and file retries need persisted uploads (#19); extraction concurrency (4) is global, so one workspace's batch can delay others (#19); no member/plan endpoints (nothing to audit yet); activity purge runs only at startup.
- Not decided (not code): pricing/billing, target customer, 3–5 user interviews.
