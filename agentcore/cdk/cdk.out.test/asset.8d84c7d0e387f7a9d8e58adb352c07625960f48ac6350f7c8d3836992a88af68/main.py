import time
from typing import Any

from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from model.load import load_model
from mcp_client.client import get_streamable_http_mcp_client
from config import KNOWLEDGE_BASE_ID, GROUNDING_STRICT_MODE
from services.knowledge_base_service import retrieve_context
from services.prompt_builder import (
    NOT_FOUND_RESPONSE,
    build_context,
    build_grounded_prompt,
    format_sources,
)

app = BedrockAgentCoreApp()
log = app.logger

# ---------------------------------------------------------------------------
# Startup validation — fail fast in strict mode when KB is not configured.
# ---------------------------------------------------------------------------
if not KNOWLEDGE_BASE_ID:
    if GROUNDING_STRICT_MODE:
        log.error(
            "KNOWLEDGE_BASE_ID environment variable is not set. "
            "RAG grounding is required (GROUNDING_STRICT_MODE=true). "
            "Set KNOWLEDGE_BASE_ID to your Bedrock Knowledge Base ID and restart."
        )
        raise SystemExit(1)
    else:
        log.warning(
            "KNOWLEDGE_BASE_ID not set. RAG grounding is disabled. "
            "Set KNOWLEDGE_BASE_ID to enable knowledge-grounded responses."
        )

# ---------------------------------------------------------------------------
# System prompt — strict BARTT grounding instructions.
# The user-turn message (built by prompt_builder) carries the KB context and
# question; the system prompt carries the behavioural guardrails.
# ---------------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = """\
You are a BARTT Business Assistant (Broker Automated Reconciliation and Trade Tieout).

You must answer ONLY using the knowledge base context provided in the user message.
If the context does not contain the answer, respond exactly:
"I could not find this information in the BARTT knowledge base."

Never fabricate information. Never use knowledge outside the provided context.\
"""

# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

# Define a Streamable HTTP MCP Client
mcp_clients = [get_streamable_http_mcp_client()]

# Collect all tools
tools: list[Any] = []


@tool
def add_numbers(a: int, b: int) -> int:
    """Return the sum of two numbers"""
    return a + b


tools.append(add_numbers)

for mcp_client in mcp_clients:
    if mcp_client:
        tools.append(mcp_client)

# ---------------------------------------------------------------------------
# Agent singleton
# ---------------------------------------------------------------------------

_agent: Agent | None = None


def get_or_create_agent() -> Agent:
    global _agent
    if _agent is None:
        _agent = Agent(
            model=load_model(),
            system_prompt=DEFAULT_SYSTEM_PROMPT,
            tools=tools,
        )
    return _agent


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


@app.entrypoint
async def invoke(payload: dict[str, Any], context: Any) -> Any:  # type: ignore[misc]
    log.info("Invoking Agent.....")

    user_query: str = payload.get("prompt", "")
    t_start = time.monotonic()

    # ------------------------------------------------------------------
    # Step 1 — Retrieve context from Bedrock Knowledge Base.
    # ------------------------------------------------------------------
    retrieval_results: dict[str, list[Any]] = {"chunks": [], "sources": [], "metadata": []}
    retrieval_attempted = False

    if KNOWLEDGE_BASE_ID:
        try:
            retrieval_results = await retrieve_context(user_query)
            retrieval_attempted = True
        except ValueError as exc:
            # Config error — already logged in the service layer.
            log.error("KB configuration error: %s", exc)
        except RuntimeError as exc:
            log.warning(
                "Knowledge base retrieval failed. Proceeding without grounding. Error: %s",
                exc,
            )

    chunks: list[Any] = retrieval_results.get("chunks", [])
    sources: list[str] = retrieval_results.get("sources", [])

    # ------------------------------------------------------------------
    # Step 2 — Decide prompt strategy.
    # ------------------------------------------------------------------
    if not chunks:
        if retrieval_attempted:
            # KB responded but found nothing relevant — return not-found
            # immediately (no model call) to prevent hallucination.
            log.info(
                "No KB results for query. Returning not-found response. "
                "knowledge_base_id=%s",
                KNOWLEDGE_BASE_ID,
            )
            yield NOT_FOUND_RESPONSE
            return
        # KB retrieval failed (network/API error) — fall back to the
        # original query so the service remains usable.
        final_prompt = user_query
    else:
        # Retrieved context available — build grounded prompt.
        kb_context = build_context(retrieval_results)
        final_prompt = build_grounded_prompt(user_query, kb_context)

    # ------------------------------------------------------------------
    # Step 3 — Invoke the Foundation Model via the Strands Agent.
    # ------------------------------------------------------------------
    agent = get_or_create_agent()
    model_t0 = time.monotonic()

    stream = agent.stream_async(final_prompt)
    async for event in stream:
        if "data" in event and isinstance(event["data"], str):
            yield event["data"]

    model_ms = int((time.monotonic() - model_t0) * 1000)
    total_ms = int((time.monotonic() - t_start) * 1000)

    # ------------------------------------------------------------------
    # Step 4 — Append source attribution when grounding was active.
    # ------------------------------------------------------------------
    if sources:
        yield format_sources(sources)

    log.info(
        "Agent invocation complete. "
        "grounding_active=%s retrieved_chunks=%d source_docs=%d "
        "model_ms=%d total_ms=%d",
        bool(chunks),
        len(chunks),
        len(sources),
        model_ms,
        total_ms,
    )


if __name__ == "__main__":
    app.run()
