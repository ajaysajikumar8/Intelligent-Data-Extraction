# ADR 011 — Retrying failed extractions in place

- **Status:** Accepted (2026-10-24) — resolves issue #16

## Context

A document that failed for a temporary reason (AI busy, rate limit, timeout, server restart) forced the
user to start over. In the dev database about 70% of failures were `INTERRUPTED`/`AI_BUSY`/`TIMEOUT`/`RATE_LIMITED`;
only 1 of 301 documents ended in `BAD_AI_OUTPUT`.

## Decision

1. **`POST /api/v1/logs/{id}/retry`** re-queues a `FAILED` document whose stored failure code is in
   `RETRYABLE_CODES` (`AI_BUSY`, `RATE_LIMITED`, `TIMEOUT`, `INTERRUPTED`, `BAD_AI_OUTPUT`, plus `NO_AI_KEY` and
   `AI_KEY_INVALID`, which the user can fix by adding a key or verifying their email). Anything else returns 409.
2. **Retry in place, not as a copy.** The same `DocumentLog` is reset to `PENDING` (error and progress cleared,
   `createdAt` reset to "queued at") and enqueued again. So there is no second row to count against the monthly
   quota, Logs does not fill with duplicates, and the document id the user and any webhook consumer already hold
   stays valid. A retry that finishes sends a new outbound webhook for the same document id.
   *Alternative considered:* a new log linked to the original (`retryOfId`). It needs a schema change and
   keeps the failed attempt visible, but doubles quota use and rows; the failed attempt has no value beyond its
   error code. Revisit if audit history of attempts becomes a requirement.
3. **Atomic claim.** The reset is a conditional `UPDATE ... WHERE status = 'FAILED'`, so a double-click or two
   tabs queue the job once (the loser gets 409). The per-workspace in-flight cap (ADR 010) and queue backlog
   limit apply as for a new submission. Trial credits are spent again when the job runs (the failed attempt
   had refunded its credit).
4. **Text submissions only.** Uploaded files are not stored, so a document with a `fileName` returns 409 and
   the UI says to upload it again (hint instead of a button). This lifts when uploads are persisted (#19).
5. **Template reuse.** If classification had already matched a template, the retry forces it (skips the
   classify call); otherwise it auto-detects again.
6. **UI.** `RetryAction` renders "Try again" under the failure on the Submit result and in the Logs drawer.
   `useDocumentPolling` takes an `attempt` so polling restarts for the same id.

## Consequences

- `createdAt` moves to the retry time, so a retried document jumps to the top of Logs and counts toward the
  month it was retried in. The original submission time is not kept.
- Batch rows (file uploads) cannot be retried from the batch panel; the user re-uploads those files.
- #17 (re-ask once on unreadable AI output) was not built: measured 1 in 301 documents, and `BAD_AI_OUTPUT` is
  now one click to retry.
