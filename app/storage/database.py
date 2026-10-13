"""
app/storage/database.py — SQLAlchemy engine and session factories.
Three separate connections for three separate MySQL users.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for quantai_app schema models."""
    pass


def _make_engine(dsn: str, pool_size: int = 5, **kw):
    engine = create_engine(
        dsn,
        pool_size=pool_size,
        pool_pre_ping=True,
        pool_recycle=3600,
        **kw,
    )
    return engine


def _get_engines():
    cfg = get_settings()
    return {
        "readonly": _make_engine(cfg.readonly_dsn, pool_size=10),
        "import_": _make_engine(cfg.import_dsn, pool_size=3),
        "app": _make_engine(cfg.app_dsn, pool_size=5),
    }


# Lazy singletons
_engines: dict | None = None


def engines() -> dict:
    global _engines
    if _engines is None:
        _engines = _get_engines()
    return _engines


def get_readonly_engine():
    return engines()["readonly"]


def get_import_engine():
    return engines()["import_"]


def get_app_engine():
    return engines()["app"]


# Session factories
AppSession = sessionmaker(autocommit=False, autoflush=False)


@contextmanager
def app_session() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy Session on the quantai_app schema."""
    session = AppSession(bind=get_app_engine())
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def readonly_session():
    """Yield a read-only connection on quantai_data."""
    eng = get_readonly_engine()
    with eng.connect() as conn:
        # Force read-only at session level
        conn.execute(text("SET SESSION TRANSACTION READ ONLY"))
        cfg = get_settings()
        conn.execute(
            text(f"SET SESSION MAX_EXECUTION_TIME={cfg.query_timeout_ms}")
        )
        yield conn


@contextmanager
def import_connection():
    """Yield a connection with import privileges on quantai_data."""
    eng = get_import_engine()
    with eng.connect() as conn:
        yield conn
