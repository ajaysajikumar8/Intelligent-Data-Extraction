# ADR 014 — Versioned database migrations (Prisma Migrate)

- **Status:** Accepted (2026-10-25)
- **Supersedes:** the "`prisma db push`" workflow used since Phase 2.

## Context

The schema was applied with `prisma db push`, which makes the database match `schema.prisma` and leaves no record. That is fine for a
throwaway dev database, but a production database needs: an ordered history of structural changes, the same changes applied identically
everywhere, a way to review the SQL before it runs, and no silent data loss. `db push` can drop or retype columns when the schema changes
destructively, and cannot be audited or replayed.

## Decision

1. **Prisma Migrate.** Every schema change is a committed SQL migration in `backend/prisma/migrations/`, created with
   `prisma migrate dev --name ...` and reviewed before commit. `migration_lock.toml` pins the provider (PostgreSQL).
2. **Baseline `0_init`** is the full schema as of 2026-10-25 (including `ApiKeySource` / `modelUsed` from ADR-013). It was generated with
   `prisma migrate diff --from-empty --to-schema-datamodel`. It was verified two ways before being adopted: the dev database showed no
   difference from `schema.prisma`, and applying `0_init` to an **empty scratch database** produced a schema with no difference from
   `schema.prisma`. The dev database then had it recorded with `prisma migrate resolve --applied 0_init` (creates only the
   `_prisma_migrations` bookkeeping table; no tables or data touched).
3. **Deploys run `prisma migrate deploy`** (pending migrations only, non-interactive, never resets) before the new code starts, followed
   by the idempotent seed. `db push` and `migrate reset` are not used outside a disposable local database.
4. **Rollback is forward-only.** Prisma has no down migrations: fix with a new migration, snapshot before deploying, and use
   expand-then-contract for risky changes.

## Consequences

- Schema changes now need an extra reviewed file in every PR that touches `schema.prisma`; forgetting it makes `migrate deploy` a no-op
  while the code expects new columns. CI should eventually fail a PR when `prisma migrate diff` against the migrations shows a difference.
- Local development needs a shadow database (`migrate dev` creates and drops one), so the local Postgres role needs `CREATEDB`.
- Automated tests still run against the dev database as before; they do not apply migrations.
- The hand-written `0_init` is never edited after it is applied anywhere. Later changes are new migrations.
