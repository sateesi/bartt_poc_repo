"""Input Validation Guardrail.

Validates and sanitises request payloads before any tool invocation.
Covers:
  - Trade date format validation (ISO-8601 ``YYYY-MM-DD``)
  - Rejection of future dates
  - Empty / missing field detection
  - SQL-injection payload rejection in date fields
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any

logger = logging.getLogger(__name__)

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def validate_trade_date(trade_date: str) -> dict[str, Any]:
    """Validate a trade-date string.

    Returns:
        ``{"valid": True, "date": <date>}`` on success.
        ``{"valid": False, "reason": "..."}`` on failure.
    """
    if not trade_date or not trade_date.strip():
        return {"valid": False, "reason": "EMPTY_TRADE_DATE"}

    trade_date = trade_date.strip()

    # Reject anything that is not a clean ISO date (blocks SQL injection)
    if not _ISO_DATE_RE.match(trade_date):
        logger.warning("Invalid trade_date format: %s", trade_date[:50])
        return {"valid": False, "reason": "INVALID_DATE_FORMAT", "detail": "Expected YYYY-MM-DD"}

    try:
        parsed = datetime.strptime(trade_date, "%Y-%m-%d").date()
    except ValueError:
        return {"valid": False, "reason": "INVALID_DATE_FORMAT", "detail": "Date does not exist"}

    if parsed > date.today():
        return {"valid": False, "reason": "FUTURE_DATE", "detail": f"{parsed} is in the future"}

    return {"valid": True, "date": parsed}


def validate_request_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run structural validation on an incoming trade normalisation request.

    Checks:
        - ``tradeId`` must be present and non-empty.
        - ``currency`` must be present and non-empty.
        - ``exchange`` must be present and non-empty.
        - ``tradeDate`` (if supplied) must pass ``validate_trade_date``.

    Returns:
        ``{"valid": True}`` when all checks pass, or
        ``{"valid": False, "errors": [...]}`` with a list of issues.
    """
    errors: list[dict[str, str]] = []

    required_fields = ["tradeId", "currency", "exchange"]
    for field in required_fields:
        value = payload.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append({"field": field, "reason": f"MISSING_{field.upper()}"})

    trade_date = payload.get("tradeDate")
    if trade_date is not None:
        date_result = validate_trade_date(str(trade_date))
        if not date_result["valid"]:
            errors.append({"field": "tradeDate", "reason": date_result["reason"], "detail": date_result.get("detail", "")})

    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True}
