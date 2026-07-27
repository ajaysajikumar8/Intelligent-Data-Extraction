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
- For Frontend: Use variables defined in `frontend/.env.example` (`NEXT_PUBLIC_API_BASE_URL`).

The `NEXT_PUBLIC_` boundary is enforced by Next.js at build time regardless of platform. No `.env` files are required on production servers.

## Render

1. Create a **Web Service** (Python) → connect repo → set root to `backend/`
2. Build command: `pip install -r requirements.txt`
3. Start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
4. Create a **Static Site** → connect repo → set root to `frontend/`
5. Build command: `npm install && npm run build`
6. Publish directory: `out` (or `.next` for SSR)

## Railway

1. Create a new project → add two services from the same repo
2. Service 1: Backend — set root to `backend/`, start command as above
3. Service 2: Frontend — set root to `frontend/`, build + start via `npm`

## Vercel (frontend only)

1. Import repo → Vercel auto-detects Next.js
2. Set all `NEXT_PUBLIC_*` vars in Vercel dashboard
3. Backend must be deployed separately (Render / Railway)
