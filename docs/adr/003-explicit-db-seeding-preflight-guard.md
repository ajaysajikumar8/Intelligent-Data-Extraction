# ADR 003: Explicit Database Pre-Seeding & Startup Verification Guard

## Context

The system relies on initial reference data, specifically `Plan` billing tiers (`free`, `pro`, `enterprise`), to create workspaces during user signup. Originally, an on-the-fly fallback was considered to automatically create a default `free` plan if missing during user registration.

However, automatic on-the-fly seeding creates runtime ambiguity, hides deployment misconfigurations, and couples signup endpoints to initial database bootstrap logic.

## Decision

We require **explicit pre-seeding** of database reference tables before any application instance serves traffic:

1. **CLI Seeding Script**: A dedicated async python CLI script (`backend/app/db/seed.py`, run via `python -m app.db.seed`) upserts required `Plan` records (`free`, `pro`, `enterprise`).
2. **Startup Pre-Flight Verification Guard**: FastAPI's `lifespan` context manager performs an explicit database check on startup (`await db.plan.find_first(where={"slug": "free"})`). If missing, it logs a `CRITICAL` error and raises a `RuntimeError` to immediately halt application startup.
3. **Signup Enforcement**: `POST /api/v1/auth/signup` queries the pre-seeded `free` plan. If missing, it fails fast with HTTP 500 alerting the operator.

## Consequences

- **Pros**:
  - Predictable deployment lifecycle: Database seeding is part of standard deployment pipelines.
  - Fail-Fast Safety: Prevents backend services from running in an partially-initialized state.
  - Decoupled Codebase: Registration endpoints assume clean database state rather than mutating infrastructure configuration.
- **Cons**:
  - Deployment pipelines must include `python -m app.db.seed` step prior to server launch.
