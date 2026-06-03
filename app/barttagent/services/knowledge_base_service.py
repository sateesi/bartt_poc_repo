"""Bedrock Knowledge Base retrieval service.

Wraps the synchronous boto3 ``bedrock-agent-runtime`` client in an async
interface using ``run_in_executor`` so it plays nicely with the
``BedrockAgentCoreApp`` async event loop without adding extra dependencies
(aioboto3, anyio, etc.).

Retry / exponential-backoff is applied automatically.  Score-based filtering
keeps only the most relevant chunks before they reach the prompt builder.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from functools import partial
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from config import (
    AWS_REGION,
    KB_MAX_RETRIES,
    KB_RETRY_BASE_DELAY_S,
    KNOWLEDGE_BASE_ID,
    MAX_RETRIEVAL_RESULTS,
    MIN_RETRIEVAL_SCORE,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_client() -> Any:
    """Create a fresh boto3 bedrock-agent-runtime client.

    A new client is created per request rather than being shared globally so
    that thread-pool workers each have their own connection pool.
    """
    return boto3.client("bedrock-agent-runtime", region_name=AWS_REGION)


def _retrieve_sync(query: str, kb_id: str, max_results: int) -> dict[str, Any]:
    """Blocking boto3 call — intended to run inside a thread pool executor."""
    client = _make_client()
    response: dict[str, Any] = client.retrieve(
        knowledgeBaseId=kb_id,
        retrievalQuery={"text": query},
        retrievalConfiguration={
            "vectorSearchConfiguration": {
                "numberOfResults": max_results,
            }
        },
    )
    return response


def _extract_source_name(location: dict[str, Any]) -> str:
    """Return a human-readable document name from a retrieval result location."""
    s3_loc: dict[str, Any] = location.get("s3Location", {})
    uri: str = s3_loc.get("uri", "")
    if uri:
        return uri.rstrip("/").split("/")[-1]
    # Fallback: use location type
    return str(location.get("type", "unknown"))


def _log_struct(msg: str, **fields: Any) -> str:
    """Format a log message with structured JSON fields appended."""
    return f"{msg} {json.dumps(fields, default=str)}"


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def retrieve_context(query: str) -> dict[str, list[Any]]:
    """Retrieve relevant chunks from the configured Bedrock Knowledge Base.

    Args:
        query: The user's natural-language question.

    Returns:
        A dict with keys:
        - ``chunks``  — list of text strings (one per retrieved passage)
        - ``sources`` — deduplicated list of source document names
        - ``metadata``— list of per-chunk metadata dicts

    Raises:
        ValueError:  If ``KNOWLEDGE_BASE_ID`` is not configured.
        RuntimeError: If all retry attempts fail (caller should catch and
                      proceed without grounding).
    """
    if not KNOWLEDGE_BASE_ID:
        raise ValueError(
            "KNOWLEDGE_BASE_ID environment variable is not set. "
            "Configure the Bedrock Knowledge Base ID before starting the agent."
        )

    t_start = time.monotonic()
    raw_response = await _retrieve_with_retry(query)
    retrieval_ms = int((time.monotonic() - t_start) * 1000)

    raw_results: list[dict[str, Any]] = raw_response.get("retrievalResults", [])

    # ------------------------------------------------------------------
    # Score-based filtering
    # ------------------------------------------------------------------
    filtered: list[dict[str, Any]] = [
        r
        for r in raw_results
        # Keep chunk when score is absent (KB doesn't always return it) or
        # when score meets the minimum threshold.
        if r.get("score") is None or float(r.get("score", 0.0)) >= MIN_RETRIEVAL_SCORE
    ]

    chunks: list[str] = []
    sources: list[str] = []
    metadata: list[dict[str, Any]] = []

    for result in filtered:
        text: str = result.get("content", {}).get("text", "")
        location: dict[str, Any] = result.get("location", {})
        score: float | None = result.get("score")

        source_name = _extract_source_name(location)

        chunks.append(text)
        if source_name and source_name not in sources:
            sources.append(source_name)
        metadata.append(
            {
                "source": source_name,
                "score": score,
                "location": location,
            }
        )

    logger.info(
        _log_struct(
            "KB retrieval completed",
            knowledge_base_id=KNOWLEDGE_BASE_ID,
            retrieval_duration_ms=retrieval_ms,
            raw_chunk_count=len(raw_results),
            filtered_chunk_count=len(chunks),
            source_document_count=len(sources),
            min_retrieval_score=MIN_RETRIEVAL_SCORE,
        )
    )

    return {"chunks": chunks, "sources": sources, "metadata": metadata}


async def _retrieve_with_retry(query: str) -> dict[str, Any]:
    """Call ``_retrieve_sync`` in a thread pool with exponential back-off."""
    loop = asyncio.get_running_loop()
    last_exc: Exception = RuntimeError("Retrieval not attempted")

    for attempt in range(KB_MAX_RETRIES):
        try:
            result: dict[str, Any] = await loop.run_in_executor(
                None,
                partial(_retrieve_sync, query, KNOWLEDGE_BASE_ID, MAX_RETRIEVAL_RESULTS),
            )
            return result
        except (ClientError, BotoCoreError, OSError) as exc:
            last_exc = exc
            if attempt < KB_MAX_RETRIES - 1:
                delay = KB_RETRY_BASE_DELAY_S * (2**attempt)
                logger.warning(
                    _log_struct(
                        "KB retrieval attempt failed, retrying",
                        attempt=attempt + 1,
                        max_retries=KB_MAX_RETRIES,
                        retry_delay_s=delay,
                        error=str(exc),
                    )
                )
                await asyncio.sleep(delay)

    raise RuntimeError(
        f"Bedrock Knowledge Base retrieval failed after {KB_MAX_RETRIES} attempts"
    ) from last_exc
