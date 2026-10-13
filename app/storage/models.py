"""
app/storage/models.py — SQLAlchemy 2.0 ORM models for the quantai_app schema.
All metadata, history, catalog, approved examples, and exports live here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.mysql import LONGTEXT, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.storage.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class Source(Base):
    """A connected data source (MySQL table group, uploaded file, or REST API)."""
    __tablename__ = "sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # mysql|csv|excel|api
    schema_name: Mapped[Optional[str]] = mapped_column(String(128))
    table_name: Mapped[Optional[str]] = mapped_column(String(128))
    file_path: Mapped[Optional[str]] = mapped_column(String(512))
    api_url: Mapped[Optional[str]] = mapped_column(String(1024))
    api_config: Mapped[Optional[dict]] = mapped_column(JSON)
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    col_count: Mapped[Optional[int]] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    catalog_entries: Mapped[list["ColumnCatalog"]] = relationship(back_populates="source", cascade="all, delete-orphan")
    sessions: Mapped[list["ChatSession"]] = relationship(back_populates="source")
    approved_examples: Mapped[list["ApprovedExample"]] = relationship(back_populates="source", cascade="all, delete-orphan")


class ColumnCatalog(Base):
    """Per-column metadata profile for a source (wide-table support)."""
    __tablename__ = "column_catalog"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    original_name: Mapped[str] = mapped_column(String(256), nullable=False)
    safe_name: Mapped[str] = mapped_column(String(64), nullable=False)
    col_type: Mapped[str] = mapped_column(String(32))  # int|float|str|date|datetime|bool
    mysql_type: Mapped[Optional[str]] = mapped_column(String(64))
    null_pct: Mapped[Optional[float]] = mapped_column(Float)
    distinct_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    col_min: Mapped[Optional[str]] = mapped_column(String(256))
    col_max: Mapped[Optional[str]] = mapped_column(String(256))
    top_values: Mapped[Optional[list]] = mapped_column(JSON)  # top 5 for low-cardinality
    description: Mapped[Optional[str]] = mapped_column(Text)  # user-written or auto-drafted
    unit: Mapped[Optional[str]] = mapped_column(String(64))
    synonyms: Mapped[Optional[list]] = mapped_column(JSON)
    is_date_col: Mapped[bool] = mapped_column(Boolean, default=False)
    is_key_col: Mapped[bool] = mapped_column(Boolean, default=False)
    is_pii: Mapped[bool] = mapped_column(Boolean, default=False)
    embedding_path: Mapped[Optional[str]] = mapped_column(String(512))
    ordinal_position: Mapped[int] = mapped_column(Integer, default=0)

    source: Mapped["Source"] = relationship(back_populates="catalog_entries")

    __table_args__ = (
        UniqueConstraint("source_id", "safe_name", name="uq_catalog_source_col"),
    )


class ChatSession(Base):
    """A conversation session."""
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sources.id"))
    title: Mapped[Optional[str]] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    source: Mapped[Optional["Source"]] = relationship(back_populates="sessions")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", cascade="all, delete-orphan")


class Message(Base):
    """A single user or assistant message in a session."""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(16))  # user|assistant
    content: Mapped[str] = mapped_column(LONGTEXT)
    run_id: Mapped[Optional[str]] = mapped_column(String(36))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class QueryRun(Base):
    """Full record of a query execution — question, plan, SQL, result metadata."""
    __tablename__ = "query_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("chat_sessions.id"))
    source_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("sources.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[Optional[dict]] = mapped_column(JSON)
    generated_sql: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|success|error|ambiguous
    confidence: Mapped[Optional[str]] = mapped_column(String(16))  # High|Medium|Low
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    resolved_date_range: Mapped[Optional[str]] = mapped_column(String(128))
    columns_used: Mapped[Optional[list]] = mapped_column(JSON)
    interpretation_text: Mapped[Optional[str]] = mapped_column(Text)
    insight_text: Mapped[Optional[str]] = mapped_column(Text)
    timing_ms: Mapped[Optional[dict]] = mapped_column(JSON)
    feedback: Mapped[Optional[int]] = mapped_column(Integer)  # 1=up, -1=down
    is_fallback_sql: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ApprovedExample(Base):
    """User-approved question → plan pairs used as few-shot examples."""
    __tablename__ = "approved_examples"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    source_id: Mapped[str] = mapped_column(String(36), ForeignKey("sources.id", ondelete="CASCADE"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    plan_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    embedding_blob: Mapped[Optional[bytes]] = mapped_column(MEDIUMBLOB)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    source: Mapped["Source"] = relationship(back_populates="approved_examples")


class Export(Base):
    """Record of a generated export file."""
    __tablename__ = "exports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(String(36), ForeignKey("query_runs.id", ondelete="CASCADE"))
    format: Mapped[str] = mapped_column(String(16))  # csv|xlsx|pdf|html|png|svg|json|zip
    file_path: Mapped[str] = mapped_column(String(512))
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime)


class Settings(Base):
    """Key-value app settings stored in DB (overrides .env for runtime)."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
