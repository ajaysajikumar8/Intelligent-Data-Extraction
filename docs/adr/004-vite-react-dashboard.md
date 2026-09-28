# ADR-004: Vite + React for Dashboard Portal (Not Next.js)

**Status:** Accepted  
**Date:** 2026-08-23

## Context

The original tech stack listed Next.js (TypeScript) as the frontend framework. Before beginning Phase 5, the choice was re-evaluated against the actual requirements of this application.

The dashboard is a **private, authenticated portal** — every screen requires a valid JWT. There are no public-facing pages, no SEO requirements, and no need to serve content to anonymous users or crawlers.

A future public website (landing page, pricing, blog, docs) has been identified as a likely future need, but it is a **separate product** with separate requirements.

## Decision

Use **Vite + React (TypeScript)** for `frontend/` (the dashboard portal), not Next.js.

When a public website is needed in the future, it will be built as a **separate package** (e.g., `website/`) using Next.js 15 or Astro, deployed independently at a different subdomain (`yourproduct.com` vs `app.yourproduct.com`).

## Reasoning

| Factor | Next.js | Vite + React |
|---|---|---|
| SSR / SEO | ✅ (unused — all pages are auth-gated) | ✗ (not needed) |
| API routes | ✅ (unused — FastAPI is the backend) | ✗ (not needed) |
| Dev server speed | Moderate | ✅ Very fast (Vite ESM HMR) |
| Mental model | Complex (RSC, server vs. client boundary) | ✅ Simple — just React |
| Bundle output | Node.js server required for SSR | ✅ Pure static `dist/` — any CDN |
| Appropriate for SPAs | Overkill | ✅ Purpose-built |

Mixing the private admin portal with the future public site in one Next.js app would introduce conflicting caching strategies, layout/routing complexity, and deployment coupling. Separation of concerns is the correct model (see: Linear, Vercel, Stripe — all run separate apps at `app.*` vs the root domain).

## Consequences

### Positive
- Simpler codebase — no server components, no `"use client"` directives, no hydration concerns.
- Significantly faster dev server iteration.
- Static `dist/` output deploys to any CDN (Vercel, Netlify, Render Static Site, S3+CloudFront).
- Future public website framework decision is fully independent — no lock-in.

### Negative
- If a public landing page is later added to this same domain path (not a subdomain), some routing configuration is needed at the CDN/reverse-proxy layer. This is standard practice and not a blocker.

### Environment Variables

Vite uses the `VITE_` prefix (instead of `NEXT_PUBLIC_`) to inline browser-safe variables at build time. The `.env.local` file uses `VITE_API_BASE_URL` instead of `NEXT_PUBLIC_API_BASE_URL`.
