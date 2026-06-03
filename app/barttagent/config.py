"""Centralised runtime configuration for the BARTT AgentCore application.

All values are read from environment variables so the same container image
can be used in every environment without rebuilding.
"""
import os

# ---------------------------------------------------------------------------
# AWS
# ---------------------------------------------------------------------------
AWS_REGION: str = os.getenv("AWS_REGION", "ap-south-1")

# ---------------------------------------------------------------------------
# Bedrock Knowledge Base
# ---------------------------------------------------------------------------

# Required — fail fast in strict mode if this is absent.
KNOWLEDGE_BASE_ID: str = os.getenv("KNOWLEDGE_BASE_ID", "")

# Maximum number of chunks to retrieve per query.
MAX_RETRIEVAL_RESULTS: int = int(os.getenv("MAX_RETRIEVAL_RESULTS", "5"))

# Minimum relevance score (0.0 – 1.0) for a retrieved chunk to be included
# in the context.  Chunks below this threshold are discarded.
MIN_RETRIEVAL_SCORE: float = float(os.getenv("MIN_RETRIEVAL_SCORE", "0.5"))

# When True: if no KB context is available the agent returns the standard
# "not found" message without calling the LLM — prevents hallucination.
# When False: the agent calls the LLM even without KB context (useful for
# development/debugging).
GROUNDING_STRICT_MODE: bool = os.getenv("GROUNDING_STRICT_MODE", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}

# Hard ceiling on context characters injected into the prompt to prevent
# token explosions with large knowledge bases.
MAX_CONTEXT_CHARS: int = int(os.getenv("MAX_CONTEXT_CHARS", "8000"))

# ---------------------------------------------------------------------------
# Retrieval retry / backoff
# ---------------------------------------------------------------------------
KB_MAX_RETRIES: int = int(os.getenv("KB_MAX_RETRIES", "3"))
KB_RETRY_BASE_DELAY_S: float = float(os.getenv("KB_RETRY_BASE_DELAY_S", "1.0"))
