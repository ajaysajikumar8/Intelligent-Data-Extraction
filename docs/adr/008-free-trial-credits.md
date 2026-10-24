# ADR-008: Free-Trial Credits for New Workspaces

**Status:** Accepted
**Date:** 2026-10-23
**Amended:** credits are now granted on email verification, not at signup — see [ADR-009](009-email-verification-and-signup-limits.md).

## Context

ADR-005 made BYOAK mandatory unless a paid workspace opts into Platform Key Fallback. A brand-new free workspace therefore cannot complete a single extraction until it has created a Gemini key, which loses most users before they see the product work (issue #14, blocking the first-run checklist #2).

## Decision

Each **new** workspace gets a small number of free extractions on the platform key, then must add its own key.

1. **Balance on the workspace.** `Workspace.trialExtractionsRemaining Int @default(0)`. Existing workspaces keep 0, so nobody's spend changes silently (same principle as ADR-005). Signup grants `TRIAL_EXTRACTIONS` (default 5, `0` = trial off).
2. **One routing policy.** `app/services/ai_access.py` decides the key per job: own key → platform fallback (paid opt-in) → trial credit → `NO_AI_KEY`. A workspace with its own key never touches credits. The pipeline is unchanged; a trial job simply resolves to "platform key allowed".
3. **Atomic spend.** A single conditional `UPDATE ... WHERE trialExtractionsRemaining > 0` decrement; concurrent jobs, or several instances, cannot overspend. Resolved inside the queue worker (`extraction_queue._run`), so every ingestion path (dashboard, API key, inbound adapters) behaves identically and no API contract changes.
4. **Refund on failure.** A job that ends `FAILED` (including timeout/interrupt/unhandled error) gives its credit back: a trial user must not pay for our outage. `SUCCESS`, `NEEDS_REVIEW` and `UNMATCHED` keep the spend (the AI was called).
5. **UI.** The workspace response exposes `trialExtractionsRemaining`. The Dashboard shows a first-run checklist whose progress is *derived* from data (template exists, extraction exists, key set), not stored; it hides itself when complete and moves the key step first once the trial is used up. "Run a sample extraction" opens `/submit?sample=1` with a pre-filled invoice. Settings shows the balance.

## Consequences

- **Cost / abuse:** every signup can spend `TRIAL_EXTRACTIONS` of platform budget. There is no email verification or signup rate limiting yet, so credits can be farmed with throwaway emails. Mitigations today: small default, `TRIAL_EXTRACTIONS=0` kill switch. **Before public launch** add email verification and signup rate limiting (and consider the per-IP cap).
- A workspace that spends its trial then adds a key keeps any unspent credits but never uses them; deleting the key later makes them usable again. Acceptable.
- Credits are per workspace in Postgres, so they hold under multiple backend instances. The in-process queue limits from ADR-006 are unchanged.
- Rollback: set `TRIAL_EXTRACTIONS=0` (stops new grants); to also stop existing balances, `UPDATE "Workspace" SET "trialExtractionsRemaining" = 0`. The column is additive and can be dropped.
