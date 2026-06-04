"""Integration-style unit tests for the invoke() entrypoint in main.py.

These tests mock the Strands Agent and the KB service layer so no real AWS
or LLM calls are made.  The goal is to verify the RAG orchestration logic:
    retrieve → build prompt → stream model → yield sources.
"""
from __future__ import annotations

import sys
import types
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _collect_yields(gen: AsyncGenerator[Any, None]) -> list[str]:
    """Drain an async generator and collect all yielded strings."""
    items: list[str] = []
    async for item in gen:
        items.append(item)
    return items


def _make_agent_stream(tokens: list[str]) -> AsyncMock:
    """Return a mock agent whose stream_async yields token events."""

    async def _stream(_prompt: str) -> AsyncGenerator[dict[str, str], None]:
        for tok in tokens:
            yield {"data": tok}

    mock_agent = MagicMock()
    mock_agent.stream_async = _stream
    return mock_agent


def _make_retrieval_results(
    chunks: list[str],
    sources: list[str],
) -> dict[str, Any]:
    return {
        "chunks": chunks,
        "sources": sources,
        "metadata": [{"source": s, "score": 0.9} for s in sources],
    }


# ---------------------------------------------------------------------------
# Tests — full RAG flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_grounded_flow() -> None:
    """Full happy-path: KB returns context, model streams tokens, sources appended."""
    retrieval = _make_retrieval_results(
        chunks=["BARTT matches trades."],
        sources=["blda_exchange_xref.json"],
    )

    mock_agent = _make_agent_stream(["BARTT", " answer."])

    with (
        patch("main.KNOWLEDGE_BASE_ID", "kb-123"),
        patch("main.retrieve_context", new=AsyncMock(return_value=retrieval)),
        patch("main.get_or_create_agent", return_value=mock_agent),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "What is BARTT?"}, object()))

    assert "BARTT" in output
    assert " answer." in output
    # Source attribution must be the last yielded item
    assert output[-1].startswith("\n\nSources:")
    assert "blda_exchange_xref.json" in output[-1]


@pytest.mark.asyncio
async def test_invoke_no_sources_omits_attribution() -> None:
    """When sources list is empty, no Sources block is yielded."""
    retrieval = _make_retrieval_results(chunks=["Some context."], sources=[])

    mock_agent = _make_agent_stream(["Model answer."])

    with (
        patch("main.KNOWLEDGE_BASE_ID", "kb-123"),
        patch("main.retrieve_context", new=AsyncMock(return_value=retrieval)),
        patch("main.get_or_create_agent", return_value=mock_agent),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "question"}, object()))

    assert not any("Sources:" in item for item in output)


# ---------------------------------------------------------------------------
# Tests — empty KB response (strict mode)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_returns_not_found_when_kb_empty() -> None:
    """KB configured + retrieval succeeds with 0 chunks → NOT_FOUND_RESPONSE."""
    empty_retrieval = _make_retrieval_results(chunks=[], sources=[])

    with (
        patch("main.KNOWLEDGE_BASE_ID", "kb-123"),
        patch("main.retrieve_context", new=AsyncMock(return_value=empty_retrieval)),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "Unknown topic"}, object()))

    assert len(output) == 1
    assert "could not find" in output[0].lower()


# ---------------------------------------------------------------------------
# Tests — retrieval failure fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_falls_back_to_model_on_api_failure() -> None:
    """RuntimeError from KB service → model called with original query."""
    mock_agent = _make_agent_stream(["Fallback answer."])

    with (
        patch("main.KNOWLEDGE_BASE_ID", "kb-123"),
        patch(
            "main.retrieve_context",
            new=AsyncMock(side_effect=RuntimeError("Bedrock API unreachable")),
        ),
        patch("main.get_or_create_agent", return_value=mock_agent),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "some query"}, object()))

    assert "Fallback answer." in output
    # No source attribution since retrieval failed
    assert not any("Sources:" in item for item in output)


@pytest.mark.asyncio
async def test_invoke_falls_back_on_value_error() -> None:
    """ValueError (config error) → model called with original query."""
    mock_agent = _make_agent_stream(["Answer from model."])

    with (
        patch("main.KNOWLEDGE_BASE_ID", "kb-123"),
        patch(
            "main.retrieve_context",
            new=AsyncMock(side_effect=ValueError("KNOWLEDGE_BASE_ID not set")),
        ),
        patch("main.get_or_create_agent", return_value=mock_agent),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "query"}, object()))

    assert "Answer from model." in output


# ---------------------------------------------------------------------------
# Tests — no KB ID (strict mode disabled)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_no_kb_id_skips_retrieval() -> None:
    """When KNOWLEDGE_BASE_ID is empty, retrieve_context is never called."""
    mock_agent = _make_agent_stream(["Direct answer."])
    retrieve_mock = AsyncMock()

    with (
        patch("main.KNOWLEDGE_BASE_ID", ""),
        patch("main.retrieve_context", new=retrieve_mock),
        patch("main.get_or_create_agent", return_value=mock_agent),
    ):
        import main

        output = await _collect_yields(main.invoke({"prompt": "question"}, object()))

    retrieve_mock.assert_not_called()
    assert "Direct answer." in output
