# ADR 015 — Activity log (who changed what)

- **Status:** Accepted (2026-10-25) — resolves issue #24

## Context

The Logs page records *extractions*. Nothing recorded *changes*: who edited a template, replaced the Gemini key, rotated the API key,
changed a webhook. Business customers handling financial documents will ask "who changed this?", and it is the first question after a
security incident. History that is not recorded now cannot be rebuilt later.

## Decision

1. **One append-only table, `ActivityLog`**: workspace, actor (user id + a label snapshot: email, "API key" or "System"), a dotted `action`
   string (`template.updated`), optional target type/id, a short `summary`, optional IP, time. `action` is a string, not an enum, so a new
   action never needs a migration; `services/activity.ACTION_CATEGORIES` maps actions to the filter categories on the page.
2. **What is recorded** (only events that exist today): sign-up, email verified, sign-in, failed sign-in; API key / inbound secret rotated;
   Gemini key added, replaced or removed; platform fallback on/off; workspace renamed; webhook created / changed / enabled / disabled /
   deleted / auto-disabled (actor "System"); template created / changed / activated / deactivated / deleted; document approved, corrected
   or retried (`ExtractionCorrection.correctedByUserId` now stores the reviewer). Member and plan changes have no endpoints yet.
3. **Never recorded:** secret values, document contents, or full webhook URLs (they commonly embed tokens, so only the host is stored).
   Summaries are capped at 300 characters and written by the calling endpoint, not derived from request bodies.
4. **IP address** is stored only for sign-in and key events (`auth.`, `api_key.`, `gemini_key.`, `inbound_secret.`), using the same
   trusted-proxy logic as the signup limits (`TRUSTED_PROXY_HOPS`). Routine configuration changes keep no IP.
5. **Failed sign-ins** are recorded only when the email belongs to an account (that is the only way to attribute them to a workspace),
   capped at 20 per workspace per hour so a guessing run cannot flood the table.
6. **Fail-safe:** `record()` never raises; a failure to write is logged and the action it describes still succeeds. No-op updates (nothing
   changed) record nothing.
7. **Read access:** `GET /api/v1/activity` is for workspace OWNERs only (it contains IPs and security events). It rejects API-key-only
   requests. The dashboard shows an "Activity" page (owner-only nav item): newest first, category filter, pagination.
8. **Retention:** `ACTIVITY_RETENTION_DAYS` (default 365, `0` = forever); expired rows are deleted at application startup.
9. **No foreign key** from `ActivityLog.workspaceId`: audit rows must not block, or vanish with, changes to the workspace row. A future
   workspace-deletion feature must purge them explicitly.

## Consequences

- If the migration has not been applied, the app fails at startup (the retention purge touches the table) instead of silently not auditing.
- Under concurrent edits the "from" value in a summary is read before the update, so two simultaneous renames can both claim the same
  previous name. The set of entries is still complete.
- The retention purge only runs at startup; with long-lived processes it runs when they next restart. A scheduled job can replace it later.
- Entries are a snapshot: renaming a user's email later does not rewrite old entries (intentional for an audit trail).
- No export yet; add one if customers ask. Members, invitations and plan changes should call `activity.record` when those features exist.
