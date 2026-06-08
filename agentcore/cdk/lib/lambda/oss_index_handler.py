"""Custom resource handler to create/delete an OpenSearch Serverless vector index.

Called by a CDK CustomResource during `agentcore deploy`.  Creates (or deletes)
the `bartt-kb-index` knn_vector index inside the OSS collection so that the
Bedrock Knowledge Base can store and query embeddings.

All HTTP requests are signed with AWS SigV4 using boto3 credentials from the
Lambda execution role.  No third-party packages are required.
"""

from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import urllib.error
import urllib.request

import boto3


# ── SigV4 helpers ─────────────────────────────────────────────────────────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _get_sig_key(secret: str, date_stamp: str, region: str, service: str) -> bytes:
    k = _sign(("AWS4" + secret).encode("utf-8"), date_stamp)
    k = _sign(k, region)
    k = _sign(k, service)
    return _sign(k, "aws4_request")


def _signed_request(
    method: str, host: str, path: str, body: str, region: str
) -> tuple[int, str]:
    """Make a SigV4-signed HTTP request to an OpenSearch Serverless endpoint."""
    creds = boto3.session.Session().get_credentials().get_frozen_credentials()
    t = datetime.datetime.utcnow()
    amzdate = t.strftime("%Y%m%dT%H%M%SZ")
    ds = t.strftime("%Y%m%d")

    payload_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    # Canonical headers — sorted alphabetically
    signed_hdrs = "content-type;host;x-amz-date"
    canon_hdrs = (
        f"content-type:application/json\n"
        f"host:{host}\n"
        f"x-amz-date:{amzdate}\n"
    )
    if creds.token:
        canon_hdrs += f"x-amz-security-token:{creds.token}\n"
        signed_hdrs += ";x-amz-security-token"

    canonical_request = (
        f"{method}\n{path}\n\n{canon_hdrs}\n{signed_hdrs}\n{payload_hash}"
    )

    credential_scope = f"{ds}/{region}/aoss/aws4_request"
    string_to_sign = (
        f"AWS4-HMAC-SHA256\n{amzdate}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    sig_key = _get_sig_key(creds.secret_key, ds, region, "aoss")
    signature = hmac.new(sig_key, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    auth_header = (
        f"AWS4-HMAC-SHA256 Credential={creds.access_key}/{credential_scope},"
        f" SignedHeaders={signed_hdrs}, Signature={signature}"
    )

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "x-amz-date": amzdate,
        "Authorization": auth_header,
    }
    if creds.token:
        headers["x-amz-security-token"] = creds.token

    req = urllib.request.Request(
        f"https://{host}{path}",
        data=body.encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# ── Lambda entry point ─────────────────────────────────────────────────────────

def handler(event: dict, context: object) -> dict:  # noqa: ARG001
    """CloudFormation custom resource handler.

    ResourceProperties expected:
      - Endpoint   : HTTPS endpoint of the OSS collection (e.g. "https://abc.aoss.amazonaws.com")
      - IndexName  : Name of the vector index to create (e.g. "bartt-kb-index")
      - Region     : AWS region (e.g. "ap-south-1")
    """
    props = event["ResourceProperties"]
    endpoint: str = props["Endpoint"]
    index_name: str = props["IndexName"]
    region: str = props["Region"]

    # Strip trailing slash / scheme from endpoint to get the host
    host = endpoint.replace("https://", "").rstrip("/")
    physical_id = f"{endpoint}/{index_name}"

    request_type: str = event["RequestType"]

    if request_type in ("Create", "Update"):
        index_body = json.dumps({
            "settings": {
                "index.knn": True,
            },
            "mappings": {
                "properties": {
                    "embedding": {
                        "type": "knn_vector",
                        "dimension": 1024,
                        "method": {
                            "engine": "faiss",
                            "space_type": "l2",
                            "name": "hnsw",
                        },
                    },
                    "text": {"type": "text"},
                    "metadata": {"type": "text"},
                },
            },
        })

        status, resp_body = _signed_request("PUT", host, f"/{index_name}", index_body, region)

        if status not in (200, 201):
            # 400 with "resource_already_exists_exception" is idempotent — allow it
            try:
                parsed = json.loads(resp_body)
            except (json.JSONDecodeError, ValueError):
                parsed = {}
            err_type = parsed.get("error", {}).get("type", "")
            if err_type != "resource_already_exists_exception":
                raise RuntimeError(
                    f"Failed to create OSS index '{index_name}': HTTP {status}: {resp_body}"
                )

    elif request_type == "Delete":
        # Best-effort deletion — 404 is fine (already gone)
        _signed_request("DELETE", host, f"/{index_name}", "", region)

    return {"PhysicalResourceId": physical_id}
