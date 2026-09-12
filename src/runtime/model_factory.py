"""Provider-agnostic LLM model factory for CareBridge.

The Supervisor Agent is driven by whichever LLM the deployment configures,
selected at runtime from the ``LLM_PROVIDER`` environment variable. No provider
SDK is imported at module load: each adapter is imported lazily inside
:func:`get_model` so a missing optional dependency can never break the API, the
demo, or the test suite when that provider is not in use.

Failure contract (AGENTS.md §9 — never silently fail):

- provider not supported        -> ``RuntimeError`` listing supported values
- provider SDK not installed    -> ``RuntimeError`` with the exact ``pip install``
- provider credentials missing  -> ``RuntimeError`` naming the exact env var

Callers that must keep running without an LLM (offline tests, a demo with no API
key, read-only API routes) catch ``RuntimeError`` and use the deterministic
fallback path — see ``src/agents/supervisor_agent.py``.

Security (AGENTS.md §10): credentials are read from the environment and are
NEVER logged. Only the provider name and model id appear in log output, and the
cache fingerprint stores a non-reversible digest rather than the key itself.

Adapter note (verified against strands-agents 1.55.1): provider credentials are
passed via ``client_args=``, not as model-config kwargs. ``GeminiModel`` and
``OpenAIModel`` validate their ``**model_config`` keys and would silently drop
an ``api_key=`` kwarg (Strands emits "Invalid configuration parameters" and
continues without credentials), so ``client_args`` is mandatory here.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
from typing import TYPE_CHECKING, Any, Callable, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from strands.models import Model

logger = logging.getLogger(__name__)

# Groq exposes an OpenAI-compatible API, so it is served by the OpenAI adapter
# with an overridden base_url (no separate SDK needed).
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Substrings that identify an unfilled .env.example template rather than a real
# secret. See :func:`is_placeholder_credential`.
_PLACEHOLDER_MARKERS: tuple[str, ...] = (
    "your-",
    "change-me",
    "changeme",
    "replace-me",
    "placeholder",
)

SUPPORTED_PROVIDERS: tuple[str, ...] = (
    "gemini",
    "groq",
    "bedrock",
    "anthropic",
    "openai",
    "ollama",
    "litellm",
)

# Settings field name -> environment variable name. Configuration is read from
# ``src.api.config.Settings`` when importable (it also loads ``.env``) and from
# the raw environment otherwise, so this module never hard-depends on the API
# layer being configured.
_ENV_VARS: dict[str, str] = {
    "llm_provider": "LLM_PROVIDER",
    "gemini_api_key": "GEMINI_API_KEY",
    "gemini_model": "GEMINI_MODEL",
    "groq_api_key": "GROQ_API_KEY",
    "groq_model": "GROQ_MODEL",
    "bedrock_model_id": "BEDROCK_MODEL_ID",
    "aws_region": "AWS_REGION",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
    "anthropic_model": "ANTHROPIC_MODEL",
    "anthropic_max_tokens": "ANTHROPIC_MAX_TOKENS",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL",
    "ollama_host": "OLLAMA_HOST",
    "ollama_model": "OLLAMA_MODEL",
    "litellm_model": "LITELLM_MODEL",
}

# Documented defaults, mirroring src/api/config.py. Applied when a value is
# absent or blank so both configuration paths resolve identically.
_DEFAULTS: dict[str, Any] = {
    "llm_provider": "gemini",
    "gemini_model": "gemini-3.6-flash",
    "groq_model": "llama-3.3-70b-versatile",
    "bedrock_model_id": "anthropic.claude-sonnet-4-20250514-v1:0",
    "aws_region": "us-east-1",
    "anthropic_model": "claude-sonnet-4-20250514",
    "anthropic_max_tokens": 4096,
    "openai_model": "gpt-4o-mini",
    "ollama_host": "http://localhost:11434",
    "ollama_model": "llama3.1:8b",
}

# Model construction is serialised and the instance cached, so a provider SDK is
# imported and configured once per process rather than per request.
_model_lock = threading.Lock()
_cached_model: Optional[Any] = None
_cached_fingerprint: Optional[str] = None


# ---------------------------------------------------------------------------
# Configuration resolution
# ---------------------------------------------------------------------------

def _load_config() -> dict[str, Any]:
    """Resolve LLM provider configuration from Settings or the environment.

    Returns:
        Dict of every field in :data:`_ENV_VARS` with defaults applied and
        ``llm_provider`` normalised to lowercase.
    """
    config: dict[str, Any] = {}
    try:
        from src.api.config import get_settings

        settings = get_settings()
        config = {name: getattr(settings, name, None) for name in _ENV_VARS}
    except ImportError as exc:
        # The API layer is optional for non-HTTP entrypoints (e.g. main.py).
        logger.debug("Reading LLM config from environment: %s", exc)
        config = {name: os.environ.get(env) for name, env in _ENV_VARS.items()}
    except Exception as exc:
        # Never silently fall back on an unexpected settings failure (AGENTS.md §3).
        logger.warning(
            "Falling back to raw environment for LLM config (%s: %s)",
            type(exc).__name__, exc,
        )
        config = {name: os.environ.get(env) for name, env in _ENV_VARS.items()}

    resolved: dict[str, Any] = dict(_DEFAULTS)
    for name, value in config.items():
        if value is not None and str(value).strip() != "":
            resolved[name] = value
    resolved["llm_provider"] = str(resolved["llm_provider"]).strip().lower()
    return resolved


def is_placeholder_credential(value: Any) -> bool:
    """Return True when a credential is an unfilled ``.env.example`` template.

    ``.env.example`` ships values such as ``your-gemini-api-key``.  Every Strands
    adapter constructs successfully offline, so a copied-but-unedited template
    would otherwise report the LLM as available and then fail with an opaque 401
    at inference time.  Detecting the template turns that into an actionable
    startup message instead (AGENTS.md §9 — never silently fail).

    The markers are chosen so they cannot occur inside a real provider key
    (Gemini/Groq/OpenAI/Anthropic keys are alphanumeric with ``-`` and ``_``).

    Args:
        value: The raw credential value.

    Returns:
        True when the value looks like a placeholder rather than a secret.
    """
    if value is None:
        return True
    text = str(value).strip().lower()
    if not text:
        return True
    if text.startswith("<") and text.endswith(">"):
        return True
    return any(marker in text for marker in _PLACEHOLDER_MARKERS)


def _require_credential(
    provider: str, config: dict[str, Any], field: str, env_var: str
) -> str:
    """Return a required credential or raise a RuntimeError naming the env var.

    Args:
        provider: The provider being built (used in the error message).
        config: Resolved configuration from :func:`_load_config`.
        field: Configuration field holding the credential.
        env_var: Environment variable name to report to the operator.

    Returns:
        The trimmed, non-empty credential value.

    Raises:
        RuntimeError: If the credential is missing, blank, or still a template.
    """
    value = config.get(field)
    if is_placeholder_credential(value):
        raise RuntimeError(
            f"LLM_PROVIDER='{provider}' is configured but {env_var} is missing. "
            f"Set {env_var} in your .env file (never commit it), or switch "
            f"LLM_PROVIDER to a provider you have credentials for."
        )
    return str(value).strip()


def _import_adapter(provider: str, class_name: str, package: str) -> Any:
    """Lazily import a Strands model adapter class.

    Args:
        provider: Provider name, for the error message.
        class_name: Adapter class name on ``strands.models``.
        package: Distribution to install when the adapter's SDK is absent.

    Returns:
        The adapter class (not an instance).

    Raises:
        RuntimeError: If the adapter or its underlying SDK is not installed.
    """
    try:
        from strands import models as strands_models

        return getattr(strands_models, class_name)
    except ImportError as exc:
        raise RuntimeError(
            f"LLM_PROVIDER='{provider}' needs the Strands {class_name} adapter, "
            f"which requires the '{package}' package. Install with: "
            f"pip install {package}"
        ) from exc
    except AttributeError as exc:
        raise RuntimeError(
            f"LLM_PROVIDER='{provider}': the installed strands-agents version does "
            f"not expose {class_name}. Upgrade with: pip install -U strands-agents"
        ) from exc


def _ensure_aws_credentials() -> None:
    """Verify AWS credentials are discoverable without touching the network.

    Raises:
        RuntimeError: If boto3 cannot resolve any credentials.
    """
    # boto3 falls back to the EC2 instance metadata service, which blocks for
    # seconds when running off-cloud. Disable it for the probe so a missing
    # credential fails fast instead of hanging startup or the test suite.
    prior = os.environ.get("AWS_EC2_METADATA_DISABLED")
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    try:
        import boto3

        credentials = boto3.Session().get_credentials()
    except ImportError as exc:
        raise RuntimeError(
            "LLM_PROVIDER='bedrock' requires boto3. Install with: pip install boto3"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"LLM_PROVIDER='bedrock' could not resolve AWS credentials "
            f"({type(exc).__name__}: {exc})."
        ) from exc
    finally:
        if prior is None:
            os.environ.pop("AWS_EC2_METADATA_DISABLED", None)
        else:
            os.environ["AWS_EC2_METADATA_DISABLED"] = prior

    if credentials is None:
        raise RuntimeError(
            "LLM_PROVIDER='bedrock' is configured but no AWS credentials were found. "
            "Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY (plus AWS_SESSION_TOKEN "
            "for temporary credentials), or configure an AWS profile / IAM role."
        )


# ---------------------------------------------------------------------------
# Provider builders — each returns (model instance, model_id)
# ---------------------------------------------------------------------------

def _build_gemini(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the Google Gemini adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (GeminiModel instance, model_id).

    Raises:
        RuntimeError: If GEMINI_API_KEY is missing or google-genai is absent.
    """
    api_key = _require_credential("gemini", config, "gemini_api_key", "GEMINI_API_KEY")
    model_id = str(config["gemini_model"])
    gemini_model = _import_adapter("gemini", "GeminiModel", "google-genai")
    return gemini_model(client_args={"api_key": api_key}, model_id=model_id), model_id


def _build_openai_compatible(
    config: dict[str, Any],
    provider: str,
    key_field: str,
    key_env: str,
    model_field: str,
    base_url: Optional[str] = None,
) -> tuple[Any, str]:
    """Build an OpenAI-compatible adapter (OpenAI itself, Groq, OpenRouter).

    Args:
        config: Resolved configuration.
        provider: Provider name for error messages.
        key_field: Configuration field holding the API key.
        key_env: Environment variable name to report when the key is missing.
        model_field: Configuration field holding the model id.
        base_url: Optional override of the OpenAI-compatible endpoint.

    Returns:
        Tuple of (OpenAIModel instance, model_id).

    Raises:
        RuntimeError: If the API key is missing or the openai package is absent.
    """
    api_key = _require_credential(provider, config, key_field, key_env)
    model_id = str(config[model_field])
    openai_model = _import_adapter(provider, "OpenAIModel", "openai")
    client_args: dict[str, Any] = {"api_key": api_key}
    if base_url:
        client_args["base_url"] = base_url
    return openai_model(client_args=client_args, model_id=model_id), model_id


def _build_groq(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the Groq adapter via the OpenAI-compatible endpoint.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (OpenAIModel instance, model_id).

    Raises:
        RuntimeError: If GROQ_API_KEY is missing or the openai package is absent.
    """
    return _build_openai_compatible(
        config, "groq", "groq_api_key", "GROQ_API_KEY", "groq_model",
        base_url=GROQ_BASE_URL,
    )


def _build_openai(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the OpenAI adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (OpenAIModel instance, model_id).

    Raises:
        RuntimeError: If OPENAI_API_KEY is missing or the openai package is absent.
    """
    return _build_openai_compatible(
        config, "openai", "openai_api_key", "OPENAI_API_KEY", "openai_model"
    )


def _build_bedrock(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the Amazon Bedrock adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (BedrockModel instance, model_id).

    Raises:
        RuntimeError: If boto3 is absent or no AWS credentials are discoverable.
    """
    region = str(config["aws_region"])
    model_id = str(config["bedrock_model_id"])
    bedrock_model = _import_adapter("bedrock", "BedrockModel", "boto3")
    _ensure_aws_credentials()
    return bedrock_model(region_name=region, model_id=model_id), model_id


def _build_anthropic(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the Anthropic adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (AnthropicModel instance, model_id).

    Raises:
        RuntimeError: If ANTHROPIC_API_KEY is missing or anthropic is absent.
    """
    api_key = _require_credential(
        "anthropic", config, "anthropic_api_key", "ANTHROPIC_API_KEY"
    )
    model_id = str(config["anthropic_model"])
    anthropic_model = _import_adapter("anthropic", "AnthropicModel", "anthropic")
    return (
        anthropic_model(
            client_args={"api_key": api_key},
            model_id=model_id,
            # Strands types max_tokens as Required for Anthropic; set it
            # explicitly rather than depending on a provider-side default.
            max_tokens=int(config["anthropic_max_tokens"]),
        ),
        model_id,
    )


def _build_ollama(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the local Ollama adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (OllamaModel instance, model_id).

    Raises:
        RuntimeError: If the ollama package is absent.
    """
    host = str(config["ollama_host"])
    model_id = str(config["ollama_model"])
    ollama_model = _import_adapter("ollama", "OllamaModel", "ollama")
    # OllamaModel takes host as a positional argument.
    return ollama_model(host, model_id=model_id), model_id


def _build_litellm(config: dict[str, Any]) -> tuple[Any, str]:
    """Build the LiteLLM universal adapter.

    Args:
        config: Resolved configuration.

    Returns:
        Tuple of (LiteLLMModel instance, model_id).

    Raises:
        RuntimeError: If LITELLM_MODEL is missing or litellm is absent.
    """
    raw_model = config.get("litellm_model")
    if not raw_model or not str(raw_model).strip():
        raise RuntimeError(
            "LLM_PROVIDER='litellm' requires LITELLM_MODEL in provider-prefixed "
            "form (e.g. 'gemini/gemini-2.5-flash', 'openai/gpt-4o-mini', "
            "'anthropic/claude-sonnet-4-20250514')."
        )
    model_id = str(raw_model).strip()
    litellm_model = _import_adapter("litellm", "LiteLLMModel", "litellm")
    return litellm_model(model_id=model_id), model_id


_BUILDERS: dict[str, Callable[[dict[str, Any]], tuple[Any, str]]] = {
    "gemini": _build_gemini,
    "groq": _build_groq,
    "bedrock": _build_bedrock,
    "anthropic": _build_anthropic,
    "openai": _build_openai,
    "ollama": _build_ollama,
    "litellm": _build_litellm,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_provider_name() -> str:
    """Return the configured LLM provider name for introspection.

    Used by ``GET /ready`` so an operator can see which provider a deployment
    resolved to. Never raises: an unsupported value is returned as configured so
    the readiness payload reflects reality.

    Returns:
        Lowercase provider name (e.g. ``"gemini"``).
    """
    return str(_load_config()["llm_provider"])


def get_configured_model_id() -> Optional[str]:
    """Return the model id the configured provider would use.

    Returns:
        The resolved model id, or None when the provider is unknown or its model
        id is not configured (e.g. ``litellm`` without ``LITELLM_MODEL``).
    """
    config = _load_config()
    provider = str(config["llm_provider"])
    model_field = {
        "gemini": "gemini_model",
        "groq": "groq_model",
        "bedrock": "bedrock_model_id",
        "anthropic": "anthropic_model",
        "openai": "openai_model",
        "ollama": "ollama_model",
        "litellm": "litellm_model",
    }.get(provider)
    if model_field is None:
        return None
    value = config.get(model_field)
    return str(value) if value else None


def _fingerprint(provider: str, config: dict[str, Any]) -> str:
    """Build a cache key that changes when the effective configuration changes.

    Credentials are represented by a non-reversible digest so a rotated key
    invalidates the cache without the secret being stored in a module global.

    Args:
        provider: Normalised provider name.
        config: Resolved configuration.

    Returns:
        Hex digest identifying the effective configuration.
    """
    parts: list[str] = [provider]
    for name in sorted(_ENV_VARS):
        value = config.get(name)
        if value is None:
            continue
        text = str(value)
        if name.endswith("_api_key"):
            text = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        parts.append(f"{name}={text}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def get_model() -> "Model":
    """Return the configured LLM adapter, constructing and caching it on demand.

    The provider is selected by ``LLM_PROVIDER`` and its adapter is imported
    lazily, so unrelated provider SDKs are never loaded. The instance is cached
    behind a lock and rebuilt only when the effective configuration changes.

    Returns:
        A ``strands.models.Model`` adapter instance for the configured provider.

    Raises:
        RuntimeError: If ``LLM_PROVIDER`` is unsupported, the provider's SDK is
            not installed, or its credentials are missing. The message names the
            exact package to install or environment variable to set.
    """
    global _cached_model, _cached_fingerprint

    config = _load_config()
    provider = str(config["llm_provider"])

    builder = _BUILDERS.get(provider)
    if builder is None:
        raise RuntimeError(
            f"Unsupported LLM_PROVIDER='{provider}'. Supported providers: "
            f"{', '.join(SUPPORTED_PROVIDERS)}."
        )

    fingerprint = _fingerprint(provider, config)
    with _model_lock:
        if _cached_model is not None and _cached_fingerprint == fingerprint:
            return _cached_model

        model, model_id = builder(config)
        _cached_model = model
        _cached_fingerprint = fingerprint
        # Provider name and model id only — never the API key (AGENTS.md §10).
        logger.info("LLM provider: %s, model: %s", provider, model_id)
        return model


def is_llm_available() -> bool:
    """Return True if the configured provider can build a model adapter.

    Construction is offline (no inference request is issued), so this is safe to
    call from a readiness probe. Failures are logged at DEBUG to avoid flooding
    the log when a probe polls a deployment that intentionally runs without an
    LLM; the one-time operator-facing WARNING is emitted by settings validation.

    Returns:
        True when :func:`get_model` succeeds, False otherwise.
    """
    try:
        get_model()
        return True
    except Exception as exc:
        logger.debug(
            "LLM adapter unavailable (provider=%s): %s", get_provider_name(), exc
        )
        return False


def reset_model_cache() -> None:
    """Drop the cached model instance.

    Used by tests that change provider configuration between cases; a production
    process rebuilds automatically when the fingerprint changes.

    Returns:
        None.
    """
    global _cached_model, _cached_fingerprint
    with _model_lock:
        _cached_model = None
        _cached_fingerprint = None
