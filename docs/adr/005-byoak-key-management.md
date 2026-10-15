# ADR-005: BYOAK (Bring Your Own API Key) — Encryption, Validation, and Platform Fallback

**Status:** Accepted (core implemented; see Consequences for open items)
**Date:** 2026-10-15

## Context

Every extraction previously ran on the platform's own `GEMINI_API_KEY`, with no way for a workspace to use its own Gemini key or to control whether the platform key could be used on its behalf. Full design options are in [`implementation_plan_byoak.md`](../../implementation_plan_byoak.md).

Two implementation questions needed deciding:
1. Should the stored Gemini key be encrypted at rest?
2. Should the key be validated against the live Gemini API when a user saves it?

A third question — what should happen to a workspace that has neither a custom key nor platform-fallback enabled — surfaced as a consequence of the design, not a pre-existing open question.

## Decision

1. **Encrypt at rest** — Fernet (`cryptography`), key from the `ENCRYPTION_KEY` env var. If unset, falls back to plaintext with a logged warning (local-dev-only escape hatch). See [`encryption.py`](../../backend/app/core/encryption.py).
2. **Validate on save** — `PUT /api/v1/workspaces/current/gemini-key` makes a live `count_tokens` call before encrypting and storing the key; returns `422` on an invalid key instead of letting it fail silently at extraction time.
3. **Platform Key Fallback is an explicit, paid-plan-gated kill switch** — `Workspace.allowPlatformFallback` defaults to `false`. A workspace with no custom key and fallback off is blocked from extracting at all (`PUT /api/v1/workspaces/current/platform-fallback` requires `plan.priceUsdCents > 0` to enable it). This means the platform never spends its own Gemini budget without a workspace explicitly opting in, including workspaces that existed before this feature shipped.
4. **Gemini SDK migration** — switched from `google-generativeai` (process-wide singleton client, incompatible with per-workspace keys) to `google-genai`, which supports independent `Client` instances. `gemini_service.py` now keeps a cache keyed by API key string instead of an `lru_cache(maxsize=1)` singleton.

## Reasoning

Encrypting at rest and validating on save were both explicitly requested over their cheaper alternatives (plaintext storage; no validation) for better security posture and UX — a typo'd key should fail immediately with a clear message, not three steps later during a real extraction.

The fallback gate was the harder call: the alternative (quietly keep using the platform key for anyone who hasn't configured anything) would have undermined the entire point of the kill switch — never spending platform budget without consent — including for every pre-existing workspace. That was rejected in favor of building the real toggle (`PUT .../platform-fallback` + the Settings UI switch) rather than a temporary bypass.

## Consequences

### Positive
- No workspace's platform-budget usage happens without an explicit, paid-plan-gated opt-in.
- A bad key is caught at save time, not at extraction time.
- Per-workspace Gemini clients are now architecturally possible (fixed the old singleton assumption).

### Negative / Follow-up required
- **Every existing workspace loses extraction access** until it sets a custom key or (on a paid plan) enables fallback. This is a real behavior change for any workspace already in production, not just new signups.
- `DocumentLog.api_key_source` (recording whether a run used the workspace key, platform key, or a mid-run fallback) is described in the plan doc but not yet implemented — would need a new schema field.
- No "Upgrade" flow exists yet for the free-plan block on the fallback toggle (currently just a toast).
- The `website/` marketing site is unrelated to this ADR but currently has no real `/signup` page to send upgrade traffic to.

### Bugs found and fixed while wiring this up
The pipeline-side BYOAK code existed in draft form before this ADR's implementation pass but had never been exercised end-to-end. Fixing the plumbing (`ingest.py` not passing the key/flag through) surfaced three independent, pre-existing bugs that also blocked extraction:
- `_call_with_fallback` was referenced but never defined.
- `_classify`/`_extract` didn't accept an `api_key` parameter at all, so it could never reach Gemini even when passed correctly.
- `confidenceScores` was written as a bare Python `None` instead of `Json(None)`, which Prisma's Python client rejects for a nullable Json column.
- Unrelated to BYOAK, but discovered in the same pass: `GEMINI_MODEL` had regressed to a since-removed model name (`gemini-2.0-flash`); corrected to `gemini-3.8-flash`.

All fixed; full backend suite (31 tests, including a new test locking in the fallback gate) passes, and the pipeline was verified end-to-end against the live Gemini API.
