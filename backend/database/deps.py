"""Database session utilities.

Provides:
- get_db: FastAPI dependency yielding a session, closed after request.
- db_session: context manager for use inside services/background threads.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy.orm import Session

from backend.database.models import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency. Usage: `db: Session = Depends(get_db)`."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """Context manager for non-request code (services, background threads).

    Usage:
        with db_session() as db:
            db.query(...).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
