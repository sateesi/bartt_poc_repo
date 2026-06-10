"""Confidence Score Guardrail.

Attaches a confidence score to normalisation results and determines the
auto-approval decision:

    >= 0.95   →  AUTO_APPROVED
    0.80–0.94 →  REVIEW_REQUIRED
    < 0.80    →  REJECTED
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class ConfidenceDecision(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ConfidenceResult:
    confidence: float
    decision: ConfidenceDecision

    def to_dict(self) -> dict[str, Any]:
        return {"confidence": self.confidence, "decision": self.decision.value}


def compute_confidence(
    currency_found: bool,
    exchange_found: bool,
    bartt_code_found: bool,
    lot_size_found: bool = True,
    price_conversion_found: bool = True,
) -> ConfidenceResult:
    """Compute confidence based on how many reference lookups succeeded.

    Each lookup contributes a weighted fraction:
        - currency:         0.25
        - exchange:         0.25
        - bartt_code:       0.30
        - lot_size:         0.10
        - price_conversion: 0.10

    If **any** critical lookup (currency, exchange, bartt_code) is missing the
    confidence is capped at 0.50 and the decision is ``REJECTED``.
    """
    weights = {
        "currency": 0.25,
        "exchange": 0.25,
        "bartt_code": 0.30,
        "lot_size": 0.10,
        "price_conversion": 0.10,
    }

    flags = {
        "currency": currency_found,
        "exchange": exchange_found,
        "bartt_code": bartt_code_found,
        "lot_size": lot_size_found,
        "price_conversion": price_conversion_found,
    }

    score = sum(weights[k] for k, v in flags.items() if v)

    # Critical fields — if any are missing, cap the score
    critical_fields = ["currency", "exchange", "bartt_code"]
    critical_missing = [f for f in critical_fields if not flags[f]]

    if critical_missing:
        score = min(score, 0.50)
        logger.info("Critical reference(s) missing: %s — confidence capped at %.2f", critical_missing, score)

    # Determine decision
    if score >= 0.95:
        decision = ConfidenceDecision.AUTO_APPROVED
    elif score >= 0.80:
        decision = ConfidenceDecision.REVIEW_REQUIRED
    else:
        decision = ConfidenceDecision.REJECTED

    return ConfidenceResult(confidence=round(score, 2), decision=decision)


def unknown_result() -> dict[str, Any]:
    """Return a standardised UNKNOWN response for unverifiable information."""
    return {"status": "UNKNOWN", "confidence": 0.0, "decision": ConfidenceDecision.UNKNOWN.value}
