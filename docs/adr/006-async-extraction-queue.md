# ADR 006 — Asynchronous extraction with an in-process queue

- **Status:** Accepted (2026-10-22)
- **Supersedes:** the synchronous behaviour of `POST /api/v1/ingest` described in ADR 002.

## Context

`POST /ingest` ran the whole 3-stage Gemini pipeline inside the HTTP request. In a live test a single
submission blocked for 30–60 s, and when Gemini returned `503 UNAVAILABLE` ("high demand") the raw
provider error dict was stored in `DocumentLog.validationErrors` and shown to the user.

Problems this caused:

1. **Raw provider errors reached users** (`503 UNAVAILABLE. {'error': {...}}`), which is confusing and can
   leak internals.
2. **No retry** for transient provider errors, so a momentary spike failed the document outright.
3. **Request-bound work.** Long requests hold a worker, hit proxy/load-balancer timeouts, and cannot be
   shed under load. Backend standards require queueing long-running jobs.
4. **Inconsistent paths.** The inbound adapters already ran the pipeline as a fire-and-forget task, but
   did not pass the workspace's BYOAK key or fallback flag, so they could only ever fail with
   "No AI key configured". Terminal states also did not all dispatch outbound webhooks.

## Decision

1. **Failures are classified, not leaked.** `app/services/failures.py` maps any exception to a
   `Failure(code, message)` with a stable code (`AI_BUSY`, `RATE_LIMITED`, `AI_KEY_INVALID`,
   `CONTENT_BLOCKED`, `UNPROCESSABLE`, `TIMEOUT`, `INTERRUPTED`, `NO_AI_KEY`, `INTERNAL`) and a
   user-safe message. It is stored as `validationErrors = {"error": <message>, "code": <code>}`.
   Raw exceptions are logged server-side only.
2. **Transient provider errors are retried** (5xx and transport errors) with exponential backoff and
   jitter, up to 3 attempts, before the document is failed with `AI_BUSY`. Quota (429) is not retried
   against the same key; it keeps the existing BYOAK platform-fallback behaviour.
3. **`POST /ingest` returns `202 Accepted`** with the `DocumentLog` in `PENDING`. The pipeline runs in an
   in-process queue (`app/services/extraction_queue.py`):
   - bounded concurrency (semaphore) and a bounded backlog (HTTP 503 when full, checked *before* a log
     row is created, because queued jobs hold uploaded file bytes in memory);
   - a per-job timeout, so every job reaches a terminal state;
   - graceful shutdown: in-flight jobs get a grace period, the rest are marked `INTERRUPTED`;
   - startup sweep: rows left `PENDING`/`PROCESSING` longer than the job timeout (crash orphans) are
     marked `INTERRUPTED`. The age threshold keeps this safe if more than one instance runs.
4. **One enqueue path.** Dashboard/API ingestion and every inbound adapter call
   `extraction_queue.enqueue(workspace, ...)`, which resolves the BYOAK key and fallback flag in one place.
5. **Every terminal transition dispatches the outbound webhook**, through a single `_finish()` in the pipeline.
6. **The dashboard polls** `GET /logs/{id}` until the document is terminal, and the Logs page refreshes
   while any visible row is still in flight. The Submit page remembers the last submission for the tab
   (`sessionStorage`) and resumes it after a reload or navigating away.
7. **Live progress is stored on the document.** A nullable `DocumentLog.progress` JSON column
   (`{stage, attempt, maxAttempts, retryReason}`) is written at each stage and retry and cleared when the
   document finishes. The UI shows Queued → Reading → Extracting, "The AI service is busy, retrying
   (attempt 2 of 3)", and a running timer. Writing it is best-effort and never fails a job.
8. **Retry policy:** each AI call is cut off after 60 s (a hung call counts as transient); backoff is
   ≈5 s then ≈10 s with jitter; the per-job timeout is 450 s (worst case ≈2 × (3 × 60 s + 15 s)).
9. **Optional backup model.** If `GEMINI_FALLBACK_MODEL` is set, a transient failure on the primary model
   moves the remaining attempts, and later stages of the same job, to the backup model (e.g. one version
   behind) instead of re-trying a model that is already busy. The UI says "Switching to a backup AI model".
   An unusable backup (retired / 404) is dropped and never masks the real "AI is busy" failure. Off by
   default; the setting is opt-in because model names are account-specific. During testing the newest
   models returned 503 while the previous versions answered in about 2.5 s.

## Consequences

- **Breaking API change:** API-key callers of `POST /ingest` no longer receive the extraction result in
  the response. They read it from `GET /logs/{id}` or receive it via outbound webhook. Acceptable
  pre-launch; must be called out in release notes once external users exist.
- **One additive schema change:** `DocumentLog.progress Json?` (applied with `prisma db push`; rollback =
  drop the column).
- **No new infrastructure or dependencies.** Trade-off: the queue is in-process.
  - A hard crash loses in-flight jobs; they are marked `INTERRUPTED` by the startup sweep (after the
    timeout) and the user can resubmit.
  - Uploaded file bytes are not persisted (there is no object storage yet), which is why a durable
    queue was not chosen.
  - Concurrency and backlog limits are per process, not global.
- **Graduation path** when scale or durability requires it: persist uploads to object storage, store a
  job row (or use Redis + a worker such as Arq), and run the same `extraction_pipeline.run` from a
  separate worker process. The `enqueue()` seam is the only call site to change.

## Alternatives considered

- **Only classify errors + retry, keep synchronous.** Fixes the leak but keeps 30–60 s requests, so
  rejected.
- **Celery/Redis or Arq now.** Durable and horizontally scalable, but adds infrastructure and a package
  install, and uploads still need object storage. Premature for the current stage.
- **A `?wait=true` synchronous mode.** Extra surface for a pre-launch API with no external callers.
