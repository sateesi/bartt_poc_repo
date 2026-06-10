"""BARTT Agent Guardrails — enterprise-grade safety layer for trade normalisation.

Modules:
    reference_data   — Ensures all codes come from approved lookup sources.
    sql_safety       — Blocks any agent-generated SQL.
    input_validation — Validates and sanitises incoming request payloads.
    write_validation — Validates all fields before database writes.
    confidence       — Attaches confidence scores and auto-approval decisions.
    audit            — Structured audit logging for every normalisation action.
    prompt_injection — Detects and rejects prompt injection attempts.
"""

from guardrails.reference_data import validate_reference_lookup, lookup_reference
from guardrails.sql_safety import detect_sql_in_text, SqlSafetyError
from guardrails.input_validation import validate_trade_date, validate_request_payload
from guardrails.write_validation import validate_normalized_trade
from guardrails.confidence import compute_confidence, ConfidenceDecision
from guardrails.audit import create_audit_entry, AuditLogger
from guardrails.prompt_injection import detect_prompt_injection, PromptInjectionError

__all__ = [
    "validate_reference_lookup",
    "lookup_reference",
    "detect_sql_in_text",
    "SqlSafetyError",
    "validate_trade_date",
    "validate_request_payload",
    "validate_normalized_trade",
    "compute_confidence",
    "ConfidenceDecision",
    "create_audit_entry",
    "AuditLogger",
    "detect_prompt_injection",
    "PromptInjectionError",
]
