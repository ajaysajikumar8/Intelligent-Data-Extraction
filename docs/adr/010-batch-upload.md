# ADR 010 — Batch upload (client-driven, one document per file)

- **Status:** Accepted (2026-10-24) — resolves issue #10

## Context

Users with many documents (e.g. a folder of invoices) had to submit one file at a time. Extraction runs
through the in-process queue (ADR 006), which holds uploaded bytes in memory and has a global backlog cap.

## Decision

1. **Each file is its own document.** The dashboard submits every file to the existing `POST /ingest`
   (one `DocumentLog`, one trial credit, one webhook per file). No new backend endpoint: per-file
   validation, quota, key routing and failure handling are reused unchanged, and one bad file cannot
   fail the others.
2. **The browser throttles itself.** `useBatchSubmit` keeps at most 3 documents in flight: submit a file,
   poll it to a final status, then take the next. Max 20 files per batch, validated client-side
   (type, 20 MB) and again by the server.
3. **Server safety net.** `EXTRACTION_MAX_IN_FLIGHT_PER_WORKSPACE` (default 25, `0` disables) rejects new
   ingests with `429` + `Retry-After` when a workspace already has that many `PENDING`/`PROCESSING`
   documents, so one tenant cannot fill the shared backlog. Rows older than the job timeout (crash
   orphans) are ignored. It applies to `POST /ingest`; inbound adapters are not capped yet.
4. **Capacity errors stop the batch.** A `429`/`503` marks every not-yet-submitted file "Not submitted"
   with the reason (monthly quota, workspace cap, queue full) instead of hammering the server.
5. **Trial-credit pre-check.** A workspace with no own key and no platform fallback can only run as many
   documents as it has trial credits (`trialLimit` in `lib/batch.ts`). The Submit page warns, runs only the
   first N files, and leaves the rest selected; at 0 credits the batch button is disabled. Credits are
   re-read after each result because a failed document refunds its credit. The server remains the authority
   (each job still spends a credit atomically), so a stale count can never overspend.
6. Text input is not used in batch mode; one file keeps the existing single/hybrid flow.

## Consequences

- Not-yet-submitted files exist only in the open tab: closing it loses them (already-submitted
  documents keep running and appear in Logs). The panel says so while submitting.
- No server-side batch object: no batch id, no per-batch webhook/summary, no resume after reload.
  Add one if users need "batch complete" notifications (see #18) or API-side bulk submit.
- The per-workspace cap is per process (like the queue). A durable shared queue (#19) would make it global.
- Rate-limit headroom: default cap 25 > batch size 20 + a few single submissions.
