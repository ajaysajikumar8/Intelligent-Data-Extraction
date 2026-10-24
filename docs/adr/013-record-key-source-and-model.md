# ADR 013 — Record whose AI key and which model ran each extraction

- **Status:** Accepted (2026-10-25) — resolves issue #12

## Context

A document could be paid for by the workspace's own Gemini key, by the platform key (paid-plan fallback or a
free-trial credit), or start on the workspace key and finish on the platform key when that key hit its quota.
The backup model can also answer instead of the primary. None of this was recorded per document, and it cannot
be reconstructed later. It decides who costs the platform money, which matters for pricing the trial and the
fallback feature, for support ("whose limit was hit?"), and for BYOAK customers who want to know their key was
(or was not) the one used.

## Decision

1. `DocumentLog.apiKeySource` (enum `ApiKeySource`: `WORKSPACE`, `PLATFORM`, `TRIAL_CREDIT`,
   `WORKSPACE_THEN_PLATFORM`) and `DocumentLog.modelUsed` (the model of the last successful AI call).
   Both nullable. `ai_access.AiAccess.key_source` derives the initial value; the pipeline flips it to
   `WORKSPACE_THEN_PLATFORM` if the workspace key's quota forces a switch mid-run.
2. Written once, when the job reaches a terminal state after the AI was involved (success, review, validation
   failure, unmatched after classification, or an AI error). Jobs that never reached the AI (no key, no
   active template, timeout/restart handled by the queue) record nothing. A retry (ADR-011) clears both fields.
3. Existing rows stay `NULL` ("unknown"); no backfill, because any value would be a guess.
4. Exposed on the log API and shown in the Logs drawer ("AI key used", "AI model").

## Consequences

- Platform spend can be attributed per document: `TRIAL_CREDIT` + `PLATFORM` + the platform part of
  `WORKSPACE_THEN_PLATFORM` are the platform's cost; `WORKSPACE` is not.
- `modelUsed` is the *last* successful call (the extraction stage), not a per-stage history.
- Timeouts and restart recoveries are written by the queue, which does not know the key source, so those
  documents have `NULL` even though a key was resolved. Acceptable: no tokens are reliably billable there.
- Schema change was additive (one enum, two nullable columns): `prisma db push` on dev; production needs the same.
