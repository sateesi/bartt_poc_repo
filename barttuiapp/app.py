"""
BARTT Agent Chat UI
Streamlit chat interface for the BARTT Amazon Bedrock AgentCore backend.

INVOKE_MODE=local  → plain HTTP POST to a locally running barttagent container
INVOKE_MODE=aws    → boto3 call to the deployed Bedrock AgentCore runtime on AWS
"""

import json
import os

import boto3
import requests
import streamlit as st
from botocore.exceptions import BotoCoreError, ClientError

# ── Configuration ──────────────────────────────────────────────────────────────
INVOKE_MODE = os.getenv("INVOKE_MODE", "local")   # "local" | "aws"

# Local mode settings
AGENT_URL   = os.getenv("AGENT_URL", "http://localhost:8080")
INVOKE_PATH = os.getenv("INVOKE_PATH", "/invocations")
INVOKE_URL  = f"{AGENT_URL}{INVOKE_PATH}"
HEALTH_URL  = f"{AGENT_URL}/ping"

# AWS mode settings
RUNTIME_ID  = os.getenv("RUNTIME_ID", "")
RUNTIME_ARN = os.getenv("RUNTIME_ARN", "")   # full ARN preferred; falls back to RUNTIME_ID
AWS_REGION  = os.getenv("AWS_REGION", "ap-south-1")

APP_TITLE = "BARTT Agent"
APP_ICON  = "🤖"

# ── Page Config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ─────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
        .stChatMessage { border-radius: 10px; }
        div[data-testid="stStatusWidget"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ BARTT Config")

    if INVOKE_MODE == "aws":
        st.markdown("**Mode:** `AWS` (Bedrock AgentCore)")
        st.markdown(f"**Region:** `{AWS_REGION}`")
        _display_arn = RUNTIME_ARN or RUNTIME_ID
        st.markdown(f"**Runtime:** `{_display_arn}`")
        st.divider()
        st.markdown("**Backend Status**")
        try:
            sts = boto3.client("sts", region_name=AWS_REGION)
            identity = sts.get_caller_identity()
            st.success(f"✅ Authenticated as `{identity.get('Arn', 'unknown')}`")
        except (BotoCoreError, ClientError) as exc:
            st.error(f"❌ AWS auth failed: `{exc}`")
        except Exception:
            st.warning("⚠️ Could not verify AWS credentials")
    else:
        st.markdown("**Mode:** `Local` (Docker)")
        st.markdown(f"**Backend URL:** `{AGENT_URL}`")
        st.markdown(f"**Endpoint:** `{INVOKE_PATH}`")
        st.divider()
        st.markdown("**Backend Status**")
        try:
            r = requests.get(HEALTH_URL, timeout=3)
            # /ping returns 200 when the AgentCore runtime is ready
            if r.status_code == 200:
                st.success("✅ Connected")
            elif r.status_code < 500:
                st.warning(f"⚠️ HTTP {r.status_code}")
            else:
                st.error(f"❌ HTTP {r.status_code}")
        except requests.exceptions.ConnectionError:
            st.error("❌ Unreachable")
        except Exception:
            st.info("⚪ Status unknown")

    st.divider()
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("Powered by Amazon Bedrock AgentCore · Strands SDK")


# ── Main Header ────────────────────────────────────────────────────────────────
st.title(f"{APP_ICON} {APP_TITLE}")
mode_label = "AWS Bedrock AgentCore" if INVOKE_MODE == "aws" else "local Docker"
st.caption(f"Ask anything — connected to **{mode_label}**")

# ── Session State ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ── Response Fetchers ─────────────────────────────────────────────────────────
def fetch_agent_local(prompt: str) -> str:
    """Fetch the full response from the locally running barttagent HTTP server."""
    with requests.post(
        INVOKE_URL,
        json={"prompt": prompt},
        stream=True,
        timeout=120,
        headers={"Content-Type": "application/json"},
    ) as resp:
        resp.raise_for_status()
        return "".join(
            chunk
            for chunk in resp.iter_content(chunk_size=None, decode_unicode=True)
            if chunk
        )


def fetch_agent_aws(prompt: str) -> str:
    """Fetch the full response from the deployed AWS Bedrock AgentCore runtime."""
    arn = RUNTIME_ARN or RUNTIME_ID
    if not arn:
        raise ValueError(
            "Set RUNTIME_ARN (full ARN) or RUNTIME_ID env var. "
            "Example RUNTIME_ARN: "
            "'arn:aws:bedrock-agentcore:ap-south-1:123456789012:runtime/my-runtime-id'"
        )
    # Service: 'bedrock-agentcore'  (boto3 name — NOT 'bedrock-agentcore-runtime')
    # Parameter: agentRuntimeArn accepts both full ARN and runtime ID
    # Response key: 'response' (streaming blob)
    client = boto3.client("bedrock-agentcore", region_name=AWS_REGION)
    resp = client.invoke_agent_runtime(
        agentRuntimeArn=arn,
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )
    body = resp.get("response")
    if body is None:
        return ""
    raw = b"".join(body.iter_chunks(chunk_size=1024)).decode("utf-8", errors="replace")
    return _parse_sse(raw)


def _parse_sse(raw: str) -> str:
    """Parse SSE lines of the form  data: "json-string"  into plain text.

    The AgentCore runtime returns each token as a Server-Sent Events line:
        data: "<thinking"
        data: ">"
        data: " \\nThe user is asking..."
    We JSON-decode each value so escape sequences (\\n, \\t, unicode) are
    resolved, then join everything into a single readable string.
    If a line is NOT in that format (plain text backend, etc.) we keep it as-is.
    """
    parts: list[str] = []
    for line in raw.splitlines():
        if line.startswith("data:"):
            value = line[len("data:"):].strip()
            try:
                # value is a JSON-encoded string, e.g. "\"hello\\nworld\""
                parts.append(json.loads(value))
            except (json.JSONDecodeError, ValueError):
                # not JSON — keep the raw value
                parts.append(value)
        elif line:
            # non-SSE line — keep verbatim
            parts.append(line)
    return "".join(parts)


def fetch_agent(prompt: str) -> str:
    """Route to the correct fetcher based on INVOKE_MODE."""
    if INVOKE_MODE == "aws":
        return fetch_agent_aws(prompt)
    return fetch_agent_local(prompt)


# ── Chat Input & Response ──────────────────────────────────────────────────────
if user_input := st.chat_input("Ask BARTT something..."):

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Thinking..."):
                full_response = fetch_agent(user_input)
            st.markdown(full_response)

        except requests.exceptions.ConnectionError:
            full_response = (
                "❌ **Cannot reach the BARTT Agent backend.**\n\n"
                f"Ensure the agent service is running at `{AGENT_URL}`.\n\n"
                "**Docker local:** `docker compose up` from repo root.\n"
                "**AWS mode:** run `docker compose -f docker-compose.aws.yml up`."
            )
            st.error(full_response)

        except (BotoCoreError, ClientError) as exc:
            full_response = f"❌ **AWS SDK error:** `{exc}`"
            st.error(full_response)

        except ValueError as exc:
            full_response = f"❌ **Configuration error:** {exc}"
            st.error(full_response)

        except requests.exceptions.HTTPError as exc:
            full_response = f"❌ **Agent returned an error:** `{exc}`"
            st.error(full_response)

        except requests.exceptions.Timeout:
            full_response = "❌ **Request timed out.** The agent took too long to respond."
            st.error(full_response)

        except Exception as exc:  # noqa: BLE001
            full_response = f"❌ **Unexpected error:** `{exc}`"
            st.error(full_response)

    st.session_state.messages.append(
        {"role": "assistant", "content": full_response}
    )
