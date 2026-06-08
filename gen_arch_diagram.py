"""
Generate BARTT AgentCore Architecture PNG using the diagrams library.
Run with: py gen_arch_diagram.py
Output:  BARTT_AgentCore_Architecture.png
"""
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.ml import Bedrock, SagemakerModel
from diagrams.aws.storage import S3
from diagrams.aws.security import IAMRole
from diagrams.aws.compute import ECR
from diagrams.aws.devtools import Codebuild
from diagrams.aws.general import User, GenericOfficeBuilding
from diagrams.aws.analytics import AmazonOpensearchService as OpenSearch
from diagrams.onprem.client import Users
from diagrams.onprem.container import Docker
from diagrams.programming.language import Python
from diagrams.generic.compute import Rack

# ── Arrow style helpers ───────────────────────────────────────────────────────
def req(step, label=""):
    """Blue numbered request-flow arrow."""
    return Edge(
        label=f"[{step}] {label}".strip(),
        color="#1565C0",
        style="bold",
        fontcolor="#1565C0",
        fontsize="11",
    )

def res(step, label=""):
    """Green numbered response-flow arrow."""
    return Edge(
        label=f"[{step}] {label}".strip(),
        color="#2E7D32",
        style="bold",
        fontcolor="#2E7D32",
        fontsize="11",
    )

def deploy_edge(label=""):
    """Gray dashed deploy/provision arrow."""
    return Edge(label=label, color="#78909C", style="dashed", fontcolor="#78909C", fontsize="10")

def iam_edge(label=""):
    """Orange dashed IAM-grant arrow."""
    return Edge(label=label, color="#E65100", style="dashed", fontcolor="#E65100", fontsize="9")


# ── Cost note text (bottom graph label) ──────────────────────────────────────
COST_NOTE = (
    "💰  AWS Ballpark Monthly Cost Estimate (POC / Light Usage)\n"
    "─────────────────────────────────────────────────────────────────────────────────────────────\n"
    "  OpenSearch Serverless (min 2 OCU × 24h × 30d × $0.24/OCU-hr)  →  ~$345 / mo   ← largest cost\n"
    "  Bedrock AgentCore Runtime  (compute + invocations, POC traffic) →  ~$50–100 / mo\n"
    "  Amazon Nova Pro  (~1M tokens/mo input+output)                   →  ~$5–15  / mo\n"
    "  Titan Embed Text v2  (~500K tokens/mo)                          →  ~$1–2   / mo\n"
    "  S3  (docs + storage)                                            →  ~$1–3   / mo\n"
    "  ECR  (image storage)                                            →  ~$1     / mo\n"
    "  CloudFormation / CDK / IAM                                      →  Free\n"
    "─────────────────────────────────────────────────────────────────────────────────────────────\n"
    "  TOTAL ESTIMATE                                                   →  ~$400–465 / mo\n"
    "  * Costs drop significantly if OpenSearch Serverless is replaced with a provisioned cluster.\n"
    "  * Production traffic will increase Nova Pro token costs proportionally.\n"
    "  * All figures in USD; ap-south-1 pricing as of mid-2025."
)

graph_attr = {
    "fontsize": "18",
    "bgcolor": "white",
    "pad": "1.0",
    "splines": "ortho",
    "nodesep": "0.9",
    "ranksep": "1.3",
    "fontname": "Helvetica",
    "label": COST_NOTE,
    "labelloc": "b",
    "labeljust": "l",
    "fontcolor": "#37474F",
}

node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica",
}

with Diagram(
    "BARTT AgentCore Architecture\nBroker Automated Reconciliation & Trade Tieout  ·  AWS ap-south-1",
    filename="BARTT_AgentCore_Architecture",
    outformat="png",
    show=False,
    direction="LR",
    graph_attr=graph_attr,
    node_attr=node_attr,
):

    analyst = Users("Business User\n(Trade Analyst / Ops)")
    dev     = User("Developer")

    # ── Local Docker UI ──────────────────────────────────────────────────────
    with Cluster("Local Docker  ·  localhost:8501"):
        streamlit = Docker("barttuiapp\n(Streamlit Chat UI)")

    # ── Developer Workstation ────────────────────────────────────────────────
    with Cluster("Developer Workstation"):
        agent_code = Python("barttagent\nmain.py (Strands Agent)")
        cli        = Rack("agentcore CLI\nagentcore deploy")

    # ── AWS Build & Registry ─────────────────────────────────────────────────
    with Cluster("AWS Build & Registry"):
        codebuild = Codebuild("AWS CodeBuild")
        ecr       = ECR("Amazon ECR\nbartt-agentcore")

    # ── AWS Cloud ap-south-1 ─────────────────────────────────────────────────
    with Cluster("AWS Cloud  (ap-south-1)"):

        # ── AgentCore Runtime ────────────────────────────────────────────────
        with Cluster(
            "Amazon Bedrock AgentCore Runtime\n"
            "barttagentcorerepo_barttagent-5qiZ7J3KGa\n"
            "POST /invocations · GET /ping · WS /ws"
        ):
            runtime  = Bedrock("AgentCore\nRuntime")
            nova_pro = SagemakerModel("Amazon Nova Pro\napac.amazon.nova-pro-v1:0\n(APAC inference profile)")

        # ── Knowledge Base / RAG ─────────────────────────────────────────────
        with Cluster("Knowledge Base / RAG"):
            kb        = Bedrock("Bedrock KB\nbartt-knowledge-base")
            oss       = OpenSearch("OpenSearch Serverless\nbartt-kb-vectors\n1024-dim HNSW/faiss")
            titan     = SagemakerModel("Titan Embed Text v2\n1024-dim embeddings")
            s3_bucket = S3("S3 Bucket\nbartt-kb-data-source\n(BART REQ Docs + xref JSON)")

        # ── IAM ──────────────────────────────────────────────────────────────
        iam_agent = IAMRole("Agent Execution Role\nbedrock:Retrieve\nbedrock:RetrieveAndGenerate")
        iam_kb    = IAMRole("KB Role\nbedrock:InvokeModel\naoss:APIAccessAll · s3:GetObject")

        # ── CDK Stack ────────────────────────────────────────────────────────
        cdk = GenericOfficeBuilding("CDK Stack (TypeScript)\nbartt-AgentCore-\nbarttagentcorerepo-default")

    # =========================================================================
    # DEPLOY FLOW  (gray dashed)
    # =========================================================================
    dev        >> deploy_edge("writes code")       >> agent_code
    dev        >> deploy_edge("agentcore deploy")  >> cli
    agent_code >> deploy_edge("packages into")     >> codebuild
    codebuild  >> deploy_edge("pushes image")      >> ecr
    ecr        >> deploy_edge("pulls & runs")      >> runtime
    cdk        >> deploy_edge("provisions")        >> runtime
    cdk        >> deploy_edge()                    >> kb
    cdk        >> deploy_edge()                    >> iam_agent
    cdk        >> deploy_edge()                    >> iam_kb

    # IAM grants (orange dashed)
    iam_agent  >> iam_edge("grants Retrieve")   >> kb
    iam_kb     >> iam_edge("grants API access") >> oss

    # S3 ingestion (one-time setup, gray dashed)
    s3_bucket  >> deploy_edge("ingestion job\n(one-time setup)") >> kb

    # =========================================================================
    # REQUEST FLOW  ➜  blue numbered  [1]→[2]→[3]→[4]→[5]→[6]→[7]
    # =========================================================================
    analyst   >> req(1, "Ask question")               >> streamlit
    streamlit >> req(2, "POST /invocations\n{prompt}") >> runtime
    runtime   >> req(3, "Invoke Strands Agent")        >> nova_pro
    runtime   >> req(4, "retrieve(query)")             >> kb
    kb        >> req(5, "Embed query")                 >> titan
    kb        >> req(6, "kNN vector search")           >> oss

    # =========================================================================
    # RESPONSE FLOW  ➜  green numbered  [7]→[8]→[9]→[10]
    # =========================================================================
    oss       >> res(7,  "Top-k chunks")               >> kb
    kb        >> res(8,  "Retrieved context")          >> runtime
    nova_pro  >> res(9,  "LLM generated answer")       >> runtime
    runtime   >> res(10, "SSE streaming chunks")       >> streamlit
    streamlit >> res(11, "Renders markdown response")  >> analyst

print("✅  BARTT_AgentCore_Architecture.png generated successfully.")

