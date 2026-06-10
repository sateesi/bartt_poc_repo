"""Reference Data Lookup Guardrail.

Ensures the agent NEVER invents BARTT codes, currency codes, exchange codes,
lot-size mappings, or price-conversion mappings.  All values must originate
from approved reference tables or knowledge-base sources.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Approved reference data registries (populated at startup from JSON / DB)
# ---------------------------------------------------------------------------
_APPROVED_CURRENCIES: set[str] = set()
_APPROVED_EXCHANGES: set[str] = set()
_APPROVED_BARTT_CODES: set[str] = set()
_APPROVED_LOT_SIZES: dict[str, float] = {}
_APPROVED_PRICE_CONVERSIONS: dict[str, float] = {}


def load_approved_data(
    currencies: set[str] | None = None,
    exchanges: set[str] | None = None,
    bartt_codes: set[str] | None = None,
    lot_sizes: dict[str, float] | None = None,
    price_conversions: dict[str, float] | None = None,
) -> None:
    """Populate approved reference registries (call once at startup)."""
    global _APPROVED_CURRENCIES, _APPROVED_EXCHANGES, _APPROVED_BARTT_CODES
    global _APPROVED_LOT_SIZES, _APPROVED_PRICE_CONVERSIONS
    if currencies is not None:
        _APPROVED_CURRENCIES = {c.upper() for c in currencies}
    if exchanges is not None:
        _APPROVED_EXCHANGES = {e.upper() for e in exchanges}
    if bartt_codes is not None:
        _APPROVED_BARTT_CODES = {b.upper() for b in bartt_codes}
    if lot_sizes is not None:
        _APPROVED_LOT_SIZES = lot_sizes
    if price_conversions is not None:
        _APPROVED_PRICE_CONVERSIONS = price_conversions


# ---------------------------------------------------------------------------
# Lookup with strict validation
# ---------------------------------------------------------------------------

VALID_CODE_TYPES = {"currency", "exchange", "bartt_code", "lot_size", "price_conversion"}


def lookup_reference(code_type: str, code_value: str) -> dict[str, Any]:
    """Look up a reference value by type.  Returns the value if found, or a
    deterministic FAILED response — never guesses or infers.

    Args:
        code_type:  One of ``currency``, ``exchange``, ``bartt_code``,
                    ``lot_size``, ``price_conversion``.
        code_value: The code to resolve (case-insensitive).

    Returns:
        ``{"status": "OK", "code_type": ..., "code_value": ..., "resolved": ...}``
        on success, or
        ``{"status": "FAILED", "reason": "UNKNOWN_REFERENCE_DATA"}`` on miss.
    """
    code_type = code_type.strip().lower()
    code_value_upper = code_value.strip().upper()

    if code_type not in VALID_CODE_TYPES:
        logger.warning("lookup_reference called with invalid code_type=%s", code_type)
        return {
            "status": "FAILED",
            "reason": "INVALID_CODE_TYPE",
            "detail": f"code_type must be one of {sorted(VALID_CODE_TYPES)}",
        }

    registry_map: dict[str, Any] = {
        "currency": _APPROVED_CURRENCIES,
        "exchange": _APPROVED_EXCHANGES,
        "bartt_code": _APPROVED_BARTT_CODES,
        "lot_size": _APPROVED_LOT_SIZES,
        "price_conversion": _APPROVED_PRICE_CONVERSIONS,
    }

    registry = registry_map[code_type]

    if isinstance(registry, set):
        if code_value_upper in registry:
            return {"status": "OK", "code_type": code_type, "code_value": code_value_upper, "resolved": code_value_upper}
    elif isinstance(registry, dict):
        if code_value_upper in registry:
            return {"status": "OK", "code_type": code_type, "code_value": code_value_upper, "resolved": registry[code_value_upper]}

    logger.info("Reference lookup miss: code_type=%s code_value=%s", code_type, code_value)
    return {"status": "FAILED", "reason": "UNKNOWN_REFERENCE_DATA"}


def validate_reference_lookup(code_type: str, code_value: str) -> bool:
    """Return True only if the reference value exists in the approved registry."""
    result = lookup_reference(code_type, code_value)
    return result["status"] == "OK"
