import os

from strands.models.bedrock import BedrockModel


# APAC system-defined inference profile for Nova Pro (covers ap-south-1 and
# other APAC regions).  The bare model ID "amazon.nova-pro-v1:0" cannot be
# used with on-demand throughput in ap-south-1; an inference profile is
# required.  Override via BEDROCK_INFERENCE_PROFILE_ID or BEDROCK_MODEL_ID.
DEFAULT_NOVA_MODEL_ID = "apac.amazon.nova-pro-v1:0"


def load_model() -> BedrockModel:
    """Get Bedrock model client using IAM credentials.

    Uses the APAC Nova Pro inference profile by default (required for
    ap-south-1 on-demand throughput).  Override with:
      BEDROCK_INFERENCE_PROFILE_ID – inference profile ID or ARN (highest priority)
      BEDROCK_MODEL_ID             – any model/profile ID
    """
    model_id = (
        os.getenv("BEDROCK_INFERENCE_PROFILE_ID")
        or os.getenv("BEDROCK_MODEL_ID")
        or DEFAULT_NOVA_MODEL_ID
    )
    return BedrockModel(model_id=model_id)

