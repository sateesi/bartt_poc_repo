"""Unit tests for services/prompt_builder.py."""
from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_retrieval(chunks: list[str], sources: list[str]) -> dict[str, Any]:
    return {
        "chunks": chunks,
        "sources": sources,
        "metadata": [{"source": s, "score": 0.9} for s in sources],
    }


# ---------------------------------------------------------------------------
# build_context
# ---------------------------------------------------------------------------


def test_build_context_basic() -> None:
    """Each chunk appears with its source header."""
    retrieval = _make_retrieval(
        ["BARTT processes trades.", "Broker codes are defined here."],
        ["trade_doc.pdf", "broker_ref.pdf"],
    )
    from services.prompt_builder import build_context

    ctx = build_context(retrieval)

    assert "Source: trade_doc.pdf" in ctx
    assert "BARTT processes trades." in ctx
    assert "Source: broker_ref.pdf" in ctx
    assert "Broker codes are defined here." in ctx
    # Sections are separated by the dashed separator
    assert "---" in ctx


def test_build_context_empty_retrieval_returns_empty_string() -> None:
    """Empty retrieval → empty string."""
    from services.prompt_builder import build_context

    assert build_context({"chunks": [], "sources": [], "metadata": []}) == ""


def test_build_context_respects_max_chars_limit() -> None:
    """Context is not allowed to exceed MAX_CONTEXT_CHARS."""
    large_chunk = "A" * 5000
    retrieval: dict[str, Any] = {
        "chunks": [large_chunk, large_chunk, large_chunk],
        "sources": ["doc1.pdf", "doc2.pdf", "doc3.pdf"],
        "metadata": [
            {"source": "doc1.pdf", "score": 0.9},
            {"source": "doc2.pdf", "score": 0.88},
            {"source": "doc3.pdf", "score": 0.85},
        ],
    }
    with patch("services.prompt_builder.MAX_CONTEXT_CHARS", 8000):
        from services.prompt_builder import build_context

        ctx = build_context(retrieval)

    assert len(ctx) <= 8000 + len("...[truncated]")


def test_build_context_truncates_with_marker() -> None:
    """A chunk that overflows the limit is truncated with '...[truncated]'."""
    big_chunk = "B" * 4000
    retrieval: dict[str, Any] = {
        "chunks": [big_chunk],
        "sources": ["big_doc.pdf"],
        "metadata": [{"source": "big_doc.pdf", "score": 0.95}],
    }
    with patch("services.prompt_builder.MAX_CONTEXT_CHARS", 500):
        from services.prompt_builder import build_context

        ctx = build_context(retrieval)

    assert ctx.endswith("...[truncated]")


def test_build_context_metadata_fallback_when_shorter() -> None:
    """If metadata list is shorter than chunks list, 'unknown' source is used."""
    retrieval: dict[str, Any] = {
        "chunks": ["Chunk A", "Chunk B"],
        "sources": ["docA.pdf"],
        "metadata": [{"source": "docA.pdf", "score": 0.9}],  # only one entry
    }
    from services.prompt_builder import build_context

    ctx = build_context(retrieval)
    assert "Source: unknown" in ctx


# ---------------------------------------------------------------------------
# build_grounded_prompt
# ---------------------------------------------------------------------------


def test_build_grounded_prompt_includes_both_parts() -> None:
    """Grounded prompt contains context header and user question."""
    from services.prompt_builder import build_grounded_prompt

    prompt = build_grounded_prompt(
        user_query="What is the BARTT tieout process?",
        retrieved_context="BARTT matches clearing broker trades against internal positions.",
    )

    assert "Knowledge Base Context:" in prompt
    assert "BARTT matches clearing broker trades" in prompt
    assert "User Question:" in prompt
    assert "What is the BARTT tieout process?" in prompt


def test_build_grounded_prompt_context_before_question() -> None:
    """Context section appears before the user question in the prompt."""
    from services.prompt_builder import build_grounded_prompt

    prompt = build_grounded_prompt(
        user_query="My question",
        retrieved_context="Context text",
    )
    ctx_pos = prompt.index("Context text")
    q_pos = prompt.index("My question")
    assert ctx_pos < q_pos


# ---------------------------------------------------------------------------
# format_sources
# ---------------------------------------------------------------------------


def test_format_sources_basic() -> None:
    """Non-empty sources list produces bulleted 'Sources:' block."""
    from services.prompt_builder import format_sources

    result = format_sources(["blda_exchange_xref.json", "blda_curr_xref.json"])

    assert "Sources:" in result
    assert "- blda_exchange_xref.json" in result
    assert "- blda_curr_xref.json" in result


def test_format_sources_deduplicates_preserving_order() -> None:
    """Duplicate entries are removed while original insertion order is kept."""
    from services.prompt_builder import format_sources

    result = format_sources(["doc_a.pdf", "doc_b.pdf", "doc_a.pdf", "doc_c.pdf"])

    sources_block = result.split("Sources:")[1]
    # doc_a appears exactly once
    assert sources_block.count("doc_a.pdf") == 1
    # Order: a, b, c
    assert sources_block.index("doc_a.pdf") < sources_block.index("doc_b.pdf")
    assert sources_block.index("doc_b.pdf") < sources_block.index("doc_c.pdf")


def test_format_sources_empty_returns_empty_string() -> None:
    """Empty sources list returns empty string (no Sources section)."""
    from services.prompt_builder import format_sources

    assert format_sources([]) == ""


def test_format_sources_single_entry() -> None:
    """Single source is formatted correctly."""
    from services.prompt_builder import format_sources

    result = format_sources(["only_doc.pdf"])
    assert "- only_doc.pdf" in result


# ---------------------------------------------------------------------------
# NOT_FOUND_RESPONSE constant
# ---------------------------------------------------------------------------


def test_not_found_response_is_non_empty_string() -> None:
    """NOT_FOUND_RESPONSE is a non-empty string."""
    from services.prompt_builder import NOT_FOUND_RESPONSE

    assert isinstance(NOT_FOUND_RESPONSE, str)
    assert len(NOT_FOUND_RESPONSE) > 0


# ---------------------------------------------------------------------------
# is_strict_mode
# ---------------------------------------------------------------------------


def test_is_strict_mode_returns_bool() -> None:
    """is_strict_mode returns a boolean reflecting GROUNDING_STRICT_MODE."""
    with patch("services.prompt_builder.GROUNDING_STRICT_MODE", True):
        from services.prompt_builder import is_strict_mode

        assert is_strict_mode() is True

    with patch("services.prompt_builder.GROUNDING_STRICT_MODE", False):
        assert is_strict_mode() is False
