# Intelligent Data Extraction — Agent Context

> **Start of every session:** Read `MEMORY.md`. Update it after every task.

## Stack

| Layer | Tech |
|---|---|
| Backend | Python / FastAPI |
| Frontend | Next.js (TypeScript) |
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

- Root `.env` is the single source of truth for both frontend and backend.
- `frontend/.env.local` is a symlink to `../.env` — never edit it directly.
- `NEXT_PUBLIC_*` = browser-safe. Everything else = server-only.
- Never reference a non-`NEXT_PUBLIC_` var in frontend `.ts`/`.tsx` files.

## Standards

- Python: PEP 8, type hints, async FastAPI patterns.
- TypeScript: strict mode, no `any`.
- Git: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`).
- Never hardcode secrets.

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

## MEMORY.md Housekeeping

`MEMORY.md` is a **working buffer**, not an archive. Keep it short and current.

**Archive a decision entry when:**
- The decision is stable and no longer being actively iterated on, AND
- It has enough context/reasoning to stand alone as a record.

**How to archive:**
1. Create `docs/adr/NNN-short-title.md` with the decision details (context, decision, consequences).
2. Replace the full entry in `MEMORY.md` with a one-liner: `[date] — Topic → see docs/adr/NNN-short-title.md`

**Keep in `MEMORY.md` always:**
- The To-Do list (Done + Pending)
- Decisions still being worked out
- Anything the agent needs to act on right now
