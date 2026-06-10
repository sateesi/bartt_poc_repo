"""SQL Safety Guardrail.

Blocks any agent-generated SQL.  The agent may ONLY invoke approved action
groups (``read_holding_tank``, ``lookup_reference``, ``write_normalized_trade``).
Direct SQL of any kind — SELECT, INSERT, UPDATE, DELETE, DROP, etc. — is
forbidden.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


class SqlSafetyError(Exception):
    """Raised when SQL content is detected in agent output."""


# Regex patterns for common SQL statements (case-insensitive, multi-line)
_SQL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\b(SELECT)\s+.+\s+FROM\s+", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(INSERT)\s+INTO\s+", re.IGNORECASE),
    re.compile(r"\b(UPDATE)\s+\S+\s+SET\s+", re.IGNORECASE),
    re.compile(r"\b(DELETE)\s+FROM\s+", re.IGNORECASE),
    re.compile(r"\b(DROP)\s+(TABLE|DATABASE|INDEX|VIEW)\s+", re.IGNORECASE),
    re.compile(r"\b(ALTER)\s+(TABLE|DATABASE)\s+", re.IGNORECASE),
    re.compile(r"\b(TRUNCATE)\s+(TABLE\s+)?\S+", re.IGNORECASE),
    re.compile(r"\b(CREATE)\s+(TABLE|DATABASE|INDEX|VIEW)\s+", re.IGNORECASE),
    re.compile(r"\b(EXEC|EXECUTE)\s+", re.IGNORECASE),
    re.compile(r"\b(MERGE)\s+INTO\s+", re.IGNORECASE),
]


def detect_sql_in_text(text: str) -> bool:
    """Return True if the text contains SQL-like statements.

    This scanner is intentionally aggressive — false positives are
    acceptable because the agent should never produce SQL.
    """
    for pattern in _SQL_PATTERNS:
        if pattern.search(text):
            logger.warning("SQL detected in text: pattern=%s", pattern.pattern)
            return True
    return False


def assert_no_sql(text: str) -> None:
    """Raise ``SqlSafetyError`` if ``text`` contains SQL statements."""
    if detect_sql_in_text(text):
        raise SqlSafetyError(
            "Agent output contains SQL.  The agent is not permitted to "
            "generate SQL statements.  Use approved action groups only."
        )
