"""Audit Logging Guardrail.

Creates structured audit entries for every normalisation action.
Entries are emitted to Python logging (→ CloudWatch when deployed)
and optionally to a callback for database persistence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger("bartt.audit")

# Optional callback for persisting audit entries to a database table
_persist_callback: Callable[[dict[str, Any]], None] | None = None


def set_persist_callback(callback: Callable[[dict[str, Any]], None]) -> None:
    """Register a callback that receives each audit entry dict for DB persistence."""
    global _persist_callback
    _persist_callback = callback


def create_audit_entry(
    trade_id: str,
    input_code: str,
    normalized_code: str | None,
    source: str,
    confidence: float,
    decision: str,
    status: str = "SUCCESS",
    reason: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and emit a structured audit entry.

    Returns the audit entry dict.
    """
    entry: dict[str, Any] = {
        "tradeId": trade_id,
        "inputCode": input_code,
        "normalizedCode": normalized_code,
        "source": source,
        "confidence": confidence,
        "decision": decision,
        "status": status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if reason:
        entry["reason"] = reason
    if extra:
        entry.update(extra)

    # Emit to CloudWatch via structured logging
    logger.info("AUDIT | %s", json.dumps(entry, default=str))

    # Persist to DB if callback registered
    if _persist_callback is not None:
        try:
            _persist_callback(entry)
        except Exception:
            logger.exception("Failed to persist audit entry for tradeId=%s", trade_id)

    return entry


class AuditLogger:
    """Convenience wrapper for creating audit entries within a normalisation flow."""

    def __init__(self, source: str = "bartt_agent"):
        self.source = source

    def log_success(
        self,
        trade_id: str,
        input_code: str,
        normalized_code: str,
        confidence: float,
        decision: str,
    ) -> dict[str, Any]:
        return create_audit_entry(
            trade_id=trade_id,
            input_code=input_code,
            normalized_code=normalized_code,
            source=self.source,
            confidence=confidence,
            decision=decision,
            status="SUCCESS",
        )

    def log_failure(
        self,
        trade_id: str,
        input_code: str,
        reason: str,
    ) -> dict[str, Any]:
        return create_audit_entry(
            trade_id=trade_id,
            input_code=input_code,
            normalized_code=None,
            source=self.source,
            confidence=0.0,
            decision="REJECTED",
            status="FAILED",
            reason=reason,
        )

    def log_injection_attempt(
        self,
        input_text: str,
        pattern_matched: str,
    ) -> dict[str, Any]:
        return create_audit_entry(
            trade_id="N/A",
            input_code=input_text[:200],  # truncate for safety
            normalized_code=None,
            source=self.source,
            confidence=0.0,
            decision="REJECTED",
            status="BLOCKED",
            reason="PROMPT_INJECTION_DETECTED",
            extra={"patternMatched": pattern_matched},
        )
