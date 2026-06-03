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
| `barttagent` | 8080 | Agent backend — `POST /invocations`, `GET /ping` |
| `barttuiapp` | 8501 | Streamlit chat UI |

**Environment variables used (`INVOKE_MODE=local`):**

| Variable | Default | Description |
|----------|---------|-------------|
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
|----------|---------|-------------|
| `INVOKE_MODE` | `aws` | Routes invocation to boto3 AgentCore client |
| `RUNTIME_ARN` | `arn:aws:bedrock-agentcore:ap-south-1:662864911724:runtime/barttagentcorerepo_barttagent-30zRtU516q` | Full runtime ARN (preferred over RUNTIME_ID) |
| `RUNTIME_ID` | `barttagentcorerepo_barttagent-30zRtU516q` | Runtime ID (fallback if RUNTIME_ARN not set) |
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

## Technical Notes

### AgentCore SDK Endpoints

The `BedrockAgentCoreApp` Starlette server registers these routes on port 8080:

| Route | Method | Description |
|-------|--------|-------------|
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

```
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

## References

- [AgentCore CLI](https://github.com/aws/agentcore-cli)
- [Amazon Bedrock AgentCore](https://aws.amazon.com/bedrock/agentcore/)
- [Strands Agents SDK](https://github.com/strands-agents/sdk-python)
- [AgentCore CDK Constructs](https://github.com/aws/agentcore-l3-cdk-constructs)

---

## RAG — Bedrock Knowledge Base

The agent uses an Amazon Bedrock Knowledge Base to ground all answers in BARTT
business documents.  Retrieval is mandatory by default (`GROUNDING_STRICT_MODE=true`):
if the query cannot be answered from the knowledge base, the agent replies with a
fixed "not found" message rather than hallucinating.

### Architecture

```
User prompt
   │
   ▼
┌──────────────────────┐
│  invoke() entrypoint │
│   (main.py)          │
└──────┬───────────────┘
       │ 1. retrieve_context(query)
       ▼
┌──────────────────────┐     Bedrock
│  knowledge_base_     │ ──► retrieve API
│  service.py          │ ◄── chunks + sources
└──────┬───────────────┘
       │ 2. filter by MIN_RETRIEVAL_SCORE
       │ 3. build_context() + build_grounded_prompt()
       ▼
┌──────────────────────┐
│  Strands Agent       │ ──► Nova Pro / inference profile
│  stream_async()      │ ◄── streamed tokens
└──────┬───────────────┘
       │ 4. yield tokens + format_sources()
       ▼
  Response to caller
```

### Knowledge Base Environment Variables

Set these on the agent runtime (locally in `agentcore/.env.local`, or as
container overrides when deploying to AgentCore):

| Variable | Default | Description |
|----------|---------|-------------|
| `KNOWLEDGE_BASE_ID` | _(required)_ | Bedrock KB ID — output of the CDK deployment |
| `MAX_RETRIEVAL_RESULTS` | `5` | Max chunks retrieved per query |
| `MIN_RETRIEVAL_SCORE` | `0.5` | Minimum relevance score — chunks below this are discarded |
| `GROUNDING_STRICT_MODE` | `true` | `true` = no KB results → fixed "not found" reply, no LLM call |
| `MAX_CONTEXT_CHARS` | `8000` | Maximum characters of retrieved context sent to the model |
| `KB_MAX_RETRIES` | `3` | Retry attempts for transient KB API errors |
| `KB_RETRY_BASE_DELAY_S` | `1.0` | Initial backoff delay in seconds (doubles each retry) |

### Deploying the Knowledge Base CDK Stack

The Knowledge Base infrastructure lives in a separate CDK stack
(`agentcore/cdk/lib/knowledge-base-stack.ts`) so it can be deployed
independently from the agent runtime.

```bash
cd agentcore/cdk
npm install

# Deploy the KB stack (S3 bucket + OpenSearch Serverless + Bedrock KB)
npm run cdk deploy "KnowledgeBase-*"
```

> **Cost note:** OpenSearch Serverless collections incur OCU charges even when
> idle.  Destroy the stack with `npm run cdk destroy "KnowledgeBase-*"` when
> done with the POC to avoid unexpected charges.

### Post-Deploy Steps (One-Time Manual Setup)

CloudFormation cannot create the OpenSearch Serverless vector index — this must
be done via the OpenSearch API **after** the AOSS collection is ACTIVE.

#### 1. Retrieve the collection endpoint

```bash
aws cloudformation describe-stacks \
  --stack-name "KnowledgeBase-barttagentcorerepo-<target-name>" \
  --query "Stacks[0].Outputs[?OutputKey=='AossCollectionEndpoint'].OutputValue" \
  --output text
# → e.g. https://abc123.ap-south-1.aoss.amazonaws.com
```

#### 2. Create the vector index

Replace `<ENDPOINT>` with the value above and run with AWS credentials that have
`aoss:APIAccessAll` on the collection (the account root is pre-authorised by the
CDK data access policy):

```bash
ENDPOINT="<ENDPOINT>"   # e.g. https://abc123.ap-south-1.aoss.amazonaws.com

curl -X PUT "${ENDPOINT}/bartt-kb-index" \
  -H "Content-Type: application/json" \
  --aws-sigv4 "aws:amz:ap-south-1:aoss" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "x-amz-security-token: ${AWS_SESSION_TOKEN}" \
  -d '{
    "settings": { "index.knn": true },
    "mappings": {
      "properties": {
        "embedding":  { "type": "knn_vector", "dimension": 1024 },
        "text":       { "type": "text" },
        "metadata":   { "type": "text" }
      }
    }
  }'
```

> The embedding dimension `1024` matches `amazon.titan-embed-text-v2:0`.

#### 3. Upload BARTT documents to S3

```bash
# Get bucket name from CDK outputs
BUCKET=$(aws cloudformation describe-stacks \
  --stack-name "KnowledgeBase-barttagentcorerepo-<target-name>" \
  --query "Stacks[0].Outputs[?OutputKey=='S3BucketName'].OutputValue" \
  --output text)

# Upload the BARTT reference JSON files
aws s3 cp "BART Requirement Understanding/" "s3://${BUCKET}/bartt-docs/" --recursive
```

#### 4. Start a KB ingestion job

```bash
KB_ID=$(aws cloudformation describe-stacks \
  --stack-name "KnowledgeBase-barttagentcorerepo-<target-name>" \
  --query "Stacks[0].Outputs[?OutputKey=='KnowledgeBaseId'].OutputValue" \
  --output text)

DS_ID=$(aws cloudformation describe-stacks \
  --stack-name "KnowledgeBase-barttagentcorerepo-<target-name>" \
  --query "Stacks[0].Outputs[?OutputKey=='DataSourceId'].OutputValue" \
  --output text)

aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "${KB_ID}" \
  --data-source-id   "${DS_ID}"
```

Monitor the job:
```bash
aws bedrock-agent get-ingestion-job \
  --knowledge-base-id "${KB_ID}" \
  --data-source-id   "${DS_ID}" \
  --ingestion-job-id <job-id from previous command>
```

#### 5. Configure the agent runtime

Set the `KNOWLEDGE_BASE_ID` environment variable on the agent:

- **Local (`agentcore/.env.local`):** add `KNOWLEDGE_BASE_ID=<kb-id>`
- **Deployed runtime:** run `agentcore deploy` with the env var set in the
  relevant harness/environment config so the container picks it up.

After setting `KNOWLEDGE_BASE_ID`, redeploy the agent:

```bash
agentcore deploy
```
