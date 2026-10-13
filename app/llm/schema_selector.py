"""
app/llm/schema_selector.py — Embedding-based column selection for wide tables.

For each question, selects the top-K most relevant columns from a 150+ column
schema using:
  1. Embedding cosine similarity (nomic-embed-text via Ollama)
  2. Fuzzy/keyword matching on column names
  3. Always includes: date columns, key/ID columns, explicitly named columns

Embeddings are cached on disk so repeat questions are fast (~<1s).
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    an = np.array(a, dtype=np.float32)
    bn = np.array(b, dtype=np.float32)
    denom = np.linalg.norm(an) * np.linalg.norm(bn)
    if denom == 0:
        return 0.0
    return float(np.dot(an, bn) / denom)


def _col_text(col: dict[str, Any]) -> str:
    """Concatenate column metadata into a text for embedding."""
    parts = [col.get("safe_name", ""), col.get("original_name", "")]
    if col.get("description"):
        parts.append(col["description"])
    if col.get("synonyms"):
        parts.extend(col["synonyms"])
    if col.get("top_values"):
        parts.append(", ".join(str(v) for v in col["top_values"][:5]))
    return " ".join(filter(None, parts))


def _fuzzy_score(question: str, col_name: str) -> float:
    """Return 0-1 fuzzy overlap between question and column name."""
    try:
        from rapidfuzz import fuzz
        q_lower = question.lower()
        col_lower = col_name.lower().replace("_", " ")
        score = fuzz.partial_ratio(q_lower, col_lower) / 100.0
        # Boost exact word match
        words = re.findall(r"\w+", col_lower)
        for w in words:
            if w in q_lower and len(w) > 3:
                score = min(1.0, score + 0.2)
        return score
    except ImportError:
        return 0.0


def _cache_path(source_id: str) -> Path:
    cfg = get_settings()
    return cfg.embedding_cache_dir / f"{source_id}_cols.json"


def _load_cache(source_id: str) -> dict[str, Any] | None:
    p = _cache_path(source_id)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def _save_cache(source_id: str, data: dict[str, Any]) -> None:
    p = _cache_path(source_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, default=str), encoding="utf-8")


def _schema_hash(columns: list[dict]) -> str:
    """Hash of column safe_names to detect schema changes."""
    names = sorted(c.get("safe_name", "") for c in columns)
    return hashlib.md5(json.dumps(names).encode()).hexdigest()[:12]


async def build_column_embeddings(
    source_id: str,
    columns: list[dict[str, Any]],
    force: bool = False,
) -> dict[str, list[float]]:
    """
    Build and cache embeddings for all columns in a source.
    Returns dict: safe_name -> embedding vector.
    Only re-embeds when schema changes (detected by hash).
    """
    from app.llm.client import embed_text

    schema_hash = _schema_hash(columns)
    cache = _load_cache(source_id)

    if not force and cache and cache.get("schema_hash") == schema_hash:
        log.debug("Column embeddings cache hit for source %s (%d cols)", source_id, len(cache["embeddings"]))
        return cache["embeddings"]

    log.info("Building column embeddings for source %s (%d columns)...", source_id, len(columns))
    texts = [_col_text(c) for c in columns]
    embeddings_list = await embed_text(texts)

    embeddings: dict[str, list[float]] = {}
    for col, emb in zip(columns, embeddings_list):
        embeddings[col["safe_name"]] = emb

    _save_cache(source_id, {"schema_hash": schema_hash, "embeddings": embeddings})
    log.info("Column embeddings built and cached for %s", source_id)
    return embeddings


async def select_columns(
    question: str,
    columns: list[dict[str, Any]],
    source_id: str,
    top_k: int | None = None,
    always_include: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Select the top-K most relevant columns for a question.

    Always includes:
      - Columns with is_date_col=True
      - Columns with is_key_col=True
      - Columns explicitly named in the question (by original or safe name)
      - Any columns in always_include list

    Args:
        question: The user's question.
        columns: Full list of column catalog dicts.
        source_id: Used for embedding cache lookup.
        top_k: Max columns to return (default from config).
        always_include: Additional safe_names to always include.

    Returns:
        Subset of columns, ordered by relevance.
    """
    cfg = get_settings()
    k = top_k or cfg.column_selector_top_k
    always = set(always_include or [])

    # Always-include: date and key columns
    forced = []
    scoreable = []
    q_lower = question.lower()

    for col in columns:
        sname = col.get("safe_name", "")
        oname = col.get("original_name", "").lower()
        is_forced = (
            col.get("is_date_col", False)
            or col.get("is_key_col", False)
            or sname in always
            or sname.lower() in q_lower
            or oname in q_lower
        )
        if is_forced:
            forced.append(col)
        else:
            scoreable.append(col)

    if len(forced) >= k:
        return forced[:k]

    remaining_k = k - len(forced)

    # Try embedding-based selection
    try:
        from app.llm.client import embed_text
        col_embeddings = await build_column_embeddings(source_id, columns)
        q_emb = (await embed_text([question]))[0]

        scored = []
        for col in scoreable:
            sname = col.get("safe_name", "")
            col_emb = col_embeddings.get(sname, [])
            if col_emb:
                sim = _cosine_similarity(q_emb, col_emb)
            else:
                sim = 0.0
            fuzz = _fuzzy_score(question, sname)
            # Combined score: 70% embedding, 30% fuzzy
            score = 0.7 * sim + 0.3 * fuzz
            scored.append((score, col))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = forced + [c for _, c in scored[:remaining_k]]

    except Exception as exc:
        log.warning("Embedding-based selection failed (%s), using fuzzy only", exc)
        scored = [(( _fuzzy_score(question, c.get("safe_name", ""))), c) for c in scoreable]
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = forced + [c for _, c in scored[:remaining_k]]

    log.debug(
        "Column selector: %d/%d columns selected for '%s...'",
        len(selected), len(columns), question[:50],
    )
    return selected


def check_missing_columns(
    selected_names: set[str],
    sql: str,
    all_columns: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    After SQL generation, check if the model used columns not in the selection.
    Returns list of catalog entries for any extra real columns it used.
    """
    all_safe = {c["safe_name"]: c for c in all_columns}
    extra = []
    for name, col in all_safe.items():
        if name not in selected_names and f"`{name}`" in sql:
            extra.append(col)
            log.info("Column selector: model used '%s' which was not pre-selected — expanding", name)
    return extra
