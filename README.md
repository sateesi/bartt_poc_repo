# BARTT AgentCore POC

**BARTT** (Broker Automated Reconciliation and Trade Tieout) AI agent built on
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using the
[Strands SDK](https://github.com/strands-agents/sdk-python).

This repository contains:

| Component | Location | Description |
|-----------|----------|-------------|
| **barttagent** | `app/barttagent/` | Python agent backend — deployed to AWS Bedrock AgentCore |
| **barttuiapp** | `barttuiapp/` | Streamlit chat UI — runs locally via Docker |
| **AgentCore config** | `agentcore/` | CLI config, CDK infra, AWS targets, local credentials |

---

## Deployed Runtime

| Property | Value |
|----------|-------|
| Runtime ID | `barttagentcorerepo_barttagent-30zRtU516q` |
| Region | `ap-south-1` |
| Network | PUBLIC |
| Model | `apac.amazon.nova-pro-v1:0` (Amazon Nova Pro — APAC inference profile) |
| Runtime ARN | `arn:aws:bedrock-agentcore:ap-south-1:662864911724:runtime/barttagentcorerepo_barttagent-30zRtU516q` |

---

## Project Structure

```
barttagentcorerepo/
├── README.md
├── docker-compose.yml          # Local mode — UI + backend containers
├── docker-compose.aws.yml      # AWS mode  — UI only, calls deployed runtime
├── app/
│   └── barttagent/
│       ├── main.py             # Agent entry point (@app.entrypoint)
│       ├── Dockerfile          # Container image for AgentCore deployment
│       └── pyproject.toml      # Python deps managed with uv
├── barttuiapp/
│   ├── app.py                  # Streamlit chat UI (dual-mode: local | aws)
│   ├── Dockerfile
│   ├── requirements.txt        # streamlit, requests, boto3
│   └── .dockerignore
├── agentcore/
│   ├── agentcore.json          # AgentCore project config
│   ├── aws-targets.json        # Deployment target (account + region)
│   ├── .env.local              # Temp AWS credentials — gitignored, refresh with `agentcore dev`
│   └── cdk/                   # CDK infrastructure
└── evaluators/
```

---

## Prerequisites

| Tool | Notes |
|------|-------|
| **Docker Desktop** | Required for both run modes |
| **Python 3.10+** + **uv** | For local agent dev only |
| **Node.js 20+** | Required for AgentCore CLI |
| **AWS credentials** | In `agentcore/.env.local` — refresh with `agentcore dev` |

---

## Run Mode 1 — Local Docker Stack

Both the Streamlit UI **and** the barttagent backend run as local Docker containers.
The UI calls the backend via the internal Docker bridge network.

```bash
# Build images and start both containers
docker compose up --build

# Open the chat UI
open http://localhost:8501
```

**Services started:**

| Container | Port | Description |
|-----------|------|-------------|
| `barttagent` | 8080 | Agent backend — serves HTTP `/invoke` |
| `barttuiapp` | 8501 | Streamlit chat UI |

**Environment variables used (`INVOKE_MODE=local`):**

| Variable | Default | Description |
|----------|---------|-------------|
| `INVOKE_MODE` | `local` | Routing mode — `local` or `aws` |
| `AGENT_URL` | `http://barttagent:8080` | Backend URL (Docker service name) |
| `INVOKE_PATH` | `/invoke` | Agent invoke endpoint |

---

## Run Mode 2 — AWS Mode (Deployed Runtime)

The UI runs in Docker locally but calls the **already-deployed** Amazon Bedrock AgentCore
runtime on AWS. No local agent container is started.

**Refresh credentials first** (they are temporary STS tokens):

```bash
agentcore dev   # starts local dev server AND refreshes agentcore/.env.local
# Ctrl+C once credentials are written — you don't need the dev server running
```

Then start the UI in AWS mode:

```bash
docker compose -f docker-compose.aws.yml up --build

# Open the chat UI
open http://localhost:8501
```

**Environment variables used (`INVOKE_MODE=aws`):**

| Variable | Default | Description |
|----------|---------|-------------|
| `INVOKE_MODE` | `aws` | Routes invocation to boto3 AgentCore client |
| `RUNTIME_ID` | `barttagentcorerepo_barttagent-30zRtU516q` | Deployed runtime ID |
| `AWS_REGION` | `ap-south-1` | AWS region |
| `AWS_ACCESS_KEY_ID` | from `agentcore/.env.local` | Temp STS credentials |
| `AWS_SECRET_ACCESS_KEY` | from `agentcore/.env.local` | Temp STS credentials |
| `AWS_SESSION_TOKEN` | from `agentcore/.env.local` | Temp STS credentials |

---

## Refreshing AWS Credentials

Credentials in `agentcore/.env.local` are temporary (STS tokens) and expire.
Refresh them whenever you see `ExpiredTokenException`:

```bash
agentcore dev
```

This regenerates the credentials. You can then `Ctrl+C` and re-run the compose stack.

---

## Deploying the Agent Backend

The backend (`barttagent`) is **already deployed**. Re-deploy only when `app/barttagent/`
code changes:

```bash
agentcore deploy
```

After a new deployment, the `RUNTIME_ID` in `docker-compose.aws.yml` may change.
Check the new ID with:

```bash
agentcore status
```

---

## Development — Agent Backend

Run the agent locally with hot-reload (without Docker):

```bash
agentcore dev
```

This starts the barttagent server at `http://localhost:8080` and writes fresh
credentials to `agentcore/.env.local`.

---

## AgentCore CLI Reference

| Command | Description |
|---------|-------------|
| `agentcore dev` | Run agent locally with hot-reload + refresh credentials |
| `agentcore deploy` | Deploy agent to AWS via CDK |
| `agentcore status` | Show deployment status and runtime ID |
| `agentcore invoke` | Invoke agent (local or deployed) from CLI |
| `agentcore logs` | View agent CloudWatch logs |
| `agentcore traces` | View agent traces |

---

## References

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [AgentCore CDK Constructs](https://github.com/aws/agentcore-l3-cdk-constructs)
