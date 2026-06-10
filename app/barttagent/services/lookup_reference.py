"""lookup_reference — Approved action-group tool for reference data lookups.

This tool wraps the reference_data guardrail and is the ONLY way the agent
is allowed to resolve BARTT codes, currencies, exchanges, lot sizes, and
price conversions.  The agent must NEVER invent these values.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from strands import tool

from guardrails.reference_data import lookup_reference as _raw_lookup
from guardrails.audit import AuditLogger

logger = logging.getLogger(__name__)
_audit = AuditLogger(source="lookup_reference")


@tool
def lookup_reference(code_type: str, code_value: str) -> str:
    """Look up a BARTT reference value by type.

    Args:
        code_type:  One of 'currency', 'exchange', 'bartt_code',
                    'lot_size', 'price_conversion'.
        code_value: The code to resolve (case-insensitive).

    Returns:
        JSON string with the lookup result.  On success returns
        {"status": "OK", ...}.  On failure returns
        {"status": "FAILED", "reason": "UNKNOWN_REFERENCE_DATA"}.
        The agent must NEVER invent values if this returns FAILED.
    """
    result = _raw_lookup(code_type, code_value)

    if result["status"] != "OK":
        _audit.log_failure(
            trade_id="N/A",
            input_code=f"{code_type}:{code_value}",
            reason=result.get("reason", "UNKNOWN_REFERENCE_DATA"),
        )

    return json.dumps(result)
