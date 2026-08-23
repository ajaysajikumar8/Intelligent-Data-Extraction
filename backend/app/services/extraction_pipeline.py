"""
extraction_pipeline.py — 3-stage AI extraction orchestrator.

Stages
------
1. Intent Classifier  — asks Gemini which Template best matches the document.
2. Schema Extractor   — asks Gemini to pull out every field defined in the
                        matched template's extractionSchema.
3. Pydantic Validator — dynamically builds a Pydantic model from the schema
                        and validates the raw JSON returned by Stage 2.

The pipeline is always called with a DocumentLog already created at
status=PENDING. It updates that record in-place through the pipeline,
finally landing on SUCCESS, FAILED, or UNMATCHED.
"""

import json
import logging
import time
from typing import Any

from pydantic import BaseModel, ValidationError, create_model
from prisma.models import DocumentLog, Template
from prisma.fields import Json

from app.core.db import db
from app.services import gemini_service

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
) -> DocumentLog:
    """
    Execute the 3-stage extraction pipeline for a given DocumentLog record.

    Exactly one of `raw_text` or (`file_bytes` + `mime_type`) must be provided.

    Returns the final DocumentLog record after updating status in the DB.
    """
    start_ms = time.monotonic()

    # Mark as PROCESSING
    await db.documentlog.update(
        where={"id": doc_log_id},
        data={"status": "PROCESSING"},
    )

    try:
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
        # Stage 1: Intent Classification
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
        extracted_data, validation_errors = _validate(
            doc_log_id=doc_log_id,
            template=matched_template,
            raw_json_str=raw_json_str,
        )

        if validation_errors:
            logger.warning(
                "[%s] Validation failed: %s", doc_log_id, validation_errors
            )
            processing_ms = int((time.monotonic() - start_ms) * 1000)
            return await db.documentlog.update(
                where={"id": doc_log_id},
                data={
                    "status": "FAILED",
                    "validationErrors": Json(validation_errors),  # type: ignore[arg-type]
                    "processingMs": processing_ms,
                },
            )

        logger.info("[%s] Extraction successful", doc_log_id)
        processing_ms = int((time.monotonic() - start_ms) * 1000)
        return await db.documentlog.update(
            where={"id": doc_log_id},
            data={
                "status": "SUCCESS",
                "extractedJson": Json(extracted_data),  # type: ignore[arg-type]
                "processingMs": processing_ms,
            },
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("[%s] Pipeline error: %s", doc_log_id, exc)
        processing_ms = int((time.monotonic() - start_ms) * 1000)
        return await db.documentlog.update(
            where={"id": doc_log_id},
            data={
                "status": "FAILED",
                "validationErrors": Json({"pipeline_error": str(exc)}),  # type: ignore[arg-type]
                "processingMs": processing_ms,
            },
        )


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

    if raw_text:
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
    Ask Gemini to extract fields defined in the template's extractionSchema.
    Returns a raw JSON string.
    """
    schema = template.extractionSchema  # type: ignore[attr-defined]
    schema_str = json.dumps(schema, indent=2)

    prompt = (
        "You are a structured data extraction engine.\n\n"
        "Extract information from the document below and return it as a single "
        "valid JSON object. Follow these rules strictly:\n"
        "1. Only extract the fields defined in the target schema.\n"
        "2. Use null for any field you cannot find in the document.\n"
        "3. Match the data types: strings as strings, numbers as numbers, "
        "arrays as arrays.\n"
        "4. Return ONLY the JSON object — no markdown, no code fences, no explanation.\n\n"
        f"Target schema:\n{schema_str}\n\n"
        "Document content:\n"
    )

    if raw_text:
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
) -> tuple[dict[str, Any] | None, list[dict] | None]:
    """
    Parse and validate the raw JSON string from Stage 2 using a dynamically
    built Pydantic model derived from the template's extractionSchema.

    Returns:
        (validated_data, None)        on success
        (None, list_of_error_dicts)   on failure
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
        return None, [{"type": "json_parse_error", "message": str(exc)}]

    # Step 2: Build dynamic Pydantic model from schema
    schema = template.extractionSchema  # type: ignore[attr-defined]
    if not isinstance(schema, dict):
        return parsed, None  # Can't validate further — return as-is

    field_definitions: dict[str, Any] = {}
    for field_name, field_type in schema.items():
        field_type_str = str(field_type).lower()
        field_definitions[field_name] = _PRISMA_TYPE_MAP.get(
            field_type_str, (Any | None, None)
        )

    if not field_definitions:
        return parsed, None

    DynamicModel = create_model("DynamicExtractionModel", **field_definitions)  # type: ignore[call-overload]

    # Step 3: Validate
    try:
        validated = DynamicModel(**parsed)
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

async def _finalize(
    doc_log_id: str,
    start_ms: float,
    status: str,
) -> DocumentLog:
    processing_ms = int((time.monotonic() - start_ms) * 1000)
    return await db.documentlog.update(
        where={"id": doc_log_id},
        data={"status": status, "processingMs": processing_ms},
    )
