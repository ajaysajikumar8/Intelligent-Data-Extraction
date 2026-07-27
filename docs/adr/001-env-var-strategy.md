# ADR-001: Independent Service `.env` Files Strategy

**Status:** Accepted  
**Date:** 2026-07-24 (Updated 2026-07-25)

## Context

Both FastAPI (`backend/`) and Next.js (`frontend/`) need environment variables during local development. Cloud deployment platforms (Render, Railway, Vercel, PythonAnywhere) do not require physical `.env` files and instead inject variables directly into process environments via dashboard settings.

Using a single root `.env` file with symlinks (`frontend/.env.local -> ../.env`) introduced OS/git cross-platform friction.

## Decision

Maintain separate, independent environment configuration files for each service during local development:
- `backend/.env` (from `backend/.env.example`): Server-side secrets (Database, Gemini API key, JWT, OAuth).
- `frontend/.env.local` (from `frontend/.env.example`): Browser-accessible variables (`NEXT_PUBLIC_*`).

No symlinks are used.

In production deployments (Render, Railway, Vercel), variables are configured independently in each service's platform dashboard.

## Consequences

- No symlink dependency or cross-platform setup required after cloning the repo.
- Clean separation of concerns between backend secrets and frontend public configs.
- For local dev, maintain `backend/.env` and `frontend/.env.local` independently.
- `NEXT_PUBLIC_*` prefix convention remains strictly enforced by Next.js for client-side variables.
