"""
BARTT Agent Chat UI
A Streamlit-based chat interface for the BARTT Amazon Bedrock AgentCore backend.
"""

import os

import requests
import streamlit as st

# ── Configuration ──────────────────────────────────────────────────────────────
AGENT_URL = os.getenv("AGENT_URL", "http://localhost:8080")
INVOKE_PATH = os.getenv("INVOKE_PATH", "/invoke")
INVOKE_URL = f"{AGENT_URL}{INVOKE_PATH}"
HEALTH_URL = f"{AGENT_URL}/health"

APP_TITLE = "BARTT Agent"
APP_ICON = "🤖"

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
        .sidebar-title { font-size: 1.2rem; font-weight: 700; }
        div[data-testid="stStatusWidget"] { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ BARTT Config")
    st.markdown(f"**Backend URL:** `{AGENT_URL}`")
    st.markdown(f"**Endpoint:** `{INVOKE_PATH}`")

    st.divider()

    # Backend health check
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
        # Some AgentCore runtimes don't expose /health — treat as unknown
        st.info("⚪ Status unknown")

    st.divider()

    # Clear conversation
    if st.button("🗑️ Clear Conversation", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.caption("Powered by Amazon Bedrock AgentCore · Strands SDK")


# ── Main Header ────────────────────────────────────────────────────────────────
st.title(f"{APP_ICON} {APP_TITLE}")
st.caption("Ask anything — powered by Amazon Bedrock AgentCore")

# ── Session State ──────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render existing conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# ── Streaming Generator ────────────────────────────────────────────────────────
def stream_agent(prompt: str):
    """Yield response text chunks streamed from the barttagent backend."""
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


# ── Chat Input & Response ──────────────────────────────────────────────────────
if user_input := st.chat_input("Ask BARTT something..."):

    # Append and display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Stream agent response
    with st.chat_message("assistant"):
        try:
            # st.write_stream handles the generator and returns the full text
            full_response = st.write_stream(stream_agent(user_input))

        except requests.exceptions.ConnectionError:
            full_response = (
                "❌ **Cannot reach the BARTT Agent backend.**\n\n"
                f"Ensure the agent service is running at `{AGENT_URL}`.\n\n"
                "**Local dev:** run `agentcore dev` in the `barttagent` directory.\n"
                "**Docker:** run `docker compose up` from the repo root."
            )
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
