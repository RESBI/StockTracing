"""Pytest fixtures for StockTracing.

Uses an in-memory SQLite to avoid touching the real database, and a mock
YFinance provider stub for services that import yfinance lazily.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session", autouse=True)
def _isolated_data_dir(tmp_path_factory):
    """Redirect DATA_DIR to a temp dir so tests never touch real data."""
    tmp = tmp_path_factory.mktemp("st_data")
    os.environ["ST_TEST_DATA_DIR"] = str(tmp)
    from backend import config as cfg
    cfg.DATA_DIR = tmp
    cfg.CONFIG_FILE = tmp / "config.json"
    cfg.WATCHLIST_FILE = tmp / "watchlist.json"
    import backend.database.models as models
    models.DATABASE_URL = f"sqlite:///{tmp / 'test.db'}"
    models.engine.dispose()
    import sqlalchemy as sa
    models.engine = sa.create_engine(models.DATABASE_URL, connect_args={"check_same_thread": False})
    models.SessionLocal.configure(bind=models.engine)
    models.Base.metadata.create_all(bind=models.engine)
    yield tmp


@pytest.fixture
def db_session():
    """Yield a fresh SQLAlchemy session that rolls back after each test."""
    from backend.database.models import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
