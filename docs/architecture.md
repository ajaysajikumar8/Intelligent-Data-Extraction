# Architecture & Data Flow

## Overview

Multi-tenant pipeline: ingest unstructured data → classify intent → extract structured JSON → validate → store + deliver.

## Data Flow

```mermaid
graph TD
    subgraph Ingestion ["1. Ingestion Gateway"]
        API[Direct REST API]
        Email[Email OAuth Webhooks]
        Chat[Slack / Teams Bots]
        File[PDF & Image Uploads]
    end

    G[FastAPI Ingestion Gateway]

    API -->|JSON POST| G
    Email -->|Push Notification| G
    Chat -->|Bot Webhook| G
    File -->|Multipart Upload| G

    subgraph AI_Engine ["2. Multi-Tenant AI Engine"]
        Auth{Workspace Auth}
        M1[Stage 1: Intent Classifier]
        M2[Stage 2: Schema Extractor]
        Pydantic{Pydantic Validation}
    end

    G --> Auth
    Auth -->|Fetch Workspace Templates| M1
    M1 -->|Matched Template| M2
    M1 -->|Unrecognized| Drop[Log & Discard]
    M2 -->|Raw JSON| Pydantic

    subgraph Delivery ["3. Audit Storage & Delivery"]
        DB[(PostgreSQL Audit Log)]
        Webhook[Client Webhook Push]
    end

    Pydantic -->|Valid Structured JSON| DB
    Pydantic -->|Valid Structured JSON| Webhook
```

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| AI Engine | Google Gemini 1.5 Flash |
| Database | PostgreSQL, Prisma ORM |
| Frontend | Next.js (TypeScript) |
| Auth | JWT + optional Google OAuth |

## Repository Structure

```
intelligent-data-extraction/
├── .env.example
├── README.md
├── MEMORY.md
├── docs/
│   ├── architecture.md     ← you are here
│   ├── deployment.md
│   └── adr/                ← decision records
├── backend/
│   └── app/
│       ├── api/            # endpoints: ingest, templates, auth, logs
│       ├── core/           # config, security, auth
│       ├── models/         # Pydantic schemas
│       ├── services/       # Gemini logic, webhook dispatcher
│       └── main.py
├── frontend/
│   ├── src/
│   └── .env.local          # symlink → ../.env
└── prisma/
    └── schema.prisma
```
