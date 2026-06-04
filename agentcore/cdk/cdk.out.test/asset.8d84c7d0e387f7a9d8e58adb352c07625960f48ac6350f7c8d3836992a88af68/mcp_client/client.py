import os
import logging
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

logger = logging.getLogger(__name__)

# ExaAI provides information about code through web searches, crawling and code context searches through their platform. Requires no authentication
DEFAULT_MCP_ENDPOINT = "https://mcp.exa.ai/mcp"

def _is_enabled(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def get_streamable_http_mcp_client() -> MCPClient | None:
    """Returns an MCP Client compatible with Strands when enabled via env vars."""
    if not _is_enabled(os.getenv("ENABLE_EXTERNAL_MCP", "0")):
        logger.info("External MCP client is disabled (set ENABLE_EXTERNAL_MCP=1 to enable).")
        return None

    endpoint = os.getenv("MCP_ENDPOINT", DEFAULT_MCP_ENDPOINT)
    access_token = os.getenv("MCP_ACCESS_TOKEN", "").strip()

    headers = None
    if access_token:
        headers = {"Authorization": f"Bearer {access_token}"}

    return MCPClient(lambda: streamablehttp_client(endpoint, headers=headers))
