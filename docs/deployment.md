# Deployment Guide

## Platform Options

| Platform | Frontend | Backend | Notes |
|---|---|---|---|
| Vercel | ✅ | ❌ | Pair with Render or Railway for backend |
| Render | ✅ | ✅ | Static site + Python web service |
| Railway | ✅ | ✅ | Single project, separate services |
| PythonAnywhere | ❌ | ✅ | Backend only |

## Environment Variables

Set environment variables in your platform's web dashboard (Render, Railway, Vercel, PythonAnywhere):
- For Backend: Use variables defined in `backend/.env.example` (`DATABASE_URL`, `GEMINI_API_KEY`, `SECRET_KEY`, etc.).
- For Frontend: Use variables defined in `frontend/.env.example` (`VITE_API_BASE_URL`).

Optional backend settings worth knowing about (see `backend/app/core/config.py`):
- `GEMINI_FALLBACK_MODEL` — a backup Gemini model used when the primary is overloaded (e.g. one version behind `GEMINI_MODEL`). Unset = disabled. See [ADR-006](adr/006-async-extraction-queue.md).
- `TRIAL_EXTRACTIONS` — free extractions each *new* workspace gets on the platform Gemini key (default `5`; `0` turns the trial off). Costs real money, so keep it small. See [ADR-008](adr/008-free-trial-credits.md).
- `RESEND_API_KEY` / `EMAIL_FROM` — outbound email for verification links ([Resend](https://resend.com)). `EMAIL_FROM` must be on a domain you verified in Resend (SPF/DKIM). With no key set, links are only logged — **set both before launch**, or nobody can verify and nobody gets trial credits. See [ADR-009](adr/009-email-verification-and-signup-limits.md).
- `TRIAL_DAILY_GRANT_CAP`, `SIGNUP_LIMIT_PER_IP_PER_HOUR`, `SIGNUP_LIMIT_PER_DOMAIN_PER_HOUR`, `VERIFICATION_RESEND_LIMIT_PER_HOUR` — signup abuse limits (ADR-009). `TRUSTED_PROXY_HOPS` must equal the number of reverse proxies in front of the app (`1` on Render/Railway); at `0` every user shares the proxy's IP and the per-IP limit would throttle everyone.
- `WEBHOOK_ALLOW_PRIVATE_HOSTS` — defaults to `false`; webhook URLs must be public. Set `true` **only** in local development. See [ADR-007](adr/007-ssrf-protection-for-webhooks.md). In production also restrict outbound network access at the platform level.

The `VITE_` prefix is enforced by Vite at build time — only variables prefixed `VITE_` are inlined into the browser bundle. No `.env` files are required on production servers.

## Render

1. Create a **Web Service** (Python) → connect repo → set root to `backend/`
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Create a **Static Site** → connect repo → set root to `frontend/`
5. Build command: `npm install && npm run build`
6. Publish directory: `dist`

## Railway

1. Create a new project → add two services from the same repo
2. Service 1: Backend — set root to `backend/`, start command as above
3. Service 2: Frontend — set root to `frontend/`, build + start via `npm`

## Vercel / Netlify (frontend static site)

1. Import repo → point root to `frontend/`
2. Build command: `npm run build` → publish dir: `dist`
3. Set all `VITE_*` vars in the platform dashboard
4. Backend must be deployed separately (Render / Railway)

## Future: Public Website

When a public landing page / blog is needed, it will live in a separate `website/` package (Next.js or Astro) and be deployed independently. This does not affect the `frontend/` dashboard deployment.
