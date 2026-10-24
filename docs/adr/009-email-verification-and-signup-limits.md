# ADR-009: Email Verification and Signup Abuse Limits

**Status:** Accepted
**Date:** 2026-10-24
**Closes:** #21 (follow-up to ADR-008)

## Context

ADR-008 gives every new workspace `TRIAL_EXTRACTIONS` free extractions on the platform Gemini key. With nothing between "type an email" and "spend platform money", throwaway signups could farm that budget.

## Decision

1. **Credits are granted on verification, not signup.** Signup creates the workspace with 0 credits and emails a link. `POST /auth/verify-email` marks the user verified and grants `TRIAL_EXTRACTIONS` once. Unverified users can log in and set up templates/keys, but cannot spend platform budget.
2. **Stateless signed token** (JWT with a `purpose=verify_email` claim, the user's email, `VERIFICATION_TOKEN_EXPIRE_HOURS` expiry). No token table. `get_current_user` rejects any token carrying a `purpose`, so the link can never act as a session. Changing the email invalidates old links.
3. **Exactly-once grant.** New nullable columns `User.emailVerifiedAt` and `Workspace.trialGrantedAt`. Verification and grant run in one transaction, each guarded by a conditional update (`... WHERE emailVerifiedAt IS NULL`, `... WHERE trialGrantedAt IS NULL`), so re-clicking or racing requests cannot double-grant. The verify endpoint is idempotent and unauthenticated (the link often opens in another browser).
4. **Daily grant cap** (`TRIAL_DAILY_GRANT_CAP`, counted from `trialGrantedAt`). Over the cap the user is still verified but gets no credits and a `TRIAL_CAP_REACHED` warning is logged. It is a soft cap (concurrent verifications can overshoot slightly).
5. **Signup guards** (`core/signup_guard.py`): a disposable-domain blocklist, and in-process sliding-window limits per client IP and per email domain. Mainstream providers (gmail.com etc.) are exempt from the domain limit. `POST /auth/resend-verification` is limited per user and per IP. Client IP honours `X-Forwarded-For` only for `TRUSTED_PROXY_HOPS` entries from the right (the left side is client-forged).
6. **Email via Resend** (`core/email.py`, one `httpx` call, never raises). No `RESEND_API_KEY` = log the message instead (local dev/tests). Sent from a background task so a slow provider never delays signup.
7. **Plain-language validation errors.** A `RequestValidationError` handler keeps FastAPI's `detail` list shape (`loc`, `msg`, `type`) but rewrites messages; the dashboard shows them under the right field. Special-use domains (`.test`, `.invalid`) stay rejected — they cannot receive mail, so they could never be verified (#7).

## Consequences

- **Rate limits and the disposable list are per process / static.** With N instances the effective limit is N×; new throwaway domains appear daily. Move the limiter to Postgres or Redis before scaling out, and treat the blocklist as a first filter only. Verification plus the daily cap are the real controls.
- **Gmail aliasing is not handled:** `a+1@gmail.com`, `a+2@gmail.com` verify into one inbox and each earns credits. Needs a canonical-email column (strip `+tag`/dots for Gmail) if it shows up in practice.
- **Monitoring is log-based:** `RATE_LIMITED`, `SIGNUP_BLOCKED`, `TRIAL_CAP_REACHED` warnings. Wiring them to alerts is still open.
- **Launch dependency:** without `RESEND_API_KEY` + a verified sending domain, nobody receives a link and no trial credits are ever granted.
- Existing users are backfilled as verified (`emailVerifiedAt = createdAt`) so nobody is locked out; they keep the balance they already had.
- Rollback: set `TRIAL_EXTRACTIONS=0` to stop grants. Both columns are additive and nullable and can be dropped.
