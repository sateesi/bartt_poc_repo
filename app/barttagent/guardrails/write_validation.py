"""Controlled Write Operations Guardrail.

Validates every field of a normalised trade record before allowing a
database write.  All reference values (currency, exchange, BARTT code,
lot size) must exist in the approved registries.  The write itself must
go through stored procedures — never dynamic SQL.
"""

from __future__ import annotations

import logging
from typing import Any

from guardrails.reference_data import validate_reference_lookup
from guardrails.input_validation import validate_trade_date

logger = logging.getLogger(__name__)


def validate_normalized_trade(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate all fields of a normalised trade before writing.

    Checks:
        - ``tradeId`` is present
        - ``currency`` exists in approved currencies
        - ``exchange`` exists in approved exchanges
        - ``barttCode`` exists in approved BARTT codes
        - ``lotSize`` exists in approved lot sizes (when provided)
        - ``tradeDate`` passes date validation (when provided)

    Returns:
        ``{"valid": True}`` or ``{"valid": False, "errors": [...]}``
    """
    errors: list[dict[str, str]] = []

    # tradeId
    trade_id = payload.get("tradeId")
    if not trade_id or (isinstance(trade_id, str) and not trade_id.strip()):
        errors.append({"field": "tradeId", "reason": "MISSING_TRADE_ID"})

    # Currency
    currency = payload.get("currency", "")
    if not currency:
        errors.append({"field": "currency", "reason": "MISSING_CURRENCY"})
    elif not validate_reference_lookup("currency", currency):
        errors.append({"field": "currency", "reason": "UNKNOWN_REFERENCE_DATA", "detail": f"Currency '{currency}' not found"})

    # Exchange
    exchange = payload.get("exchange", "")
    if not exchange:
        errors.append({"field": "exchange", "reason": "MISSING_EXCHANGE"})
    elif not validate_reference_lookup("exchange", exchange):
        errors.append({"field": "exchange", "reason": "UNKNOWN_REFERENCE_DATA", "detail": f"Exchange '{exchange}' not found"})

    # BARTT code
    bartt_code = payload.get("barttCode", "")
    if not bartt_code:
        errors.append({"field": "barttCode", "reason": "MISSING_BARTT_CODE"})
    elif not validate_reference_lookup("bartt_code", bartt_code):
        errors.append({"field": "barttCode", "reason": "UNKNOWN_REFERENCE_DATA", "detail": f"BARTT code '{bartt_code}' not found"})

    # Lot size (optional but must be valid if provided)
    lot_size_key = payload.get("lotSizeKey")
    if lot_size_key and not validate_reference_lookup("lot_size", lot_size_key):
        errors.append({"field": "lotSizeKey", "reason": "UNKNOWN_REFERENCE_DATA", "detail": f"Lot size key '{lot_size_key}' not found"})

    # Trade date (optional but must be valid if provided)
    trade_date = payload.get("tradeDate")
    if trade_date:
        date_result = validate_trade_date(str(trade_date))
        if not date_result["valid"]:
            errors.append({"field": "tradeDate", "reason": date_result["reason"], "detail": date_result.get("detail", "")})

    if errors:
        return {"valid": False, "errors": errors}
    return {"valid": True}
