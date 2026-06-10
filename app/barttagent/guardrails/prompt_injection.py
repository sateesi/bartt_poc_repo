"""Prompt Injection Protection Guardrail.

Detects and rejects requests that attempt:
  - Tool manipulation
  - System prompt disclosure
  - SQL execution via natural language
  - Reference data override via conversational tricks
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class PromptInjectionError(Exception):
    """Raised when a prompt injection attempt is detected."""


# ---------------------------------------------------------------------------
# Detection patterns — ordered by severity
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # System prompt exfiltration
    ("SYSTEM_PROMPT_DISCLOSURE", re.compile(
        r"(show|reveal|print|display|output|repeat|tell me)\s+(your|the)\s+(system\s+prompt|instructions|rules|directives|configuration)",
        re.IGNORECASE,
    )),
    # Instruction override
    ("INSTRUCTION_OVERRIDE", re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above|earlier|your)?\s*(instructions|rules|guidelines|directives|prompts)",
        re.IGNORECASE,
    )),
    # Role hijacking
    ("ROLE_HIJACK", re.compile(
        r"(you\s+are\s+now|act\s+as|pretend\s+to\s+be|switch\s+to|become)\s+(a\s+)?(different|new|unrestricted|admin)",
        re.IGNORECASE,
    )),
    # Direct SQL injection via natural language
    ("SQL_INJECTION", re.compile(
        r"(run|execute|perform)\s+(this\s+)?(SQL|query|statement|command)\s*[:\-]",
        re.IGNORECASE,
    )),
    # Reference data override attempt
    ("REFERENCE_OVERRIDE", re.compile(
        r"(use|set|map|treat|consider|assign)\s+\S+\s+as\s+(a\s+)?(EQUITY|FUTURE|OPTION|SWAP|COMMODITY|BARTT|currency|exchange)",
        re.IGNORECASE,
    )),
    # Tool manipulation
    ("TOOL_MANIPULATION", re.compile(
        r"(call|invoke|use|run)\s+(the\s+)?(write|insert|update|delete|drop)\s+(tool|function|action|procedure)\s+(directly|without|bypassing)",
        re.IGNORECASE,
    )),
    # DAN / jailbreak patterns
    ("JAILBREAK", re.compile(
        r"(DAN|do\s+anything\s+now|developer\s+mode|unrestricted\s+mode|no\s+restrictions)",
        re.IGNORECASE,
    )),
]


def detect_prompt_injection(text: str) -> dict[str, Any]:
    """Scan input text for prompt injection attempts.

    Returns:
        ``{"safe": True}`` if no injection detected, or
        ``{"safe": False, "pattern": "<pattern_name>", "match": "<matched_text>"}``
    """
    if not text:
        return {"safe": True}

    for pattern_name, pattern in _INJECTION_PATTERNS:
        match = pattern.search(text)
        if match:
            logger.warning(
                "Prompt injection detected: pattern=%s match=%s",
                pattern_name,
                match.group()[:100],
            )
            return {
                "safe": False,
                "pattern": pattern_name,
                "match": match.group()[:100],
            }

    return {"safe": True}


def assert_no_injection(text: str) -> None:
    """Raise ``PromptInjectionError`` if injection is detected."""
    result = detect_prompt_injection(text)
    if not result["safe"]:
        raise PromptInjectionError(
            f"Prompt injection blocked: {result['pattern']}"
        )
