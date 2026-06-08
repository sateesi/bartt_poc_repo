# BARTT AgentCore POC

**BARTT** (Broker Automated Reconciliation and Trade Tieout) AI agent built on
[Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/) using the
[Strands SDK](https://github.com/strands-agents/sdk-python).

This repository contains:

## Implementation Overview

The BARTT agent is a **Strands-based AI agent** hosted on Amazon Bedrock AgentCore. It exposes a
Streamlit chat interface where users can ask reconciliation and trade tieout questions. The
agent runs inside an AWS-managed container (AgentCore runtime) and is invoked either via the
`bedrock-agentcore` boto3 client (AWS mode) or a locally running Docker container (local mode).
Infrastructure is defined as AWS CDK (TypeScript) in `agentcore/cdk/` and provisioned with a
single `agentcore deploy` command. Temporary STS credentials are managed automatically by the
AgentCore CLI (`agentcore dev`) and stored in `agentcore/.env.local`.

| Component | Location | Description |
| --------- | -------- | ----------- |
| **barttagent** | `app/barttagent/` | Python agent backend — deployed to AWS Bedrock AgentCore |
| **barttuiapp** | `barttuiapp/` | Streamlit chat UI — runs locally via Docker |
| **AgentCore config** | `agentcore/` | CLI config, CDK infra, AWS targets, local credentials |

---

## Deployed Runtime

| Property | Value |
| -------- | ----- |
| Runtime ID | `barttagentcorerepo_barttagent-5qiZ7J3KGa` |
| Region | `ap-south-1` |
| Network | PUBLIC |
| Model | `apac.amazon.nova-pro-v1:0` (Amazon Nova Pro — APAC inference profile) |
| Runtime ARN | `arn:aws:bedrock-agentcore:ap-south-1:662864911724:runtime/barttagentcorerepo_barttagent-5qiZ7J3KGa` |

---

## Project Structure

```text
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
| ---- | ----- |
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

| Container    | Port | Description                                      |
| ------------ | ---- | ------------------------------------------------ |
| `barttagent` | 8080 | Agent backend — `POST /invocations`, `GET /ping` |
| `barttuiapp` | 8501 | Streamlit chat UI                                |

**Environment variables used (`INVOKE_MODE=local`):**

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `INVOKE_MODE` | `local` | Routing mode — `local` or `aws` |
| `AGENT_URL` | `http://barttagent:8080` | Backend URL (Docker service name) |
| `INVOKE_PATH` | `/invocations` | Agent invoke endpoint |

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
| -------- | ------- | ----------- |
| `INVOKE_MODE` | `aws` | Routes invocation to boto3 AgentCore client |
| `RUNTIME_ARN` | `arn:aws:bedrock-agentcore:ap-south-1:662864911724:runtime/barttagentcorerepo_barttagent-5qiZ7J3KGa` | Full runtime ARN (preferred over RUNTIME_ID) |
| `RUNTIME_ID` | `barttagentcorerepo_barttagent-5qiZ7J3KGa` | Runtime ID (fallback if RUNTIME_ARN not set) |
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

## Knowledge Base / RAG

The agent uses a Bedrock Knowledge Base backed by OpenSearch Serverless to answer
questions about BARTT trade data, reconciliation rules, and reference data.

### Infrastructure (deployed via CDK)

| Resource | Name / ID |
| -------- | --------- |
| S3 data bucket | `bartt-kb-data-source` |
| OSS collection | `bartt-kb-vectors` |
| Bedrock KB | `bartt-knowledge-base` |
| Embedding model | `amazon.titan-embed-text-v2:0` (1 024 dims) |

### First-time setup after `agentcore deploy`

**1. Get the KB and data-source IDs from CDK outputs:**

```bash
aws cloudformation describe-stacks \
  --stack-name "bartt-AgentCore-barttagentcorerepo-default" \
  --region ap-south-1 \
  --query "Stacks[0].Outputs"
```

Look for `KnowledgeBaseId` and `KnowledgeBaseDataSourceId`.

**2. Upload source documents to S3:**

```powershell
# BART requirement / architecture docs
aws s3 cp ".\BART REQ Docs" s3://bartt-kb-data-source/bart-req-docs/ --recursive

# JSON cross-reference data files
aws s3 cp ".\BART Requirement Understanding" s3://bartt-kb-data-source/bartt-json/ --recursive
```

**3. Trigger a Bedrock ingestion job:**

```bash
aws bedrock-agent start-ingestion-job \
  --knowledge-base-id <KnowledgeBaseId> \
  --data-source-id  <KnowledgeBaseDataSourceId> \
  --region ap-south-1
```

**4. Set `KNOWLEDGE_BASE_ID` in agentcore.json and docker-compose.aws.yml**, then
re-deploy:

```bash
# In agentcore/agentcore.json — update "value" for KNOWLEDGE_BASE_ID
# In docker-compose.aws.yml  — update KNOWLEDGE_BASE_ID: "<id>"
agentcore deploy
```

**5. Re-upload and re-ingest whenever source documents change** (repeat steps 2–3).

### How the agent uses the KB

`AmazonKnowledgeBases` from `strands-agents-tools` is registered as a tool when
`KNOWLEDGE_BASE_ID` is non-empty. The agent's system prompt instructs it to call
this tool first for any BARTT-domain question, grounding responses in the
retrieved chunks.

---

## Tearing Down / Cleanup

To destroy all deployed AWS resources (AgentCore runtime, IAM roles, ECR image, etc.):

```bash
# From the agentcore/cdk/ directory
cd agentcore/cdk
npx cdk destroy --all --force
```

Or delete the CloudFormation stack directly via AWS CLI:

```bash
aws cloudformation delete-stack --stack-name "bartt-AgentCore-barttagentcorerepo-default" --region ap-south-1
```

After teardown, reset the CLI state so the next `agentcore deploy` starts fresh:

```bash
# Reset deployed state (PowerShell)
Set-Content agentcore/.cli/deployed-state.json '{}'
```

> **Note:** The `CDKToolkit` CloudFormation stack and the `cdk-hnb659fds-container-assets-*` ECR repo are shared CDK bootstrap resources — do **not** delete them.

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
| ------- | ----------- |
| `agentcore dev` | Run agent locally with hot-reload + refresh credentials |
| `agentcore deploy` | Deploy agent to AWS via CDK |
| `agentcore status` | Show deployment status and runtime ID |
| `agentcore invoke` | Invoke agent (local or deployed) from CLI |
| `agentcore logs` | View agent CloudWatch logs |
| `agentcore traces` | View agent traces |
| `cd agentcore/cdk && npx cdk destroy --all --force` | Tear down all deployed AWS resources |

---

## Technical Notes

### AgentCore SDK Endpoints

The `BedrockAgentCoreApp` Starlette server registers these routes on port 8080:

| Route | Method | Description |
| ----- | ------ | ----------- |
| `/invocations` | POST | Agent entrypoint (via `@app.entrypoint`) |
| `/ping` | GET | Health/liveness — returns `{"status": "Healthy"}` |
| `/ws` | WS | WebSocket interface |

### boto3 AWS Mode

The UI calls the deployed runtime via the **`bedrock-agentcore`** boto3 client
(not `bedrock-agentcore-runtime` — that service name does not exist):

```python
client = boto3.client("bedrock-agentcore", region_name="ap-south-1")
resp = client.invoke_agent_runtime(
    agentRuntimeArn="arn:aws:bedrock-agentcore:ap-south-1:662864911724:runtime/...",
    payload=json.dumps({"prompt": prompt}).encode("utf-8"),
)
body = resp["response"]   # StreamingBody
```

### SSE Response Parsing

The AgentCore runtime streams its response as **Server-Sent Events** lines:

```text
data: "<thinking"
data: ">"
data: " \nThe answer is..."
```

The UI reads all chunks, then parses each `data:` line by JSON-decoding the value
(resolving `\n`, `\t`, unicode escapes), and joins them into a single string before
rendering with `st.markdown()`.

### Refreshing AWS Credentials (STS tokens)

Credentials expire. Always recreate the container (not just restart) after refreshing:

```bash
# Refresh credentials
agentcore dev   # Ctrl+C once .env.local is written

# Recreate container to pick up new credentials
docker compose -f docker-compose.aws.yml up --build -d
# NOTE: `docker compose restart` does NOT re-read env_file — must use `up`
```

---

## AWS Services — Purpose, Cost & Production Recommendations

> All costs in **USD · ap-south-1 pricing · June 2025**.
> POC estimates assume light usage (~5–10 users, ~1 M tokens/mo, minimal traffic).

### Service-by-Service Breakdown

| AWS Service | Why It Is Used | POC Monthly Cost | Cost Driver | Production Recommendation | Prod Monthly Estimate |
| --- | --- | --- | --- | --- | --- |
| **Amazon Bedrock AgentCore** | Managed serverless container runtime that hosts the Strands Python agent. Handles container lifecycle, scaling, health checks (`/ping`), and `POST /invocations` routing — no ECS/EKS to manage. | ~$50–100 | Compute + invocation count | Keep AgentCore. Enable **auto-scaling** and set minimum replicas to 0 for off-hours savings. | ~$150–400 |
| **Amazon Nova Pro** (`apac.amazon.nova-pro-v1:0`) | Primary LLM for trade reconciliation Q&A. Chosen for cost-effective reasoning with strong instruction-following. APAC inference profile routes to nearest AWS region automatically. | ~$5–15 | Input + output tokens | Move to **Nova Premier** for complex multi-step reasoning in prod; keep Nova Pro for simple lookups. Use **prompt caching** to reduce repeated context costs. | ~$50–200 |
| **Amazon Bedrock Knowledge Base** | RAG (Retrieval-Augmented Generation) layer — retrieves relevant BARTT trade data, reconciliation rules, and xref JSON from the vector store before answering. Prevents hallucinations by grounding the LLM in actual BARTT data. | ~$0–2 | Retrieve API calls | Keep. Add **metadata filtering** by product/exchange to improve retrieval precision and reduce token usage. | ~$5–20 |
| **Amazon Titan Embed Text v2** | Converts user queries and source documents into 1024-dim vectors for semantic search. Used during both ingestion (doc → vector) and retrieval (query → vector). | ~$1–2 | Tokens embedded | Keep for POC scale. At high doc volume consider **Cohere Embed v3** (better multilingual, lower cost per token). | ~$5–30 |
| **Amazon OpenSearch Serverless** | Vector store backing the Knowledge Base. Stores 1024-dim HNSW/faiss embeddings and serves kNN similarity searches. Serverless chosen for zero-ops POC setup. | ~$345 ⚠️ | **2 OCU minimum** billed 24×7 regardless of traffic | **Switch to OpenSearch Managed (t3.small.search, 1 node, 20 GB EBS)** — same Bedrock KB integration, ~85% cheaper. For even lower cost use **Aurora PostgreSQL + pgvector** (~$50–70/mo). See cost optimisation section below. | ~$60–80 (managed) |
| **Amazon S3** (`bartt-kb-data-source`) | Stores source documents (BARTT REQ Docs, xref JSON files) that are ingested into the Knowledge Base. Also used by CDK for deployment assets. | ~$1–3 | Storage + PUT/GET requests | Keep. Enable **S3 Intelligent-Tiering** for infrequently accessed docs to reduce storage cost. | ~$3–10 |
| **Amazon ECR** | Stores the Docker image for the barttagent container. AgentCore pulls the image on each deployment. | ~$1 | Image storage (GB) | Keep. Enable **ECR lifecycle policy** to auto-delete images older than 30 days, keeping only the last 3 tagged versions. | ~$1–3 |
| **AWS CDK / CloudFormation** | Infrastructure-as-Code for provisioning all AWS resources (AgentCore, KB, OSS, IAM roles, S3, ECR) in a single `agentcore deploy` command. Ensures reproducible, version-controlled infrastructure. | **Free** | — | Keep CDK. Add **CDK Pipelines** (CI/CD) for automated deployment on git push. | Free |
| **AWS IAM Roles** | Least-privilege access control: Agent Execution Role grants only `bedrock:Retrieve`; KB Role grants only `bedrock:InvokeModel`, `aoss:APIAccessAll`, and `s3:GetObject`. | **Free** | — | Keep. Add **IAM Access Analyzer** to detect overly permissive policies before production. | Free |

---

### Total Cost Summary

| Scenario | Monthly Estimate | Notes |
| --- | --- | --- |
| **POC (current — OSS Serverless)** | ~$403–467 | OpenSearch Serverless dominates at ~$345/mo |
| **POC optimised (OSS Managed t3.small)** | ~$120–155 | Switch OSS → managed single-node; ~65% saving |
| **POC optimised (Aurora + pgvector)** | ~$100–135 | Replace OSS with Aurora Serverless v2 + pgvector |
| **Production (10–50 users, OSS Managed)** | ~$350–700 | Scale AgentCore replicas + Nova Pro token volume |
| **Production (10–50 users, Aurora pgvector)** | ~$280–600 | Lowest vector-store cost path |

---

### OpenSearch Cost Optimisation Options

| Option | Change Required | Monthly Saving | Effort |
| --- | --- | --- | --- |
| **OSS Managed (t3.small, 1 node)** | Replace `CfnCollection` with `opensearch.Domain` in CDK stack | ~$270/mo (65%) | Low — 1 day CDK refactor |
| **Aurora PostgreSQL + pgvector** | Replace OSS with Aurora Serverless v2; update `storageConfiguration` in `CfnKnowledgeBase` to RDS type | ~$280/mo (68%) | Medium — 2 days |
| **Bedrock built-in vector store** | Remove OSS entirely; use Bedrock-managed store | ~$345/mo (100%) | Low — but **not yet available in ap-south-1** (preview only) |

---

## References

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [AgentCore CDK Constructs](https://github.com/aws/agentcore-l3-cdk-constructs)
- [Amazon OpenSearch Managed Pricing](https://aws.amazon.com/opensearch-service/pricing/)
- [Amazon Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)
- [Aurora Serverless v2 Pricing](https://aws.amazon.com/rds/aurora/pricing/)
