# ADR-001: Single Root `.env` Strategy

**Status:** Accepted  
**Date:** 2026-07-24

## Context

Both FastAPI (backend) and Next.js (frontend) need environment variables. Keeping separate files per service means duplicating values and makes platform deployment (Render, Railway, Vercel) harder to manage.

## Decision

Use a single root `.env` as the source of truth for both services.

Security boundary is maintained by Next.js's `NEXT_PUBLIC_` prefix convention, which is enforced at **compile time** — variables without the prefix are never bundled into client JS, even if they exist in the same file.

For local dev, `frontend/.env.local` is a symlink to `../.env` so Next.js picks it up automatically.

## Consequences

- All vars in one place → easy to manage on deployment platforms
- Must never prefix a secret with `NEXT_PUBLIC_`
- Must never reference a non-`NEXT_PUBLIC_` var in frontend `.ts`/`.tsx` files
- `frontend/.env.local` symlink must be recreated after a fresh clone (`cd frontend && ln -s ../.env .env.local`)
