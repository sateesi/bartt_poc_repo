"""Unit tests for services/knowledge_base_service.py.

All AWS API calls are mocked — no real Bedrock or S3 access required.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_retrieval_result(text: str, uri: str, score: float) -> dict[str, Any]:
    return {
        "content": {"text": text},
        "score": score,
        "location": {
            "type": "S3",
            "s3Location": {"uri": f"s3://bartt-bucket/{uri}"},
        },
    }


MOCK_RESPONSE_TWO_RESULTS: dict[str, Any] = {
    "retrievalResults": [
        _make_retrieval_result(
            "BARTT processes clearing broker trade tieouts.",
            "blda_exchange_xref.json",
            0.91,
        ),
        _make_retrieval_result(
            "The clearing broker code cross-reference maps broker codes.",
            "blda_curr_xref.json",
            0.78,
        ),
    ]
}

MOCK_RESPONSE_EMPTY: dict[str, Any] = {"retrievalResults": []}

MOCK_RESPONSE_LOW_SCORE: dict[str, Any] = {
    "retrievalResults": [
        _make_retrieval_result("Irrelevant document.", "noise.txt", 0.10),
    ]
}


# ---------------------------------------------------------------------------
# Tests — successful retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_success_returns_chunks_sources_metadata() -> None:
    """Happy path: two results above threshold → both returned."""
    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            return_value=MOCK_RESPONSE_TWO_RESULTS,
        ),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("test query")

    assert len(result["chunks"]) == 2
    assert "blda_exchange_xref.json" in result["sources"]
    assert "blda_curr_xref.json" in result["sources"]
    assert len(result["metadata"]) == 2
    assert result["metadata"][0]["score"] == 0.91


@pytest.mark.asyncio
async def test_retrieve_context_deduplicates_sources() -> None:
    """Same source document referenced by two chunks → deduplicated."""
    duplicate_response: dict[str, Any] = {
        "retrievalResults": [
            _make_retrieval_result("Chunk A from same doc.", "blda_exchange_xref.json", 0.9),
            _make_retrieval_result("Chunk B from same doc.", "blda_exchange_xref.json", 0.85),
        ]
    }
    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            return_value=duplicate_response,
        ),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("test query")

    assert result["sources"].count("blda_exchange_xref.json") == 1
    assert len(result["chunks"]) == 2  # chunks are NOT deduplicated


# ---------------------------------------------------------------------------
# Tests — empty retrieval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_empty_response_returns_empty_lists() -> None:
    """KB returns no results → empty chunks/sources/metadata."""
    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            return_value=MOCK_RESPONSE_EMPTY,
        ),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("unknown query")

    assert result["chunks"] == []
    assert result["sources"] == []
    assert result["metadata"] == []


# ---------------------------------------------------------------------------
# Tests — score filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_filters_low_score_chunks() -> None:
    """Chunk with score below MIN_RETRIEVAL_SCORE is excluded."""
    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch("services.knowledge_base_service.MIN_RETRIEVAL_SCORE", 0.5),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            return_value=MOCK_RESPONSE_LOW_SCORE,
        ),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("irrelevant query")

    assert result["chunks"] == []


@pytest.mark.asyncio
async def test_retrieve_context_no_score_field_passes_filter() -> None:
    """Chunks without a score field are kept (score=None is acceptable)."""
    response_no_score: dict[str, Any] = {
        "retrievalResults": [
            {
                "content": {"text": "Document without score."},
                "location": {"type": "S3", "s3Location": {"uri": "s3://bucket/doc.pdf"}},
                # no "score" key
            }
        ]
    }
    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            return_value=response_no_score,
        ),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("some query")

    assert len(result["chunks"]) == 1


# ---------------------------------------------------------------------------
# Tests — missing KB ID
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_raises_on_missing_kb_id() -> None:
    """ValueError raised immediately when KNOWLEDGE_BASE_ID is empty."""
    with patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", ""):
        from services import knowledge_base_service

        with pytest.raises(ValueError, match="KNOWLEDGE_BASE_ID"):
            await knowledge_base_service.retrieve_context("query")


# ---------------------------------------------------------------------------
# Tests — API failure & retry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_context_raises_runtime_error_after_retries() -> None:
    """RuntimeError raised after all retry attempts are exhausted."""
    from botocore.exceptions import ClientError

    boto_err = ClientError(
        {"Error": {"Code": "ServiceUnavailableException", "Message": "Service down"}},
        "Retrieve",
    )

    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch("services.knowledge_base_service.KB_MAX_RETRIES", 2),
        patch("services.knowledge_base_service.KB_RETRY_BASE_DELAY_S", 0.0),
        patch(
            "services.knowledge_base_service._retrieve_sync",
            side_effect=boto_err,
        ),
    ):
        from services import knowledge_base_service

        with pytest.raises(RuntimeError, match="failed after"):
            await knowledge_base_service.retrieve_context("query")


@pytest.mark.asyncio
async def test_retrieve_context_succeeds_after_transient_failure() -> None:
    """Succeeds on second attempt when first attempt raises."""
    from botocore.exceptions import ClientError

    boto_err = ClientError(
        {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
        "Retrieve",
    )
    call_count = 0

    def side_effect(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise boto_err
        return MOCK_RESPONSE_TWO_RESULTS

    with (
        patch("services.knowledge_base_service.KNOWLEDGE_BASE_ID", "test-kb-123"),
        patch("services.knowledge_base_service.KB_MAX_RETRIES", 3),
        patch("services.knowledge_base_service.KB_RETRY_BASE_DELAY_S", 0.0),
        patch("services.knowledge_base_service._retrieve_sync", side_effect=side_effect),
    ):
        from services import knowledge_base_service

        result = await knowledge_base_service.retrieve_context("query")

    assert len(result["chunks"]) == 2
    assert call_count == 2


# ---------------------------------------------------------------------------
# Tests — source name extraction
# ---------------------------------------------------------------------------


def test_extract_source_name_from_s3_uri() -> None:
    """File name is extracted from S3 URI."""
    from services.knowledge_base_service import _extract_source_name

    loc = {"s3Location": {"uri": "s3://my-bucket/path/to/blda_exchange_xref.json"}}
    assert _extract_source_name(loc) == "blda_exchange_xref.json"


def test_extract_source_name_fallback_to_type() -> None:
    """Falls back to location type when S3 URI is absent."""
    from services.knowledge_base_service import _extract_source_name

    loc = {"type": "CONFLUENCE"}
    assert _extract_source_name(loc) == "CONFLUENCE"


def test_extract_source_name_unknown_fallback() -> None:
    """Returns 'unknown' when location is empty."""
    from services.knowledge_base_service import _extract_source_name

    assert _extract_source_name({}) == "unknown"
