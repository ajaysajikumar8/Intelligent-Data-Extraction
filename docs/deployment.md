# Deployment Guide

## Launch checklist

Do these before the first real user. Items marked *(you)* happen in your own accounts; the app enforces the rest at
startup when `APP_ENV=production`.

- [ ] Set `APP_ENV=production`. The app then **refuses to start** on placeholder secrets, no `ENCRYPTION_KEY`, no Resend setup,
      localhost URLs or `WEBHOOK_ALLOW_PRIVATE_HOSTS=true` ([startup checks](#production-startup-checks)).
- [ ] Set every [required production variable](#production-environment-variables) in the platform dashboard *(you)*.
- [ ] Verify a sending domain in Resend (SPF/DKIM), then set `RESEND_API_KEY` and `EMAIL_FROM` *(you)*. Without them nobody can
      verify an email, so nobody gets trial credits.
- [ ] Set `TRUSTED_PROXY_HOPS=1` on Render/Railway (the number of reverse proxies in front of the app).
- [ ] Run the [database steps](#database-first-deploy-and-schema-changes) against the production database *(you)*.
- [ ] Restrict outbound traffic from the API service ([egress restrictions](#egress-restrictions-ssrf-defence-in-depth), issue #20) *(you)*.
- [ ] Set up [monitoring and alerts](#monitoring-and-alerts) *(you)*.
- [ ] Remove any QA overrides from the environment (`SIGNUP_LIMIT_PER_*` above their defaults, `TRIAL_EXTRACTIONS` raised for testing).
- [ ] Run one real end-to-end pass on the deployed app: sign up, receive and click the verification email, run a sample extraction,
      add a webhook and send a ping.

Known limits you are accepting at launch: signup rate limits and the extraction queue are **per process**, so run a single backend
instance (see [ADR-006](adr/006-async-extraction-queue.md), [ADR-009](adr/009-email-verification-and-signup-limits.md));
Gmail `+alias` addresses can farm free trials; a hard crash or deploy loses unsent batch files and in-flight jobs
(in-flight ones are marked `INTERRUPTED` on restart).

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

## Production environment variables

Names only: never put values in this repo. Set them in the platform dashboard.

| Variable | Required | Notes |
|---|---|---|
| `APP_ENV` | yes | `production`. Turns on the startup checks below. |
| `DATABASE_URL` | yes | Use the platform's *private/internal* database URL if it offers one. |
| `SECRET_KEY` | yes | 32+ random characters (`python -c "import secrets; print(secrets.token_urlsafe(48))"`). Changing it logs everyone out. |
| `ENCRYPTION_KEY` | yes | Fernet key that encrypts customers' own Gemini keys. **Back it up**: losing it makes every stored key unreadable; changing it has the same effect. |
| `GEMINI_API_KEY` | yes | The platform key used for trials and the paid fallback. This is your cost. |
| `RESEND_API_KEY`, `EMAIL_FROM` | yes | `EMAIL_FROM` must be on a domain verified in Resend. |
| `FRONTEND_URL`, `API_BASE_URL` | yes | Public `https://` URLs. `FRONTEND_URL` is also the only allowed CORS origin. |
| `TRUSTED_PROXY_HOPS` | yes behind a proxy | `1` on Render/Railway. Never higher than the real number of proxies. |
| `WEBHOOK_ALLOW_PRIVATE_HOSTS` | no | Leave unset (`false`). |
| `TRIAL_EXTRACTIONS`, `TRIAL_DAILY_GRANT_CAP` | no | Your free-trial spend: at most `TRIAL_DAILY_GRANT_CAP` workspaces per day get `TRIAL_EXTRACTIONS` credits each; one credit is one document (about two Gemini calls). |
| `GEMINI_FALLBACK_MODEL` | no | See above. |
| `VITE_API_BASE_URL` | frontend | Set at build time on the frontend service. |

### Production startup checks

With `APP_ENV=production`, `Settings` (`backend/app/core/config.py`, `production_problems`) refuses to start and lists **every** problem when:
`ENCRYPTION_KEY` is missing or not a valid Fernet key; `SECRET_KEY` is a placeholder or under 32 characters; `GEMINI_API_KEY` is the example
placeholder; `WEBHOOK_ALLOW_PRIVATE_HOSTS` is true; `FRONTEND_URL`/`API_BASE_URL` point at localhost or are not `https`; `RESEND_API_KEY`
is unset or `EMAIL_FROM` uses Resend's shared test sender. It only **warns** (in the log) when `TRUSTED_PROXY_HOPS` is `0` or the signup
limits are above their defaults. Messages never contain the values.

If `APP_ENV` is *not* `production` but a hosted-platform variable (`RENDER`, `RAILWAY_ENVIRONMENT`, `FLY_APP_NAME`, `VERCEL`) is present,
the app logs a warning that the checks were skipped. `GET /health` reports the active `environment`.

## Database: first deploy and schema changes

The schema lives in `backend/prisma/schema.prisma`. There is **no migration history** in the repo: the project uses `prisma db push`.

First deploy of a new database (run from `backend/`, with `DATABASE_URL` pointing at it):

1. `prisma db push`: creates the tables.
2. `python -m app.db.seed`: inserts the plan tiers (idempotent upserts). The app refuses to boot until a `free` plan exists.

The build must also generate the Python Prisma client: `pip install -r requirements.txt && prisma generate` (without it the app cannot
import `prisma`'s generated models).

Every later schema change (e.g. ADR-013 added `DocumentLog.apiKeySource` / `modelUsed`) must be applied to production **before** the code
that uses it is deployed. Additive changes (new nullable columns, new tables) are safe with `prisma db push`. Never pass
`--accept-data-loss` against production, and take a database backup/snapshot first.

**Recommendation before the first customer data lands:** switch production to real migrations (`prisma migrate`): a baseline from the current
schema, then reviewed, versioned SQL per change with a rollback plan. `db push` has no history and no rollback, and a destructive change
(dropping or retyping a column) can lose data. Do this while the production database is still empty.

## Egress restrictions: SSRF defence in depth

(Issue #20.) The app already refuses webhook URLs that resolve to private/internal addresses ([ADR-007](adr/007-ssrf-protection-for-webhooks.md)):
public addresses only, the validated IP is pinned, redirects are never followed. That is one layer, in code. The second layer is the
network: the API service should be **unable** to reach internal ranges even if a future bug skips the check.

Block outbound connections from the API service to:

| Range | What it is |
|---|---|
| `169.254.0.0/16` (esp. `169.254.169.254`) | Cloud metadata service (instance credentials) |
| `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` | Private networks (databases, admin tools, other services) |
| `100.64.0.0/10` | Carrier-grade NAT / some platforms' internal networks |
| `127.0.0.0/8`, `::1` | The host itself |
| `fc00::/7`, `fe80::/10` | IPv6 private and link-local |

The service must still reach the database, Gemini (`generativelanguage.googleapis.com`), Resend (`api.resend.com`) and customers'
public webhook URLs. Choose by hosting model:

- **VM/VPC hosting (AWS, GCP, Azure, Fly private networking):** add egress deny rules for the ranges above (security group + NACL on AWS,
  egress firewall rules on GCP). Allow the database by its specific address, *before* the deny rules.
- **PaaS (Render, Railway):** as far as we know these offer no per-service outbound firewall: check their current docs. Options: route the
  service's outbound HTTP through an egress proxy that denies the ranges above (set `HTTPS_PROXY`; Stripe's open-source
  [Smokescreen](https://github.com/stripe/smokescreen) is built for exactly this), or move the API to a platform with egress control. Until
  then, rely on the application layer, and keep the database reachable only with its own credentials (never trust "private network = safe").
- Whichever you choose, give the database its own strong credentials and, where possible, an IP allow-list.

Verify (on staging, not production): deploy with the network rule in place, temporarily set `WEBHOOK_ALLOW_PRIVATE_HOSTS=true`, create a
webhook to an internal address (e.g. the metadata IP or the private database host) and press **Ping**. The app layer is bypassed, so a
*connection failure* proves the network layer works. Then set the variable back to `false`.

## Monitoring and alerts

Point the platform's log drain at any log service (Better Stack, Papertrail, Grafana Loki, Datadog) and create these alerts. They match
the exact log text the backend writes (`backend/app/...`):

| Log text | Meaning | Alert when |
|---|---|---|
| `TRIAL_CAP_REACHED` | The daily free-trial grant cap was hit; new verified users get no credits | any occurrence (your growth or abuse signal) |
| `RATE_LIMITED scope=` | A signup/resend limit blocked someone | spike (e.g. >20 in 10 min) → likely abuse |
| `Unhandled extraction error`, `Extraction exceeded` | Extraction crashed / timed out | >5 in 10 min |
| `Resend rejected email`, `Resend request failed` | Verification emails are failing | any occurrence: signups are broken |
| `Could not refund trial credit` | A failed job kept a user's credit | any occurrence |
| `Invalid ENCRYPTION_KEY` | Customer keys cannot be read or written | any occurrence (page immediately) |
| `Recovered N interrupted extraction(s)` | The process restarted with jobs in flight | any occurrence (a deploy or a crash) |
| `CRITICAL: Database has not been seeded` | Plans missing: the app will not boot | any occurrence |

Also monitor uptime on `GET /health`. It returns HTTP 200 even when the database is disconnected, so match the body: alert unless it
contains `"status":"ok"`.

Useful queries (run on a schedule or by hand against the production database):

```sql
-- Why are extractions failing? (last hour)
SELECT "validationErrors"->>'code' AS code, count(*)
FROM "DocumentLog"
WHERE status = 'FAILED' AND "createdAt" > now() - interval '1 hour'
GROUP BY 1 ORDER BY 2 DESC;

-- Who is paying for extractions? (platform spend = TRIAL_CREDIT + PLATFORM + the platform part of WORKSPACE_THEN_PLATFORM)
SELECT "apiKeySource", count(*)
FROM "DocumentLog"
WHERE "createdAt" > now() - interval '24 hours'
GROUP BY 1 ORDER BY 2 DESC;
```

## Render

1. Create a **Web Service** (Python) → connect repo → set root to `backend/`
2. Build command: `pip install -r requirements.txt && prisma generate`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` (a single instance: see the known limits above)
4. Set the [production variables](#production-environment-variables), and run the [database steps](#database-first-deploy-and-schema-changes) once
5. Create a **Static Site** → connect repo → set root to `frontend/`
6. Build command: `npm install && npm run build`
7. Publish directory: `dist`

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
