"""CareBridge runtime integrations.

Exposes the Qoder runtime client factory, which attaches the in-process MCP
server registry to a ``QoderSDKClient`` via ``QoderAgentOptions``, and the
provider-agnostic LLM model factory that selects the Strands adapter named by
``LLM_PROVIDER``.
"""

from src.runtime.model_factory import (
    SUPPORTED_PROVIDERS,
    get_configured_model_id,
    get_model,
    get_provider_name,
    is_llm_available,
    reset_model_cache,
)
from src.runtime.qoder_client import (
    create_qoder_client,
    get_qoder_client,
    reset_qoder_client,
)

__all__ = [
    "create_qoder_client",
    "get_qoder_client",
    "reset_qoder_client",
    "get_model",
    "get_provider_name",
    "get_configured_model_id",
    "is_llm_available",
    "reset_model_cache",
    "SUPPORTED_PROVIDERS",
]
