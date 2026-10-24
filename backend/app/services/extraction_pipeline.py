"""
extraction_pipeline.py — 3-stage AI extraction orchestrator.

Stages
------
1. Intent Classifier  — asks Gemini which Template best matches the document.
2. Schema Extractor   — asks Gemini to pull out every field defined in the
                        matched template’s extractionSchema.
3. Pydantic Validator — dynamically builds a Pydantic model from the schema
                        and validates the raw JSON returned by Stage 2.

Input modes
-----------
  • Text-only   : raw_text is set, file_bytes is None.
  • File-only   : file_bytes + mime_type are set, raw_text is None.
  • Hybrid      : BOTH raw_text AND file_bytes are set (e.g. an email body
                  paired with a PDF attachment). Gemini processes both sources
                  in a single multimodal API call — useful for cases like a
                  cover letter email body + résumé PDF attachment submitted
                  together.

The pipeline is always called with a DocumentLog already created at
status=PENDING. It updates that record in-place through the pipeline,
finally landing on SUCCESS, FAILED, or UNMATCHED.
"""

import asyncio
import json
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, TypeVar

from pydantic import BaseModel, ValidationError, create_model
from prisma.models import DocumentLog, Template
from prisma.fields import Json

from app.core.db import db
from app.core.config import get_settings
from app.services import failures
from app.services import gemini_service
from app.services import webhook_dispatcher

logger = logging.getLogger("app.services.pipeline")

# Transient provider errors (5xx, network, per-call timeout) are retried with
# exponential backoff plus jitter before the document is failed. Provider overloads
# usually clear within seconds, so back off a little (≈5s, then ≈10s) rather than
# hammering. A single hung call is cut off after _CALL_TIMEOUT_S and counts as transient.
# Worst case per stage ≈ 3×60s + ~15s waiting; two stages fit inside the 450s job timeout.
_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_S = 5.0
_CALL_TIMEOUT_S = 60.0

# ---------------------------------------------------------------------------
# Type alias for the dynamic Pydantic field map
# ---------------------------------------------------------------------------
_PRISMA_TYPE_MAP: dict[str, Any] = {
    "string": (str | None, None),
    "number": (float | None, None),
    "integer": (int | None, None),
    "boolean": (bool | None, None),
    "array": (list | None, None),
    "object": (dict | None, None),
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run(
    doc_log_id: str,
    workspace_id: str,
    raw_text: str | None = None,
    file_bytes: bytes | None = None,
    mime_type: str | None = None,
    target_template_id: str | None = None,
    custom_api_key: str | None = None,
    allow_platform_fallback: bool = False,
    key_source: str | None = None,
) -> DocumentLog:
    """
    Execute the 3-stage extraction pipeline for a given DocumentLog record.

    API Key routing (in priority order):
      1. custom_api_key  — workspace's BYOAK Gemini key (decrypted by caller).
      2. Platform key    — only used if allow_platform_fallback is True.
         • If custom_api_key is set and hits quota, retries with platform key
           ("platform_fallback").
         • If custom_api_key is None and allow_platform_fallback is True,
           uses the platform key directly ("platform").
         • If neither condition is met, fails immediately with a clear error.

    Input modes (at least one must be provided):
      • Text-only  : raw_text set, file_bytes None.
      • File-only  : file_bytes + mime_type set, raw_text None.
      • Hybrid     : BOTH raw_text AND file_bytes set.

    If `target_template_id` is provided, Stage 1 (AI intent classification)
    is skipped and that specific template schema is used directly.

    Returns the final DocumentLog record after updating status in the DB.
    """
    start_ms = time.monotonic()
    router = _ModelRouter(backup=get_settings().GEMINI_FALLBACK_MODEL or None, key_source=key_source)

    # ------------------------------------------------------------------
    # Resolve which API key to use
    # ------------------------------------------------------------------
    # Determine the active key upfront. If no usable key is available,
    # fail immediately with a clear, actionable error message.
    active_key: str | None = custom_api_key  # None = use platform key

    if not custom_api_key and not allow_platform_fallback:
        # No custom key and platform fallback is off — nothing to use
        logger.warning(
            "[%s] No API key configured and platform fallback disabled — failing",
            doc_log_id,
        )
        return await _finish(
            doc_log_id,
            start_ms,
            "FAILED",
            validationErrors=Json(failures.failure(failures.FailureCode.NO_AI_KEY).to_json()),  # type: ignore[arg-type]
        )

    # Mark as PROCESSING (stage 1 is skipped when the caller picked a template)
    await db.documentlog.update(
        where={"id": doc_log_id},
        data={
            "status": "PROCESSING",
            "progress": Json(_progress("EXTRACTING" if target_template_id else "CLASSIFYING")),  # type: ignore[arg-type]
        },
    )

    try:
        matched_template: Template | None = None

        if target_template_id:
            # Explicit template selection — fetch directly
            matched_template = await db.template.find_first(
                where={"id": target_template_id, "workspaceId": workspace_id, "isActive": True},
            )
            if not matched_template:
                logger.warning(
                    "[%s] Target template '%s' not found or inactive — marking UNMATCHED",
                    doc_log_id,
                    target_template_id,
                )
                return await _finish(doc_log_id, start_ms, "UNMATCHED")
        else:
            # Fetch active templates for this workspace
            templates = await db.template.find_many(
                where={"workspaceId": workspace_id, "isActive": True},
            )

            if not templates:
                logger.info(
                    "[%s] No active templates found — marking UNMATCHED", doc_log_id
                )
                return await _finish(doc_log_id, start_ms, "UNMATCHED")

            # ------------------------------------------------------------------ #
            # Stage 1: Intent Classification (Auto-detect)
            # ------------------------------------------------------------------ #
            matched_template = await _call_with_fallback(
                doc_log_id=doc_log_id,
                stage="CLASSIFYING",
                router=router,
                custom_api_key=custom_api_key,
                allow_platform_fallback=allow_platform_fallback,
                fn=lambda key, model: _classify(
                    doc_log_id=doc_log_id,
                    templates=templates,
                    raw_text=raw_text,
                    file_bytes=file_bytes,
                    mime_type=mime_type,
                    api_key=key,
                    model=model,
                ),
            )

            if matched_template is None:
                logger.info("[%s] No template matched — marking UNMATCHED", doc_log_id)
                return await _finish(doc_log_id, start_ms, "UNMATCHED", **_usage(router))

        logger.info(
            "[%s] Classified as template '%s' (%s)",
            doc_log_id,
            matched_template.name,
            matched_template.id,
        )

        # Update DocumentLog with the matched templateId
        await db.documentlog.update(
            where={"id": doc_log_id},
            data={"template": {"connect": {"id": matched_template.id}}},  # type: ignore[arg-type]
        )

        # ------------------------------------------------------------------ #
        # Stage 2: Schema Extraction
        # ------------------------------------------------------------------ #
        await _set_progress(doc_log_id, "EXTRACTING", backup_model=router.use_backup)
        raw_json_str = await _call_with_fallback(
            doc_log_id=doc_log_id,
            stage="EXTRACTING",
            router=router,
            custom_api_key=custom_api_key,
            allow_platform_fallback=allow_platform_fallback,
            fn=lambda key, model: _extract(
                doc_log_id=doc_log_id,
                template=matched_template,
                raw_text=raw_text,
                file_bytes=file_bytes,
                mime_type=mime_type,
                api_key=key,
                model=model,
            ),
        )

        # ------------------------------------------------------------------ #
        # Stage 3: Pydantic Validation
        # ------------------------------------------------------------------ #
        extracted_data, confidence_scores, validation_errors = _validate(
            doc_log_id=doc_log_id,
            template=matched_template,
            raw_json_str=raw_json_str,
        )

        if validation_errors:
            logger.warning(
                "[%s] Validation failed: %s", doc_log_id, validation_errors
            )
            # Field-level issues are actionable (the user can fix the template or correct the
            # data). Errors with no `field` mean the AI's output could not be parsed at all,
            # which is not the user's doing: show a friendly message, not parser output.
            if any("field" not in e for e in validation_errors):
                payload: Any = failures.failure(failures.FailureCode.BAD_AI_OUTPUT).to_json()
            else:
                payload = validation_errors
            return await _finish(
                doc_log_id,
                start_ms,
                "FAILED",
                validationErrors=Json(payload),  # type: ignore[arg-type]
                **_usage(router),
            )

        # Check confidence scores to determine status
        final_status = "SUCCESS"
        if confidence_scores:
            has_low_confidence = any(score in ["Low", "Medium"] for score in confidence_scores.values())
            if has_low_confidence:
                final_status = "NEEDS_REVIEW"

        logger.info("[%s] Extraction complete, status: %s", doc_log_id, final_status)
        return await _finish(
            doc_log_id,
            start_ms,
            final_status,
            extractedJson=Json(extracted_data),  # type: ignore[arg-type]
            confidenceScores=Json(confidence_scores if confidence_scores else None),  # type: ignore[arg-type]
            **_usage(router),
        )

    except Exception as exc:  # noqa: BLE001
        # The raw exception stays in the server log; the user only sees a classified message.
        logger.exception("[%s] Pipeline error: %s", doc_log_id, exc)
        failure = failures.classify(exc)
        return await _finish(
            doc_log_id,
            start_ms,
            "FAILED",
            validationErrors=Json(failure.to_json()),  # type: ignore[arg-type]
            **_usage(router),
        )


T = TypeVar("T")


@dataclass
class _ModelRouter:
    """
    Per-job choice between the primary model and the optional backup model.

    Shared by both stages of a job: once the primary has failed transiently, later
    stages start on the backup instead of spending another attempt on a model we
    already know is busy. `backup=None` means the feature is off, or the backup was
    found unusable (retired/404) and dropped.
    """

    backup: str | None
    use_backup: bool = False
    # Recorded on the DocumentLog when the job finishes (ADR-013): whose key paid, and which model
    # answered last. `key_source` flips to WORKSPACE_THEN_PLATFORM if the workspace key hits its quota.
    key_source: str | None = None
    last_model: str | None = None

    @property
    def model(self) -> str | None:
        """Model override for the next call (None = the configured primary)."""
        return self.backup if self.use_backup else None


def _usage(router: _ModelRouter) -> dict[str, Any]:
    """`DocumentLog` fields recording which key and model a finished job used (omits unknowns)."""
    usage: dict[str, Any] = {}
    if router.key_source:
        usage["apiKeySource"] = router.key_source
    if router.last_model:
        usage["modelUsed"] = router.last_model
    return usage


def _progress(
    stage: str, attempt: int = 1, retry_reason: str | None = None, backup_model: bool = False
) -> dict[str, Any]:
    """Live progress shown to the user while a document is in flight."""
    return {
        "stage": stage,
        "attempt": attempt,
        "maxAttempts": _MAX_ATTEMPTS,
        "retryReason": retry_reason,  # a FailureCode while waiting to retry, else None
        "usingBackupModel": backup_model,  # the next attempt runs on GEMINI_FALLBACK_MODEL
    }


async def _set_progress(
    doc_log_id: str,
    stage: str,
    attempt: int = 1,
    retry_reason: str | None = None,
    backup_model: bool = False,
) -> None:
    """Best-effort: progress is informational and must never fail a job."""
    try:
        await db.documentlog.update(
            where={"id": doc_log_id},
            data={"progress": Json(_progress(stage, attempt, retry_reason, backup_model))},  # type: ignore[arg-type]
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[%s] Could not record progress: %s", doc_log_id, exc)


async def _call_with_fallback(
    doc_log_id: str,
    stage: str,
    router: _ModelRouter,
    custom_api_key: str | None,
    allow_platform_fallback: bool,
    fn: Callable[[str | None, str | None], Awaitable[T]],
) -> T:
    """
    Call `fn` with the workspace's custom BYOAK key if set.

    If the custom key hits a quota/rate-limit error and the workspace has
    opted into platform fallback, retry once with the platform key
    (fn(None) — see gemini_service._get_client). Any other error, or a quota
    error with fallback disabled, propagates so the pipeline fails loudly
    with a clear message instead of silently burning platform budget.
    """
    if not custom_api_key:
        # No custom key — caller already verified fallback is allowed.
        return await _with_retries(doc_log_id, stage, router, lambda model: fn(None, model))

    try:
        return await _with_retries(doc_log_id, stage, router, lambda model: fn(custom_api_key, model))
    except Exception as exc:
        if allow_platform_fallback and gemini_service.is_quota_error(exc):
            logger.warning(
                "[%s] Custom Gemini key quota exhausted — falling back to platform key",
                doc_log_id,
            )
            router.key_source = "WORKSPACE_THEN_PLATFORM"
            return await _with_retries(doc_log_id, stage, router, lambda model: fn(None, model))
        raise


async def _with_retries(
    doc_log_id: str, stage: str, router: _ModelRouter, call: Callable[[str | None], Awaitable[T]]
) -> T:
    """
    Run `call(model)`, retrying transient provider errors (5xx / network / per-call
    timeout) with exponential backoff and jitter, and recording each retry in the
    document's live progress. Non-transient errors — including quota (429), which
    `_call_with_fallback` handles by switching keys — propagate immediately.

    Backup model: the first attempt uses the configured primary model. After it
    fails transiently, the remaining attempts (and later stages of the same job) use
    GEMINI_FALLBACK_MODEL if configured. If the backup itself proves unusable (e.g.
    retired, 404) it is dropped and the primary is retried, and the primary's error
    is what finally surfaces: a bad backup setting must never mask "the AI is busy".
    """
    last_transient: Exception | None = None

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        model = router.model
        try:
            result = await asyncio.wait_for(call(model), timeout=_CALL_TIMEOUT_S)
            router.last_model = model or get_settings().GEMINI_MODEL
            if model:
                logger.info("[%s] %s completed on backup model '%s'", doc_log_id, stage, model)
            return result
        except Exception as exc:
            if failures.is_transient(exc):
                last_transient = exc
                router.use_backup = router.backup is not None  # this model is busy: try the backup next
            elif model is not None:
                # The backup model itself is unusable (e.g. retired): drop it, retry the primary.
                logger.warning(
                    "[%s] Backup model '%s' unusable (%s); continuing on the primary model",
                    doc_log_id, model, type(exc).__name__,
                )
                router.backup, router.use_backup = None, False
            else:
                raise
            if attempt == _MAX_ATTEMPTS:
                raise last_transient or exc
            delay = _RETRY_BASE_DELAY_S * 2 ** (attempt - 1)
            delay += random.uniform(0, delay * 0.25)  # jitter avoids synchronised retries
            await _set_progress(
                doc_log_id, stage, attempt + 1,
                failures.classify(last_transient or exc).code.value, router.use_backup,
            )
            logger.warning(
                "[%s] AI call failed (attempt %d/%d, model=%s), retrying in %.1fs%s: %s",
                doc_log_id, attempt, _MAX_ATTEMPTS, model or "primary", delay,
                " on the backup model" if router.use_backup else "", exc,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


# ---------------------------------------------------------------------------
# Stage 1 — Intent Classifier
# ---------------------------------------------------------------------------

async def _classify(
    doc_log_id: str,
    templates: list[Template],
    raw_text: str | None,
    file_bytes: bytes | None,
    mime_type: str | None,
    api_key: str | None = None,
    model: str | None = None,
) -> Template | None:
    """
    Ask Gemini which template best matches the document.

    Routing:
      • Text-only  → generate_text
      • File-only  → generate_with_file
      • Hybrid     → generate_with_text_and_file (text body + file in one call)

    Returns the matched Template or None.
    """
    template_list = "\n".join(
        f"- ID: {t.id} | Name: {t.name} | Description: {t.description or 'No description'}"
        for t in templates
    )

    prompt = (
        "You are a document classification engine.\n\n"
        "You will be shown a document and a list of extraction templates. "
        "Your task is to identify which single template best matches the document type.\n\n"
        f"Available templates:\n{template_list}\n\n"
        "Instructions:\n"
        "1. Analyse the document content.\n"
        "2. Select the single best matching template.\n"
        "3. Respond with ONLY the template ID string, nothing else.\n"
        "4. If no template matches at all, respond with exactly: UNMATCHED\n\n"
        "Document content:\n"
    )

    if raw_text and file_bytes:
        # Hybrid: email body text + file attachment together
        response = await gemini_service.generate_with_text_and_file(
            prompt=prompt,
            text_body=raw_text,
            file_bytes=file_bytes,
            mime_type=mime_type or "application/octet-stream",
            api_key=api_key,
            model=model,
        )
    elif raw_text:
        prompt += raw_text
        response = await gemini_service.generate_text(prompt, api_key=api_key, model=model)
    else:
        response = await gemini_service.generate_with_file(
            prompt=prompt,
            file_bytes=file_bytes,  # type: ignore[arg-type]
            mime_type=mime_type or "application/octet-stream",
            api_key=api_key,
            model=model,
        )

    response = response.strip()

    if response == "UNMATCHED":
        return None

    # Match the returned ID against the known templates
    for template in templates:
        if template.id == response:
            return template

    logger.warning(
        "[%s] Gemini returned unknown template ID '%s' — treating as UNMATCHED",
        doc_log_id,
        response,
    )
    return None


# ---------------------------------------------------------------------------
# Stage 2 — Schema Extractor
# ---------------------------------------------------------------------------

async def _extract(
    doc_log_id: str,
    template: Template,
    raw_text: str | None,
    file_bytes: bytes | None,
    mime_type: str | None,
    api_key: str | None = None,
    model: str | None = None,
) -> str:
    """
    Ask Gemini to extract fields defined in the template’s extractionSchema.

    Routing:
      • Text-only  → generate_text
      • File-only  → generate_with_file
      • Hybrid     → generate_with_text_and_file (single combined call)

    Returns a raw JSON string.
    """
    schema = template.extractionSchema  # type: ignore[attr-defined]
    schema_str = json.dumps(schema, indent=2)

    # Fetch up to 3 recent corrections for this exact template version
    corrections = await db.extractioncorrection.find_many(
        where={
            "templateId": template.id,
            "templateVersion": template.version,
        },
        order={"createdAt": "desc"},
        take=3,
    )

    correction_prompt = ""
    if corrections:
        correction_prompt = "\n--- CRITICAL: LEARN FROM PAST MISTAKES ---\n"
        correction_prompt += "In the past, you made mistakes extracting for this schema. Here are corrections provided by a human:\n"
        for i, corr in enumerate(corrections, 1):
            correction_prompt += f"\nExample {i}:\n"
            # Parse and re-dump to ensure it fits neatly
            try:
                orig = json.dumps(json.loads(str(corr.originalJson)))
                fixed = json.dumps(json.loads(str(corr.correctedJson)))
            except Exception:
                orig = str(corr.originalJson)
                fixed = str(corr.correctedJson)
            correction_prompt += f"Original Flawed Extraction: {orig}\n"
            correction_prompt += f"Human Corrected Extraction: {fixed}\n"
        correction_prompt += "Do not repeat these mistakes.\n------------------------------------------\n\n"

    prompt = (
        "You are a structured data extraction engine.\n\n"
        "Extract information from the document below and return it as a single "
        "valid JSON object. Follow these rules strictly:\n"
        "1. You MUST return exactly two top-level keys: `extracted_data` and `confidence_scores`.\n"
        "2. `extracted_data` must strictly follow the target schema provided below.\n"
        "3. Use null in `extracted_data` for any field you cannot find in the document.\n"
        "4. `confidence_scores` must be a flat dictionary mapping every field key to a confidence level: 'High', 'Medium', or 'Low'.\n"
        "5. Return ONLY the JSON object — no markdown, no code fences, no explanation.\n"
        "6. When multiple sources are provided (text body + file), extract from "
        "BOTH and merge into one JSON object.\n\n"
        f"Target schema for `extracted_data`:\n{schema_str}\n"
        f"{correction_prompt}"
        "Document content:\n"
    )

    if raw_text and file_bytes:
        # Hybrid: combine text body + file in a single Gemini call
        return await gemini_service.generate_with_text_and_file(
            prompt=prompt,
            text_body=raw_text,
            file_bytes=file_bytes,
            mime_type=mime_type or "application/octet-stream",
            api_key=api_key,
            model=model,
        )
    elif raw_text:
        prompt += raw_text
        return await gemini_service.generate_text(prompt, api_key=api_key, model=model)
    else:
        return await gemini_service.generate_with_file(
            prompt=prompt,
            file_bytes=file_bytes,  # type: ignore[arg-type]
            mime_type=mime_type or "application/octet-stream",
            api_key=api_key,
            model=model,
        )


# ---------------------------------------------------------------------------
# Stage 3 — Pydantic Validator
# ---------------------------------------------------------------------------

def _validate(
    doc_log_id: str,
    template: Template,
    raw_json_str: str,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, list[dict] | None]:
    """
    Parse and validate the raw JSON string from Stage 2 using a dynamically
    built Pydantic model derived from the template's extractionSchema.

    Returns:
        (validated_data, confidence_scores, None)      on success
        (None, None, list_of_error_dicts)              on failure
    """
    # Step 1: Parse JSON
    try:
        # Strip markdown code fences if Gemini ignored the instruction
        cleaned = raw_json_str.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            cleaned = "\n".join(
                line for line in lines if not line.startswith("```")
            ).strip()
        parsed: dict[str, Any] = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return None, None, [{"type": "json_parse_error", "message": str(exc)}]

    # Step 1.5: Split the sidecar object
    extracted_data = parsed.get("extracted_data")
    confidence_scores = parsed.get("confidence_scores")

    # Fallback in case Gemini ignored the sidecar instruction and returned flat data
    if extracted_data is None and confidence_scores is None:
        extracted_data = parsed
        confidence_scores = {}

    if not isinstance(extracted_data, dict):
        return None, None, [{"type": "validation_error", "message": "extracted_data must be an object"}]

    # Step 2: Build dynamic Pydantic model from schema
    schema = template.extractionSchema  # type: ignore[attr-defined]
    if not isinstance(schema, dict):
        return extracted_data, confidence_scores, None  # Can't validate further — return as-is

    field_definitions: dict[str, Any] = {}
    for field_name, field_type in schema.items():
        field_type_str = str(field_type).lower()
        field_definitions[field_name] = _PRISMA_TYPE_MAP.get(
            field_type_str, (Any | None, None)
        )

    if not field_definitions:
        return extracted_data, confidence_scores, None

    DynamicModel = create_model("DynamicExtractionModel", **field_definitions)  # type: ignore[call-overload]

    # Step 3: Validate
    try:
        validated = DynamicModel(**extracted_data)
        return validated.model_dump(), confidence_scores, None
    except ValidationError as exc:
        errors = [
            {"field": e["loc"][0] if e["loc"] else "unknown", "message": e["msg"]}
            for e in exc.errors()
        ]
        return None, None, errors


def validate_correction(template: Template | None, corrected_data: dict[str, Any]) -> tuple[dict[str, Any] | None, list[dict] | None]:
    """Validate a human-provided correction against the template schema."""
    if not template:
        return corrected_data, None
        
    schema = template.extractionSchema  # type: ignore[attr-defined]
    if not isinstance(schema, dict):
        return corrected_data, None

    field_definitions: dict[str, Any] = {}
    for field_name, field_type in schema.items():
        field_type_str = str(field_type).lower()
        field_definitions[field_name] = _PRISMA_TYPE_MAP.get(
            field_type_str, (Any | None, None)
        )

    if not field_definitions:
        return corrected_data, None

    DynamicModel = create_model("DynamicExtractionModel", **field_definitions)  # type: ignore[call-overload]

    try:
        validated = DynamicModel(**corrected_data)
        return validated.model_dump(), None
    except ValidationError as exc:
        errors = [
            {"field": e["loc"][0] if e["loc"] else "unknown", "message": e["msg"]}
            for e in exc.errors()
        ]
        return None, errors

# ---------------------------------------------------------------------------

# Helper — finalize DocumentLog with no extraction data
# ---------------------------------------------------------------------------

async def _finish(
    doc_log_id: str,
    start_ms: float,
    status: str,
    **data: Any,
) -> DocumentLog:
    """
    Single exit point for every terminal state: persist the final status and
    result fields, then fire the outbound webhook dispatch.
    """
    final_log = await db.documentlog.update(
        where={"id": doc_log_id},
        data={
            "status": status,
            "processingMs": int((time.monotonic() - start_ms) * 1000),
            "progress": Json(None),  # terminal: nothing left in flight  # type: ignore[arg-type]
            **data,
        },  # type: ignore[arg-type]
    )
    asyncio.create_task(webhook_dispatcher.dispatch(final_log))
    return final_log


async def fail_document(doc_log_id: str, failure: failures.Failure) -> None:
    """
    Fail a document from outside the pipeline (queue timeout / interruption).

    Only touches rows that are still in flight so a document that already
    finished is never overwritten.
    """
    updated = await db.documentlog.update_many(
        where={"id": doc_log_id, "status": {"in": ["PENDING", "PROCESSING"]}},  # type: ignore[arg-type]
        data={
            "status": "FAILED",
            "validationErrors": Json(failure.to_json()),  # type: ignore[arg-type]
            "progress": Json(None),  # type: ignore[arg-type]
        },
    )
    if updated:
        final_log = await db.documentlog.find_unique(where={"id": doc_log_id})
        if final_log:
            asyncio.create_task(webhook_dispatcher.dispatch(final_log))
