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
import time
from typing import Any

from pydantic import BaseModel, ValidationError, create_model
from prisma.models import DocumentLog, Template
from prisma.fields import Json

from app.core.db import db
from app.services import gemini_service
from app.services import webhook_dispatcher

logger = logging.getLogger("app.services.pipeline")

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
) -> DocumentLog:
    """
    Execute the 3-stage extraction pipeline for a given DocumentLog record.

    Input modes (at least one must be provided):
      • Text-only  : raw_text set, file_bytes None.
      • File-only  : file_bytes + mime_type set, raw_text None.
      • Hybrid     : BOTH raw_text AND file_bytes set. Gemini receives both
                    sources in a single multimodal call (e.g. email body +
                    résumé PDF / invoice scan + cover note).

    If `target_template_id` is provided, Stage 1 (AI intent classification)
    is skipped and that specific template schema is used directly.

    Returns the final DocumentLog record after updating status in the DB.
    """
    start_ms = time.monotonic()

    # Mark as PROCESSING
    await db.documentlog.update(
        where={"id": doc_log_id},
        data={"status": "PROCESSING"},
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
                return await _finalize_and_dispatch(doc_log_id, start_ms, "UNMATCHED")
        else:
            # Fetch active templates for this workspace
            templates = await db.template.find_many(
                where={"workspaceId": workspace_id, "isActive": True},
            )

            if not templates:
                logger.info(
                    "[%s] No active templates found — marking UNMATCHED", doc_log_id
                )
                return await _finalize(doc_log_id, start_ms, "UNMATCHED")

            # ------------------------------------------------------------------ #
            # Stage 1: Intent Classification (Auto-detect)
            # ------------------------------------------------------------------ #
            matched_template = await _classify(
                doc_log_id=doc_log_id,
                templates=templates,
                raw_text=raw_text,
                file_bytes=file_bytes,
                mime_type=mime_type,
            )

            if matched_template is None:
                logger.info("[%s] No template matched — marking UNMATCHED", doc_log_id)
                return await _finalize(doc_log_id, start_ms, "UNMATCHED")

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
        raw_json_str = await _extract(
            doc_log_id=doc_log_id,
            template=matched_template,
            raw_text=raw_text,
            file_bytes=file_bytes,
            mime_type=mime_type,
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
            processing_ms = int((time.monotonic() - start_ms) * 1000)
            final_log = await db.documentlog.update(
                where={"id": doc_log_id},
                data={
                    "status": "FAILED",
                    "validationErrors": Json(validation_errors),  # type: ignore[arg-type]
                    "processingMs": processing_ms,
                },
            )
            asyncio.create_task(webhook_dispatcher.dispatch(final_log))
            return final_log

        # Check confidence scores to determine status
        final_status = "SUCCESS"
        if confidence_scores:
            has_low_confidence = any(score in ["Low", "Medium"] for score in confidence_scores.values())
            if has_low_confidence:
                final_status = "NEEDS_REVIEW"

        logger.info("[%s] Extraction complete, status: %s", doc_log_id, final_status)
        processing_ms = int((time.monotonic() - start_ms) * 1000)
        final_log = await db.documentlog.update(
            where={"id": doc_log_id},
            data={
                "status": final_status,
                "extractedJson": Json(extracted_data),  # type: ignore[arg-type]
                "confidenceScores": Json(confidence_scores) if confidence_scores else None,  # type: ignore[arg-type]
                "processingMs": processing_ms,
            },
        )
        asyncio.create_task(webhook_dispatcher.dispatch(final_log))
        return final_log

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Pipeline error: %s", doc_log_id, exc)
        processing_ms = int((time.monotonic() - start_ms) * 1000)
        final_log = await db.documentlog.update(
            where={"id": doc_log_id},
            data={
                "status": "FAILED",
                "validationErrors": Json({"pipeline_error": str(exc)}),  # type: ignore[arg-type]
                "processingMs": processing_ms,
            },
        )
        asyncio.create_task(webhook_dispatcher.dispatch(final_log))
        return final_log


# ---------------------------------------------------------------------------
# Stage 1 — Intent Classifier
# ---------------------------------------------------------------------------

async def _classify(
    doc_log_id: str,
    templates: list[Template],
    raw_text: str | None,
    file_bytes: bytes | None,
    mime_type: str | None,
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
        )
    elif raw_text:
        prompt += raw_text
        response = await gemini_service.generate_text(prompt)
    else:
        response = await gemini_service.generate_with_file(
            prompt=prompt,
            file_bytes=file_bytes,  # type: ignore[arg-type]
            mime_type=mime_type or "application/octet-stream",
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
        )
    elif raw_text:
        prompt += raw_text
        return await gemini_service.generate_text(prompt)
    else:
        return await gemini_service.generate_with_file(
            prompt=prompt,
            file_bytes=file_bytes,  # type: ignore[arg-type]
            mime_type=mime_type or "application/octet-stream",
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

async def _finalize_and_dispatch(
    doc_log_id: str,
    start_ms: float,
    status: str,
) -> DocumentLog:
    """Update final status, fire outbound webhook dispatch, and return the log."""
    processing_ms = int((time.monotonic() - start_ms) * 1000)
    final_log = await db.documentlog.update(
        where={"id": doc_log_id},
        data={"status": status, "processingMs": processing_ms},
    )
    asyncio.create_task(webhook_dispatcher.dispatch(final_log))
    return final_log


# Keep _finalize as an alias for legacy call-sites within the pipeline
_finalize = _finalize_and_dispatch
