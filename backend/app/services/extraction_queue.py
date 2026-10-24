"""
extraction_queue.py — In-process job queue for the extraction pipeline.

Why
---
Extraction takes 10–60 s and depends on a third-party API that can be slow or
briefly unavailable, so it must not run inside the HTTP request. Callers create
a PENDING DocumentLog, call `enqueue()`, and respond immediately; clients read
the outcome from the log (polling) or the outbound webhook.

Guarantees
----------
  • Bounded concurrency   — at most EXTRACTION_MAX_CONCURRENCY jobs hit Gemini at once.
  • Bounded backlog       — `ensure_capacity()` rejects new work when full. Queued
                            jobs hold uploaded file bytes in memory.
  • Always terminal       — each job has a timeout; timeouts, cancellation and
                            unexpected errors all mark the document FAILED.
  • Graceful shutdown     — in-flight jobs get a grace period; the rest are
                            cancelled and marked INTERRUPTED.
  • Crash recovery        — `recover_orphans()` fails rows left in flight by a
                            crashed process. The age cutoff keeps it safe when
                            several instances share a database.

Limits (see ADR 006): the queue is in-process, so a hard crash loses in-flight
jobs (recovered as INTERRUPTED) and limits are per process, not global. To scale
out, persist uploads to object storage and run `extraction_pipeline.run` from a
separate worker; `enqueue()` is the only call site that would change.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from prisma.fields import Json
from prisma.models import Workspace

from app.core.config import get_settings
from app.core.db import db
from app.services import ai_access, extraction_pipeline, failures

logger = logging.getLogger("app.services.extraction_queue")

# Strong references: the event loop only keeps weak ones, so an unreferenced
# task can be garbage-collected mid-flight.
_tasks: set[asyncio.Task[None]] = set()
# A Semaphore binds to the event loop it is first contended on, so keep one per loop.
_semaphore: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None


class QueueFullError(Exception):
    """Raised by `ensure_capacity()` when the backlog limit is reached."""


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    loop = asyncio.get_running_loop()
    if _semaphore is None or _semaphore[0] is not loop:
        _semaphore = (loop, asyncio.Semaphore(get_settings().EXTRACTION_MAX_CONCURRENCY))
    return _semaphore[1]


def ensure_capacity() -> None:
    """Call *before* creating a DocumentLog so a rejected request leaves no row behind."""
    if len(_tasks) >= get_settings().EXTRACTION_MAX_BACKLOG:
        raise QueueFullError


def enqueue(
    *,
    doc_log_id: str,
    workspace: Workspace,
    raw_text: str | None,
    file_bytes: bytes | None,
    mime_type: str | None,
    template_id: str | None,
) -> None:
    """
    Schedule the pipeline for an existing PENDING DocumentLog.

    Which Gemini key the job runs on (own key / platform fallback / trial credit) is
    resolved in `_run` via `ai_access.acquire`, so every ingestion path (dashboard,
    API key, inbound adapters) routes keys identically.
    """
    job = {
        "doc_log_id": doc_log_id,
        "workspace_id": workspace.id,
        "raw_text": raw_text,
        "file_bytes": file_bytes,
        "mime_type": mime_type,
        "target_template_id": template_id,
    }
    task = asyncio.create_task(_run(job, workspace), name=f"extraction:{doc_log_id}")
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _run(job: dict, workspace: Workspace) -> None:
    doc_log_id: str = job["doc_log_id"]
    timeout = get_settings().EXTRACTION_JOB_TIMEOUT_SECONDS
    access: ai_access.AiAccess | None = None
    failed = True  # until the pipeline reports otherwise; decides whether a trial credit is refunded
    try:
        access = await ai_access.acquire(workspace)
        async with _get_semaphore():
            result = await asyncio.wait_for(
                extraction_pipeline.run(
                    **job,
                    custom_api_key=access.custom_api_key,
                    allow_platform_fallback=access.allow_platform_fallback,
                ),
                timeout=timeout,
            )
        failed = access.trial_credit_held and result.status == "FAILED"
    except asyncio.TimeoutError:
        logger.error("[%s] Extraction exceeded %ds — failing", doc_log_id, timeout)
        await extraction_pipeline.fail_document(doc_log_id, failures.failure(failures.FailureCode.TIMEOUT))
    except asyncio.CancelledError:
        # Server shutting down. Record why, then let cancellation continue.
        await extraction_pipeline.fail_document(doc_log_id, failures.failure(failures.FailureCode.INTERRUPTED))
        raise
    except Exception as exc:  # noqa: BLE001 — pipeline.run handles its own errors; this is the last resort
        logger.exception("[%s] Unhandled extraction error: %s", doc_log_id, exc)
        await extraction_pipeline.fail_document(doc_log_id, failures.classify(exc))
    finally:
        if access and access.trial_credit_held and failed:
            await ai_access.refund_trial_credit(workspace.id)


async def wait_idle() -> None:
    """Wait for all queued/running jobs to finish. Used by tests and graceful shutdown."""
    while _tasks:
        await asyncio.gather(*list(_tasks), return_exceptions=True)


async def shutdown(grace_seconds: float = 20.0) -> None:
    """Give in-flight jobs `grace_seconds` to finish, then cancel the rest."""
    if not _tasks:
        return
    logger.info("Waiting up to %.0fs for %d extraction job(s)", grace_seconds, len(_tasks))
    _, pending = await asyncio.wait(list(_tasks), timeout=grace_seconds)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def recover_orphans() -> int:
    """
    Fail documents left PENDING/PROCESSING by a process that died.

    Only rows older than the job timeout (plus slack) are touched: any live job
    on this or another instance finishes or times out well within that window.
    Returns the number of rows recovered.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(
        seconds=get_settings().EXTRACTION_JOB_TIMEOUT_SECONDS + 60
    )
    recovered = await db.documentlog.update_many(
        where={"status": {"in": ["PENDING", "PROCESSING"]}, "createdAt": {"lt": cutoff}},  # type: ignore[arg-type]
        data={
            "status": "FAILED",
            "validationErrors": Json(failures.failure(failures.FailureCode.INTERRUPTED).to_json()),  # type: ignore[arg-type]
            "progress": Json(None),  # type: ignore[arg-type]
        },
    )
    if recovered:
        logger.warning("Recovered %d interrupted extraction(s) left in flight", recovered)
    return recovered
