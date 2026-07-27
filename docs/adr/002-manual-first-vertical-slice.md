# ADR-002: Manual Ingestion First (Vertical Slice Strategy)

**Status:** Accepted  
**Date:** 2026-07-28

## Context

Building automated email webhooks (Gmail/Outlook OAuth, webhook domain verifications, external push listeners) at the very start introduces significant external configuration friction before validating the core system logic.

Additionally, regardless of how data enters the system (automated webhook push vs. manual UI form paste), the downstream payload delivered to the AI extraction engine is identical: raw text content + optional file attachments.

## Decision

Adopt a **"Vertical Slice First"** development strategy:
1. Build and validate the manual ingestion path (`/submit` screen + `/api/ingest` endpoint) first.
2. Complete the core AI extraction pipeline (Gemini Intent Classifier + Schema Extractor + Pydantic Validation + Database Audit Logging) end-to-end.
3. Defer automated OAuth email listeners and external webhook push integrations until after the core manual slice is 100% operational.

## Consequences

### Positive
- **Zero External Obstacles**: No waiting on third-party OAuth app verification, domain registration, or cloud webhook endpoints during initial development.
- **Immediate E2E Validation**: Validates the entire flow (UI $\rightarrow$ FastAPI Gateway $\rightarrow$ Gemini AI Engine $\rightarrow$ Pydantic Schema $\rightarrow$ PostgreSQL Log) in Phase 1.
- **10x Faster Iteration**: Developers can test prompt variations, schema definitions, and edge-case documents directly in the UI in seconds without sending real emails.
- **Seamless Webhook Addition**: Automated listeners can later be added as thin wrappers over the already-proven `/api/ingest` endpoint.

### Negative
- Automated email synchronization must be tested separately after manual ingestion is complete.
