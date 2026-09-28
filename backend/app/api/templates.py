"""
templates.py — Template management endpoints.

All endpoints are workspace-scoped via the `get_current_workspace`
authentication dependency (Bearer JWT or X-API-Key).

Routes
------
POST   /api/v1/templates          — Create a new extraction template
GET    /api/v1/templates          — List all active templates (workspace)
GET    /api/v1/templates/{id}     — Get a single template by ID
PUT    /api/v1/templates/{id}     — Update template (auto-bumps version)
DELETE /api/v1/templates/{id}     — Soft-delete (isActive = false)
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from prisma.models import Workspace
from prisma.fields import Json

from app.core.auth import get_current_workspace
from app.core.db import db
from app.core.template_library import LIBRARY_TEMPLATES, get_library_template
from app.models.schemas import (
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    LibraryTemplateResponse,
)

logger = logging.getLogger("app.api.templates")
router = APIRouter()


def _to_response(template: Any) -> TemplateResponse:
    """
    Convert a Prisma Template model to a TemplateResponse Pydantic schema.

    Prisma-Python returns Json fields as a `Json` object whose serialised value
    lives in `.data` (or is already a dict when deserialized).  We normalise
    this to a plain dict before handing off to Pydantic.
    """
    raw_schema = template.extractionSchema
    # Unwrap Prisma Json wrapper if necessary
    if hasattr(raw_schema, "data"):
        raw_schema = raw_schema.data
    if isinstance(raw_schema, str):
        import json as _json
        raw_schema = _json.loads(raw_schema)

    return TemplateResponse(
        id=template.id,
        workspaceId=template.workspaceId,
        name=template.name,
        description=template.description,
        extractionSchema=raw_schema,
        version=template.version,
        isActive=template.isActive,
        createdAt=template.createdAt,
        updatedAt=template.updatedAt,
    )


# ---------------------------------------------------------------------------
# POST /templates — Create
# ---------------------------------------------------------------------------

@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    """
    Create a new extraction template for the authenticated workspace.

    The `schema` field must be a JSON object mapping field names to type
    descriptors, e.g. `{"vendor_name": "string", "total_amount": "number"}`.
    """
    template = await db.template.create(
        data={
            "name": payload.name,
            "description": payload.description,
            "extractionSchema": Json(payload.schema_),  # type: ignore[arg-type]
            "workspace": {"connect": {"id": workspace.id}},
        }
    )
    logger.info(
        "Template '%s' created (ID: %s) for workspace %s",
        template.name,
        template.id,
        workspace.id,
    )
    return _to_response(template)


# ---------------------------------------------------------------------------
# GET /templates/library — List System Templates
# ---------------------------------------------------------------------------

@router.get("/library", response_model=list[LibraryTemplateResponse])
async def list_library_templates(
    workspace: Workspace = Depends(get_current_workspace),
) -> list[LibraryTemplateResponse]:
    """
    List all pre-built system templates available in the library.
    These are served from static configuration, not the database.
    """
    return [LibraryTemplateResponse(**t) for t in LIBRARY_TEMPLATES]


# ---------------------------------------------------------------------------
# POST /templates/library/{slug}/duplicate — Duplicate System Template
# ---------------------------------------------------------------------------

@router.post("/library/{slug}/duplicate", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_library_template(
    slug: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    """
    Duplicate a pre-built library template into the user's workspace.
    """
    lib_template = get_library_template(slug)
    if not lib_template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Library template '{slug}' not found.",
        )

    # Insert a new row for this user's workspace
    template = await db.template.create(
        data={
            "name": lib_template["name"],
            "description": lib_template.get("description"),
            "extractionSchema": Json(lib_template["schema"]),  # type: ignore[arg-type]
            "workspace": {"connect": {"id": workspace.id}},
        }
    )
    logger.info(
        "Library template '%s' duplicated as (ID: %s) for workspace %s",
        slug,
        template.id,
        workspace.id,
    )
    return _to_response(template)


# ---------------------------------------------------------------------------
# GET /templates — List
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    workspace: Workspace = Depends(get_current_workspace),
    include_inactive: bool = False,
) -> list[TemplateResponse]:
    """
    List all templates for the authenticated workspace.

    By default only active templates are returned. Pass
    `?include_inactive=true` to include soft-deleted ones.
    """
    where: dict[str, Any] = {"workspaceId": workspace.id}
    if not include_inactive:
        where["isActive"] = True

    templates = await db.template.find_many(
        where=where,
        skip=skip,
        take=limit,
        order={"createdAt": "desc"},
    )
    return [_to_response(t) for t in templates]


# ---------------------------------------------------------------------------
# GET /templates/{id} — Get single
# ---------------------------------------------------------------------------

@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    """
    Get a single template by ID. Returns 404 if not found or belongs to
    a different workspace.
    """
    template = await db.template.find_first(
        where={"id": template_id, "workspaceId": workspace.id},
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found.",
        )
    return _to_response(template)


# ---------------------------------------------------------------------------
# PUT /templates/{id} — Update
# ---------------------------------------------------------------------------

@router.put("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    payload: TemplateUpdate,
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    """
    Update a template's metadata or schema.

    If `schema` is updated, the version number is automatically incremented
    to make it easy to track which DocumentLogs were processed against which
    schema version.
    """
    existing = await db.template.find_first(
        where={"id": template_id, "workspaceId": workspace.id},
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found.",
        )

    update_data: dict[str, Any] = {}
    if payload.name is not None:
        update_data["name"] = payload.name
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.isActive is not None:
        update_data["isActive"] = payload.isActive
    if payload.schema_ is not None:
        update_data["extractionSchema"] = Json(payload.schema_)  # type: ignore[assignment]
        update_data["version"] = existing.version + 1

    if not update_data:
        # Nothing to update — return as-is
        return _to_response(existing)

    updated = await db.template.update(
        where={"id": template_id},
        data=update_data,  # type: ignore[arg-type]
    )
    logger.info(
        "Template '%s' updated (ID: %s, version: %s)",
        updated.name,
        updated.id,
        updated.version,
    )
    return _to_response(updated)


# ---------------------------------------------------------------------------
# DELETE /templates/{id} — Soft-delete
# ---------------------------------------------------------------------------

@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> None:
    """
    Soft-delete a template by setting `isActive = false`.

    Past DocumentLog records that reference this template are preserved.
    The template will no longer appear in active template listings or
    be used for new extractions.
    """
    existing = await db.template.find_first(
        where={"id": template_id, "workspaceId": workspace.id},
    )
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Template '{template_id}' not found.",
        )

    await db.template.update(
        where={"id": template_id},
        data={"isActive": False},
    )
    logger.info(
        "Template '%s' soft-deleted (ID: %s)", existing.name, template_id
    )
