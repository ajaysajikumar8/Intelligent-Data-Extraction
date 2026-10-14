# Bring Your Own API Key (BYOAK)

Allow workspace owners to register their own Google Gemini API key. Extractions will consume their key first, so they only pay us a service charge. If their quota runs out, the pipeline automatically falls back to the platform key.

---

## How It Works (User Flow)

There are **two independent controls** in Settings → AI Integration:

### Control 1 — Custom Gemini Key (BYOAK)
User pastes their own `AIzaSy...` key. All extractions use it. They only pay our service charge.

### Control 2 — Platform Key Fallback (Kill Switch)
A toggle that is **OFF by default**. Turning it ON means:
- If their key is exhausted (quota/rate limit), we fall back to our key.
- Turning it on signals explicit consent to be billed for platform usage.
- Turning it on requires an active paid plan.

### Full Logic Matrix

| Custom Key Set | Fallback Toggle | Behaviour |
|---|---|---|
| ❌ No | — | Blocked — must set a key or subscribe to a paid plan |
| ✅ Yes | ❌ Off (default) | Uses only their key. If it hits quota → extraction **fails** with a clear message |
| ✅ Yes | ✅ On (paid) | Uses their key first. On quota error → silently retries with platform key |
| ❌ No | ✅ On (paid subscriber) | Uses platform key exclusively |

This ensures we **never spend platform budget on a user who hasn't explicitly opted in and paid**.

---

## Open Questions

> [!NOTE]
> **Decided — encrypt the stored Gemini key at rest.**
> Option B (Fernet via `cryptography`, `ENCRYPTION_KEY` env var). Implemented in
> [encryption.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/core/encryption.py)
> and wired into `PUT /api/v1/workspaces/current/gemini-key`.
> **Still pending:** `ENCRYPTION_KEY` has not been generated/set in `backend/.env` yet —
> until it is, keys are stored as plaintext with a warning logged on every save.

> [!NOTE]
> **Decided — validate the key on save.**
> Option B (lightweight `count_tokens` call). Implemented as
> `gemini_service.validate_api_key()` and called from
> `PUT /api/v1/workspaces/current/gemini-key`, which returns `422` on an invalid key.

> [!IMPORTANT]
> **What plan is required to enable Platform Fallback?**
> - Option A: Any paid plan (Pro+) can enable it.
> - Option B: Requires a specific "Platform Fallback" add-on entitlement on the Plan model.
>
> **Recommendation**: Option A for now (Pro plan gate). Can be made more granular later.

---

## Proposed Changes

### Backend — Database Schema

#### [MODIFY] [schema.prisma](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/prisma/schema.prisma)

Add two optional fields to `Workspace`:

```diff
 model Workspace {
   id             String   @id @default(uuid())
   name           String
   slug           String   @unique
   apiKey         String   @unique @default(uuid())
   inboundSecret  String   @unique
   planId         String
   createdAt      DateTime @default(now())
+  geminiApiKey          String?   // Encrypted BYOAK — null means use platform key
+  allowPlatformFallback Boolean  @default(false)  // Kill switch — explicit opt-in to spend platform budget
```

Run `prisma db push` from `backend/` after this change.

---

### Backend — Encryption Utility

#### [NEW] `backend/app/core/encryption.py`

A thin Fernet wrapper using a new `ENCRYPTION_KEY` env var. Used only for the Gemini API key field.

```python
def encrypt(value: str) -> str: ...
def decrypt(value: str) -> str: ...
```

If `ENCRYPTION_KEY` is not set, it logs a warning and stores plaintext (for easier local dev without configuration overhead).

---

### Backend — Gemini Service Refactor

#### [MODIFY] [gemini_service.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/services/gemini_service.py)

**Critical change**: The current `@lru_cache(maxsize=1)` singleton is incompatible with per-workspace keys. It must be changed to a **keyed cache** (`dict[str, GenerativeModel]`).

```diff
-@lru_cache(maxsize=1)
-def _get_model() -> genai.GenerativeModel:
-    settings = get_settings()
-    genai.configure(api_key=settings.GEMINI_API_KEY)
-    return genai.GenerativeModel(...)
+_model_cache: dict[str, genai.GenerativeModel] = {}
+
+def _get_model(api_key: str) -> genai.GenerativeModel:
+    if api_key not in _model_cache:
+        genai.configure(api_key=api_key)   # thread-safe on separate client objects
+        _model_cache[api_key] = genai.GenerativeModel(...)
+    return _model_cache[api_key]
```

All public methods (`generate_text`, `generate_with_file`, `generate_with_text_and_file`) gain an optional `api_key: str | None = None` parameter. If `None`, they fall back to `settings.GEMINI_API_KEY`.

---

### Backend — Extraction Pipeline

#### [MODIFY] [extraction_pipeline.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/services/extraction_pipeline.py)

The `run()` function gains two new parameters:

```python
async def run(
    doc_log_id: str,
    workspace_id: str,
    raw_text: str | None = None,
    file_bytes: bytes | None = None,
    mime_type: str | None = None,
    target_template_id: str | None = None,
+   custom_api_key: str | None = None,        # decrypted workspace BYOAK, or None
+   allow_platform_fallback: bool = False,    # kill switch
) -> DocumentLog:
```

Internal routing logic:

```
if custom_api_key:
    try:
        → call Gemini with custom_api_key
    except ResourceExhausted (HTTP 429):
        if allow_platform_fallback:
            log warning: "Quota exhausted, falling back to platform key"
            → retry call with platform key
            → record api_key_source = "platform_fallback"
        else:
            → FAIL the extraction with status=FAILED
            → validationErrors = { "error": "Your API key quota is exhausted. Enable platform fallback in Settings or top up your quota." }
else:
    if allow_platform_fallback (implies paid plan):
        → call Gemini with platform key
        → record api_key_source = "platform"
    else:
        → FAIL immediately — no key configured and fallback is off
        → validationErrors = { "error": "No AI key configured. Add your Gemini API key in Settings." }
```

Store `api_key_source` in `processingMeta` (new JSON field on `DocumentLog`).

---

### Backend — Ingest API

#### [MODIFY] [ingest.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/api/ingest.py)

When building the `run()` call, fetch and decrypt the workspace's `geminiApiKey` and pass both parameters:

```python
custom_key = decrypt(workspace.geminiApiKey) if workspace.geminiApiKey else None
asyncio.create_task(extraction_pipeline.run(
    ...,
    custom_api_key=custom_key,
    allow_platform_fallback=workspace.allowPlatformFallback,
))
```

---

### Backend — Workspace API

#### [MODIFY] [workspaces.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/api/workspaces.py)

Add three new endpoints (owner only):

| Method | Path | Description |
|---|---|---|
| `PUT` | `/api/v1/workspaces/current/gemini-key` | Validate and save an encrypted Gemini API key |
| `DELETE` | `/api/v1/workspaces/current/gemini-key` | Remove the key |
| `PUT` | `/api/v1/workspaces/current/platform-fallback` | Toggle the kill switch (requires paid plan check) |

The `PUT /platform-fallback` endpoint will:
1. Accept `{ "enabled": true/false }` in the body.
2. If `enabled: true`, verify the workspace is on a paid plan. Return `403` if on free tier.
3. Write `allowPlatformFallback` to the database.
4. Return the updated workspace.

---

### Backend — Config & Env

#### [MODIFY] [config.py](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/app/core/config.py)

```diff
+ ENCRYPTION_KEY: str | None = None   # Fernet key for encrypting BYOAK keys at rest
```

#### [MODIFY] [backend/.env](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/backend/.env)

Document and add `ENCRYPTION_KEY` (generated via `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`).

---

### Frontend — Settings Page

#### [MODIFY] [Settings.tsx](file:///home/ajay/Projects/personal/Intelligent-Data-Extraction/frontend/src/pages/Settings.tsx)

Add a new **"AI Integration"** section:

```
┌─────────────────────────────────────────────────────────────────┐
│  🤖  AI Integration                                              │
│                                                                 │
│  YOUR GEMINI API KEY                                            │
│  Status: ● No custom key — using platform key                   │
│  [Input: AIzaSy...                      ] [Save Key] [Remove]   │
│  ℹ️  Get your key at Google AI Studio →                          │
│                                                                 │
│  ─────────────────────────────────────────────────────────────  │
│                                                                 │
│  PLATFORM KEY FALLBACK                              [Toggle OFF]│
│  "If your key hits its quota, use the platform key."            │
│  ⚠️  This will incur usage charges on your account.             │
│     Requires a paid plan. Currently: Free → Upgrade             │
│     (or: Currently: Pro ✓)                                      │
└─────────────────────────────────────────────────────────────────┘
```

Toggle behaviour:
- Toggling ON on a free plan shows a toast: `"Platform fallback requires a paid plan. Upgrade to enable this."`
- Toggling ON on a paid plan shows a confirmation: `"This may incur charges. Enable platform fallback?"` with a Confirm/Cancel.
- Status indicator updates live from the workspace response.

---

### Frontend — API Client

#### [MODIFY] `frontend/src/lib/api.ts`

Add three methods to the `workspaces` object:

```typescript
saveGeminiKey: (key: string) => Promise<{ status: string }>
deleteGeminiKey: () => Promise<void>
setPlatformFallback: (enabled: boolean) => Promise<WorkspaceResponse>
```

#### [MODIFY] `frontend/src/lib/types.ts`

Add to `WorkspaceResponse`:

```typescript
geminiApiKeySet: boolean           // true = custom key saved (never expose raw value)
allowPlatformFallback: boolean     // current kill switch state
```

---

## Verification Plan

### Automated Tests
- `pytest backend/tests/test_byoak.py` — new test file covering:
  - Saving/deleting key via API
  - Extraction with workspace key (mock Gemini)
  - Quota fallback behaviour (mock 429 → assert retry with platform key)
  - Invalid key returns 422 during save

### Manual Verification
1. Go to Settings → save a valid Gemini API key → status shows "Using your key".
2. Submit an extraction → check the Log details for `api_key_source: "workspace"`.
3. Delete the key → submit again → check for `api_key_source: "platform"`.
