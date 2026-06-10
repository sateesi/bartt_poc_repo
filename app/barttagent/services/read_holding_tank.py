"""read_holding_tank — Approved action-group tool for reading trade data.

Uses read-only access and only executes predefined parameterised queries.
Validates trade-date inputs and rejects arbitrary SQL.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from strands import tool

from guardrails.input_validation import validate_trade_date
from guardrails.sql_safety import detect_sql_in_text
from guardrails.audit import AuditLogger

logger = logging.getLogger(__name__)
_audit = AuditLogger(source="read_holding_tank")

# ---------------------------------------------------------------------------
# Simulated read-only data store (replace with actual DB connection using
# read-only credentials and parameterised stored procedures in production).
# ---------------------------------------------------------------------------
_HOLDING_TANK: list[dict[str, Any]] = []


def load_holding_tank_data(data: list[dict[str, Any]]) -> None:
    """Load holding-tank data for the tool (call at startup or test setup)."""
    global _HOLDING_TANK
    _HOLDING_TANK = data


@tool
def read_holding_tank(trade_date: str) -> str:
    """Read trades from the holding tank for a specific date.

    Args:
        trade_date: Trade date in YYYY-MM-DD format.  Must not be a
                    future date.  Arbitrary SQL is rejected.

    Returns:
        JSON array of matching trade records, or a JSON error object.
    """
    # Guard: reject SQL injection in the date parameter
    if detect_sql_in_text(trade_date):
        logger.warning("SQL injection attempt in trade_date: %s", trade_date[:50])
        _audit.log_injection_attempt(trade_date, "SQL_IN_DATE_PARAM")
        return json.dumps({"status": "FAILED", "reason": "INVALID_INPUT", "detail": "SQL detected in date parameter"})

    # Guard: validate date format and range
    date_result = validate_trade_date(trade_date)
    if not date_result["valid"]:
        return json.dumps({"status": "FAILED", "reason": date_result["reason"], "detail": date_result.get("detail", "")})

    # Execute predefined parameterised query (simulated)
    target_date = str(date_result["date"])
    matching = [t for t in _HOLDING_TANK if t.get("tradeDate") == target_date]

    logger.info("read_holding_tank: date=%s found=%d records", target_date, len(matching))
    return json.dumps({"status": "OK", "tradeDate": target_date, "count": len(matching), "trades": matching}, default=str)
