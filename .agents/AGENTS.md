# Intelligent Data Extraction — Agent Context

> **Start of every session:** Read `MEMORY.md`. Update it after every task.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python / FastAPI |
| Frontend (dashboard) | Vite + React (TypeScript) |
| Frontend (public site, future) | Next.js or Astro — separate app, separate deploy |
| Database | PostgreSQL + Prisma ORM |
| AI | Google Gemini API |
| Auth | JWT + optional Google OAuth |

## Docs Map

| File | Purpose |
|---|---|
| `MEMORY.md` | Working log — current state, decisions, to-do. Read this first. |
| `docs/architecture.md` | System design, data flow, repo structure |
| `docs/deployment.md` | Render / Railway / Vercel setup |
| `docs/adr/` | Architecture Decision Records — the *why* behind every major choice |

## Env Var Rules

- Maintain independent `.env` files per service for local dev (`backend/.env` and `frontend/.env.local`).
- In production, set variables via the cloud platform dashboard (Render, Railway, Vercel).
- `VITE_*` = browser-safe (Vite inlines these at build time). Everything else = server-only.
- Never reference a non-`VITE_` var in frontend `.ts`/`.tsx` files.

## Standards

- Python: PEP 8, type hints, async FastAPI patterns.
- TypeScript: strict mode, no `any`.
- Git: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`).
- Never hardcode secrets.
- Database: schema changes are Prisma migrations (`prisma migrate dev --name x`, commit the SQL, see `docs/adr/014-prisma-migrations.md`). Never `prisma db push` / `migrate reset` outside a disposable local DB.

## Public Repo Rules

This is a public GitHub repository. Treat all committed files as public:
- `MEMORY.md`, `docs/`, and all markdown files are visible to everyone.
- Never write API keys, passwords, usernames, server IPs, or internal URLs into any of these files.
- Secrets belong only in `.env` — which is gitignored and never committed.

## Behaviour

1. Read `MEMORY.md` first.
2. Update `MEMORY.md` after every meaningful task.
3. When making an architectural decision, add a new `docs/adr/NNN-title.md`.
4. Ask before deleting existing code — there may be reasoning behind it.
5. Prefer editing existing files over creating new ones.

## MEMORY.md Housekeeping (Token Budget Discipline)

`MEMORY.md` is a **working buffer**, not an archive. It is read in full at the start of every session/task — its size is a *recurring, permanent* token cost, not a one-time cost. Keep it short and current.

**Hard rule — check this at the start of every task, not just when it feels bloated:**
- If `MEMORY.md` exceeds **~150 lines or ~5KB**, archive/collapse old entries *before* doing anything else that task.
- If a completed phase/decision hasn't been touched in **2+ dated entries' worth of time**, it's stale — collapse it.

**Archive a decision entry when:**
- The decision is stable and no longer being actively iterated on, AND
- It has enough context/reasoning to stand alone as a record (full detail is never lost — it's always still in git commit history via `git log -p -- MEMORY.md`).

**How to archive:**
1. For architecturally significant decisions: create `docs/adr/NNN-short-title.md` with the decision details (context, decision, consequences), then replace the full entry in `MEMORY.md` with a one-liner: `[date] — Topic → see docs/adr/NNN-short-title.md`
2. For routine completed-phase/to-do entries with no lasting architectural reasoning: just collapse multiple verbose bullet points into a single condensed summary line/checklist item — no ADR needed. Rely on git history for the rest.

**Keep in `MEMORY.md` always:**
- The To-Do list (Done + Pending) — collapse fully-done phases into one line each
- Decisions still being worked out
- Anything the agent needs to act on right now

**General token-optimization reminders (applies to all work in this repo, not just MEMORY.md):**
- Prefer targeted `start_line`/`end_line` reads over whole-file reads for large files (schema.prisma, service files, etc.).
- Don't re-read files already read earlier in the same session unless they may have changed.
- Keep explanations concise; avoid repeating file contents back verbatim when a summary suffices.
