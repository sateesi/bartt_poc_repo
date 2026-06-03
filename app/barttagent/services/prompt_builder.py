"""Prompt construction utilities for the BARTT RAG pipeline.

Responsibilities:
- Merge retrieved chunks into a single, size-bounded context string.
- Build the grounded user-turn message (context + question).
- Format source attribution for the response.
- Expose the canonical "not found" response string.

The *system* prompt (strict grounding instructions) lives in ``main.py``
and is set on the Strands ``Agent`` constructor so it applies to every
invocation automatically.
"""
from __future__ import annotations

from typing import Any

from config import GROUNDING_STRICT_MODE, MAX_CONTEXT_CHARS

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Returned verbatim when the Knowledge Base has no relevant content.
NOT_FOUND_RESPONSE: str = (
    "I could not find this information in the BARTT knowledge base."
)

#: Section separator used between chunks in the context block.
_SECTION_SEPARATOR: str = "\n\n--------------------------------\n\n"


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def build_context(retrieval_results: dict[str, Any]) -> str:
    """Merge retrieved chunks into a single context string.

    Each chunk is prefixed with its source document name so the model can
    reason about provenance.  The combined context is capped at
    ``MAX_CONTEXT_CHARS`` to prevent token explosions; the last chunk is
    truncated with an ellipsis if the limit is reached.

    Args:
        retrieval_results: The dict returned by
            ``knowledge_base_service.retrieve_context``.

    Returns:
        A formatted, size-bounded context string ready for injection into
        the prompt.
    """
    chunks: list[str] = retrieval_results.get("chunks", [])
    metadata: list[dict[str, Any]] = retrieval_results.get("metadata", [])

    sections: list[str] = []
    total_chars = 0

    for i, chunk in enumerate(chunks):
        source: str = metadata[i].get("source", "unknown") if i < len(metadata) else "unknown"
        section = f"Source: {source}\n\n{chunk}"

        available = MAX_CONTEXT_CHARS - total_chars
        if available <= 0:
            break

        if len(section) > available:
            if available > 200:
                section = section[:available] + "...[truncated]"
                sections.append(section)
            break

        sections.append(section)
        total_chars += len(section)

    return _SECTION_SEPARATOR.join(sections)


def build_grounded_prompt(user_query: str, retrieved_context: str) -> str:
    """Build the user-turn message with KB context injected.

    The agent's system prompt already carries the strict grounding
    instructions (see ``BARTT_SYSTEM_PROMPT`` in ``main.py``).  This
    function only formats the *content* of the user message so the model
    sees: system-instructions + "KB Context: … User Question: …".

    Args:
        user_query:        The original question from the user.
        retrieved_context: The formatted context from ``build_context``.

    Returns:
        A user-turn message string containing context and question.
    """
    return (
        f"Knowledge Base Context:\n{retrieved_context}\n\n"
        f"User Question:\n{user_query}"
    )


def format_sources(sources: list[str]) -> str:
    """Format a deduplicated source list for appending to the agent answer.

    Args:
        sources: List of source document names (may contain duplicates).

    Returns:
        A formatted "Sources:" block, or an empty string when ``sources``
        is empty.
    """
    if not sources:
        return ""
    # dict.fromkeys preserves insertion order while deduplicating.
    unique = list(dict.fromkeys(sources))
    bullets = "\n".join(f"- {s}" for s in unique)
    return f"\n\nSources:\n{bullets}"


def is_strict_mode() -> bool:
    """Return whether grounding strict mode is enabled."""
    return GROUNDING_STRICT_MODE
