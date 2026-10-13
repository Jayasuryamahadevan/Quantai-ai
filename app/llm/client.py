"""
app/llm/client.py — ChatOllama client with health check and fallback logic.

Rules:
  - Only one LLM call runs at a time (enforced by caller via async)
  - temperature=0 for SQL, 0.2 for insight
  - Falls back to smaller model on timeout or memory error
  - Health check verifies Ollama is reachable and model is available
  - Never logs user data or full prompts at INFO level
"""
from __future__ import annotations

import asyncio
import logging
import time
from functools import lru_cache
from typing import AsyncIterator, Optional

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_ollama import ChatOllama

from app.config import get_settings

log = logging.getLogger(__name__)

# Global semaphore: one LLM call at a time
_LLM_SEMAPHORE = asyncio.Semaphore(1)


class OllamaHealthError(RuntimeError):
    """Raised when Ollama is not reachable or model is missing."""
    pass


async def health_check() -> dict:
    """
    Verify Ollama is running and the configured model is available.
    Returns a dict with status, available models, and any error message.
    Prints a clear fix message if something is wrong.
    """
    cfg = get_settings()
    result = {
        "ollama_reachable": False,
        "model_available": False,
        "embed_model_available": False,
        "model": cfg.llm_model,
        "embed_model": cfg.llm_embed_model,
        "error": None,
        "available_models": [],
        "fix": None,
    }

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{cfg.ollama_base_url}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            result["ollama_reachable"] = True
            result["available_models"] = models

            result["model_available"] = any(
                cfg.llm_model in m or m.startswith(cfg.llm_model.split(":")[0])
                for m in models
            )
            result["embed_model_available"] = any(
                cfg.llm_embed_model in m for m in models
            )

            if not result["model_available"]:
                result["error"] = f"Model '{cfg.llm_model}' not found in Ollama."
                result["fix"] = (
                    f"Run:  ollama pull {cfg.llm_model}\n"
                    f"Or set LLM_MODEL to one of: {models[:5]}"
                )
                log.warning("LLM model '%s' not available. Available: %s", cfg.llm_model, models)

            if not result["embed_model_available"]:
                result.setdefault("fix", "")
                result["fix"] = (result["fix"] or "") + (
                    f"\nEmbedding model '{cfg.llm_embed_model}' not found.\n"
                    f"Run:  ollama pull {cfg.llm_embed_model}"
                )

    except httpx.ConnectError:
        result["error"] = "Ollama is not running."
        result["fix"] = (
            "Start Ollama with:  ollama serve\n"
            "Then ensure your model is pulled:\n"
            f"  ollama pull {cfg.llm_model}\n"
            f"  ollama pull {cfg.llm_embed_model}"
        )
        log.error("Cannot connect to Ollama at %s", cfg.ollama_base_url)
    except Exception as exc:
        result["error"] = str(exc)
        log.exception("Unexpected error checking Ollama health")

    return result


def _build_client(model: str, temperature: float) -> ChatOllama:
    cfg = get_settings()
    return ChatOllama(
        model=model,
        base_url=cfg.ollama_base_url,
        temperature=temperature,
        num_ctx=cfg.llm_num_ctx,
        client_kwargs={"timeout": cfg.llm_timeout_sec},
    )


async def call_llm(
    system_prompt: str,
    user_message: str,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
    format: Optional[dict] = None,  # JSON schema for structured output
) -> str:
    """
    Call the LLM with a system + user message.
    Enforces single-call semaphore. Falls back to smaller model on error.
    
    Args:
        system_prompt: System instructions (never include user data at INFO log level).
        user_message: The user / data portion of the prompt.
        temperature: Override; defaults to cfg.llm_temperature_sql.
        model: Override model name.
        format: Optional JSON schema dict for structured output (Ollama format param).
    
    Returns:
        The model's text response.
    """
    cfg = get_settings()
    temp = temperature if temperature is not None else cfg.llm_temperature_sql
    model_name = model or cfg.llm_model

    async with _LLM_SEMAPHORE:
        try:
            return await _do_call(system_prompt, user_message, temp, model_name, format)
        except Exception as exc:
            err_str = str(exc).lower()
            is_oom = any(k in err_str for k in ["out of memory", "oom", "cuda", "killed"])
            is_timeout = isinstance(exc, (TimeoutError, httpx.TimeoutException)) or any(
                marker in err_str for marker in ("timeout", "timed out")
            )

            if cfg.llm_auto_fallback and (is_oom or is_timeout) and model_name != cfg.llm_fallback_model:
                log.warning(
                    "LLM call failed (%s), falling back to %s",
                    "OOM" if is_oom else "timeout",
                    cfg.llm_fallback_model,
                )
                return await _do_call(
                    system_prompt, user_message, temp, cfg.llm_fallback_model, format
                )
            raise


async def _do_call(
    system_prompt: str,
    user_message: str,
    temperature: float,
    model_name: str,
    format: Optional[dict],
) -> str:
    cfg = get_settings()
    client_kwargs: dict = dict(
        model=model_name,
        base_url=cfg.ollama_base_url,
        temperature=temperature,
        num_ctx=cfg.llm_num_ctx,
        client_kwargs={"timeout": cfg.llm_timeout_sec},
    )
    if format:
        client_kwargs["format"] = format

    client = ChatOllama(**client_kwargs)
    messages: list[BaseMessage] = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]

    t0 = time.perf_counter()
    log.debug("LLM call: model=%s temp=%.1f ctx=%d", model_name, temperature, cfg.llm_num_ctx)

    response = await client.ainvoke(messages)
    elapsed = time.perf_counter() - t0
    log.debug("LLM response: %.2fs, %d chars", elapsed, len(response.content))

    return str(response.content).strip()


async def stream_llm(
    system_prompt: str,
    user_message: str,
    temperature: Optional[float] = None,
    model: Optional[str] = None,
) -> AsyncIterator[str]:
    """
    Stream LLM tokens for the insight generation phase.
    Yields text chunks as they arrive.
    """
    cfg = get_settings()
    temp = temperature if temperature is not None else cfg.llm_temperature_insight
    model_name = model or cfg.llm_model

    async with _LLM_SEMAPHORE:
        client = ChatOllama(
            model=model_name,
            base_url=cfg.ollama_base_url,
            temperature=temp,
            num_ctx=cfg.llm_num_ctx,
            client_kwargs={"timeout": cfg.llm_timeout_sec},
        )
        messages: list[BaseMessage] = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        async for chunk in client.astream(messages):
            if hasattr(chunk, "content") and chunk.content:
                yield str(chunk.content)


async def embed_text(texts: list[str]) -> list[list[float]]:
    """
    Embed a list of texts using the local embedding model via Ollama.
    Returns a list of embedding vectors.
    """
    cfg = get_settings()
    async with httpx.AsyncClient(timeout=60.0) as client:
        embeddings = []
        for text in texts:
            resp = await client.post(
                f"{cfg.ollama_base_url}/api/embeddings",
                json={"model": cfg.llm_embed_model, "prompt": text},
            )
            resp.raise_for_status()
            embeddings.append(resp.json()["embedding"])
        return embeddings
