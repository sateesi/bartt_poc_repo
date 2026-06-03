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
INVOKE_PATH = os.getenv("INVOKE_PATH", "/invoke")
INVOKE_URL  = f"{AGENT_URL}{INVOKE_PATH}"
HEALTH_URL  = f"{AGENT_URL}/health"

# AWS mode settings
RUNTIME_ID  = os.getenv("RUNTIME_ID", "")
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
        st.markdown(f"**Runtime ID:** `{RUNTIME_ID}`")
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
            if r.status_code < 400:
                st.success("✅ Connected")
            else:
                st.warning(f"⚠️ HTTP {r.status_code}")
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


# ── Streaming Generators ───────────────────────────────────────────────────────
def stream_agent_local(prompt: str):
    """Yield response chunks from the locally running barttagent HTTP server."""
    with requests.post(
        INVOKE_URL,
        json={"prompt": prompt},
        stream=True,
        timeout=120,
        headers={"Content-Type": "application/json"},
    ) as resp:
        resp.raise_for_status()
        for chunk in resp.iter_content(chunk_size=None, decode_unicode=True):
            if chunk:
                yield chunk


def stream_agent_aws(prompt: str):
    """Yield response chunks from the deployed AWS Bedrock AgentCore runtime."""
    if not RUNTIME_ID:
        raise ValueError(
            "RUNTIME_ID env var is not set. "
            "Set it to your AgentCore runtime ID, e.g. "
            "'barttagentcorerepo_barttagent-30zRtU516q'."
        )
    client = boto3.client("bedrock-agentcore-runtime", region_name=AWS_REGION)
    response = client.invoke_agent_runtime(
        agentRuntimeId=RUNTIME_ID,
        payload=json.dumps({"prompt": prompt}).encode("utf-8"),
    )
    body = response.get("body")
    if body is None:
        return
    # botocore StreamingBody — read in chunks
    for chunk in body.iter_chunks(chunk_size=1024):
        if chunk:
            yield chunk.decode("utf-8", errors="replace")


def stream_agent(prompt: str):
    """Route to the correct streaming generator based on INVOKE_MODE."""
    if INVOKE_MODE == "aws":
        yield from stream_agent_aws(prompt)
    else:
        yield from stream_agent_local(prompt)


# ── Chat Input & Response ──────────────────────────────────────────────────────
if user_input := st.chat_input("Ask BARTT something..."):

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    with st.chat_message("assistant"):
        try:
            full_response = st.write_stream(stream_agent(user_input))

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
