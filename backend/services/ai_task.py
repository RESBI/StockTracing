"""Persistent AI task queue backed by SQLite.

Replaces the in-memory _ai_queue list in CacheUpdater so that:
- tasks survive restarts
- failures are retried (up to max_attempts)
- progress is observable via API
"""
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_

from backend.database.deps import db_session
from backend.database.models import AITask
from backend.utils.logger import logger

MAX_ATTEMPTS = 3


def enqueue(symbol: str) -> None:
    """Add a symbol to the queue if not already pending/running."""
    sym = symbol.upper().strip()
    with db_session() as db:
        existing = db.query(AITask).filter(
            AITask.symbol == sym,
            AITask.status.in_(("pending", "running")),
        ).first()
        if existing:
            return
        db.add(AITask(symbol=sym, status="pending", max_attempts=MAX_ATTEMPTS))
        db.commit()
    logger.info("AI task enqueued: %s", sym)


def claim_next() -> AITask | None:
    """Atomically claim the next pending task (set to running)."""
    with db_session() as db:
        task = db.query(AITask).filter(
            AITask.status == "pending"
        ).order_by(AITask.created_at.asc()).first()
        if not task:
            return None
        task.status = "running"
        task.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(task)
        db.expunge(task)
        return task


def mark_done(task_id: int) -> None:
    with db_session() as db:
        task = db.query(AITask).filter(AITask.id == task_id).first()
        if task:
            task.status = "done"
            task.updated_at = datetime.now(timezone.utc)
            db.commit()


def mark_failed(task_id: int, error: str) -> None:
    """Increment attempts; requeue if under max, else mark failed."""
    with db_session() as db:
        task = db.query(AITask).filter(AITask.id == task_id).first()
        if not task:
            return
        task.attempts += 1
        task.last_error = (error or "")[:500]
        task.updated_at = datetime.now(timezone.utc)
        if task.attempts < task.max_attempts:
            task.status = "pending"
            logger.warning("AI task %s failed (attempt %s/%s), requeued: %s",
                           task.symbol, task.attempts, task.max_attempts, error)
        else:
            task.status = "failed"
            logger.warning("AI task %s permanently failed after %s attempts: %s",
                           task.symbol, task.attempts, error)
        db.commit()


def queue_status() -> dict[str, Any]:
    """Snapshot for /api/ai/queue observability."""
    with db_session() as db:
        from sqlalchemy import func
        rows = db.query(AITask.status, func.count(AITask.id)).group_by(AITask.status).all()
        counts = {status: cnt for status, cnt in rows}
        pending_symbols = [r.symbol for r in db.query(AITask.symbol).filter(
            AITask.status.in_(("pending", "running"))
        ).order_by(AITask.created_at.asc()).limit(50).all()]
    return {
        "counts": counts,
        "pending_symbols": pending_symbols,
    }
