"""write_normalized_trade — Approved action-group tool for writing normalised trades.

Uses stored procedures only.  Never executes dynamic SQL.  Validates all
fields through the write_validation guardrail and attaches confidence scores
before persisting.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from strands import tool

from guardrails.write_validation import validate_normalized_trade
from guardrails.confidence import compute_confidence, ConfidenceDecision
from guardrails.reference_data import validate_reference_lookup
from guardrails.sql_safety import detect_sql_in_text
from guardrails.audit import AuditLogger

logger = logging.getLogger(__name__)
_audit = AuditLogger(source="write_normalized_trade")

# ---------------------------------------------------------------------------
# Simulated write target (replace with stored-procedure calls in production)
# ---------------------------------------------------------------------------
_WRITTEN_TRADES: list[dict[str, Any]] = []


def get_written_trades() -> list[dict[str, Any]]:
    """Return all written trades (for testing / inspection)."""
    return list(_WRITTEN_TRADES)


def clear_written_trades() -> None:
    """Clear all written trades (for test teardown)."""
    _WRITTEN_TRADES.clear()


@tool
def write_normalized_trade(payload: str) -> str:
    """Write a normalised trade to the target table via stored procedure.

    Args:
        payload: JSON string containing the normalised trade fields:
                 tradeId, currency, exchange, barttCode, tradeDate,
                 lotSizeKey (optional).

    Returns:
        JSON result with status, confidence, and decision.
    """
    # Parse payload
    try:
        data: dict[str, Any] = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return json.dumps({"status": "FAILED", "reason": "INVALID_PAYLOAD", "detail": "Payload is not valid JSON"})

    # Guard: scan all string values for SQL
    for key, value in data.items():
        if isinstance(value, str) and detect_sql_in_text(value):
            logger.warning("SQL detected in field %s of write payload", key)
            _audit.log_injection_attempt(f"{key}={value[:100]}", "SQL_IN_WRITE_FIELD")
            return json.dumps({"status": "FAILED", "reason": "SQL_DETECTED", "detail": f"SQL found in field '{key}'"})

    # Guard: validate all fields
    validation = validate_normalized_trade(data)
    if not validation["valid"]:
        trade_id = data.get("tradeId", "UNKNOWN")
        _audit.log_failure(
            trade_id=str(trade_id),
            input_code=json.dumps(data, default=str)[:200],
            reason=json.dumps(validation["errors"], default=str),
        )
        return json.dumps({"status": "FAILED", "reason": "VALIDATION_ERROR", "errors": validation["errors"]})

    # Compute confidence
    conf = compute_confidence(
        currency_found=validate_reference_lookup("currency", data.get("currency", "")),
        exchange_found=validate_reference_lookup("exchange", data.get("exchange", "")),
        bartt_code_found=validate_reference_lookup("bartt_code", data.get("barttCode", "")),
        lot_size_found=validate_reference_lookup("lot_size", data.get("lotSizeKey", "")) if data.get("lotSizeKey") else True,
    )

    # Decision gate
    if conf.decision == ConfidenceDecision.REJECTED:
        _audit.log_failure(
            trade_id=str(data["tradeId"]),
            input_code=data.get("barttCode", ""),
            reason=f"LOW_CONFIDENCE ({conf.confidence})",
        )
        return json.dumps({
            "status": "REJECTED",
            "reason": "LOW_CONFIDENCE",
            "confidence": conf.confidence,
            "decision": conf.decision.value,
        })

    # Write via stored procedure (simulated)
    record = {**data, "confidence": conf.confidence, "decision": conf.decision.value}
    _WRITTEN_TRADES.append(record)
    logger.info("Trade written: tradeId=%s confidence=%.2f decision=%s", data["tradeId"], conf.confidence, conf.decision.value)

    # Audit success
    _audit.log_success(
        trade_id=str(data["tradeId"]),
        input_code=data.get("barttCode", ""),
        normalized_code=data.get("barttCode", ""),
        confidence=conf.confidence,
        decision=conf.decision.value,
    )

    return json.dumps({
        "status": "OK",
        "tradeId": data["tradeId"],
        "confidence": conf.confidence,
        "decision": conf.decision.value,
    })
