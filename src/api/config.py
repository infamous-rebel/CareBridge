"""Runtime configuration for the CareBridge API (pydantic-settings).

All secrets come from the environment / ``.env`` — never hardcoded. Guardrail J
is enforced here at settings-load time:

- ``JWT_SECRET`` must be present and >= 32 bytes when ``DEMO_MODE=false``.
- ``BCRYPT_ROUNDS`` must be >= 12 when ``DEMO_MODE=false``.

In ``DEMO_MODE`` a clearly-flagged development fallback secret and a low bcrypt
cost are permitted so the stack boots for a hackathon demo without a ``.env``.

LLM provider selection (``LLM_PROVIDER`` and its per-provider settings) is
resolved here so the whole stack shares one source of truth; the adapters are
built by ``src/runtime/model_factory.py``. A provider missing its credential is
a WARNING, never a crash: the app must still serve ``/health`` and the read-only
routes, while LLM-dependent routes degrade to 503.
"""

import logging
import os
from functools import lru_cache
from typing import Optional

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

# Development-only fallback. Clearly flagged; refused in non-demo mode by the
# validator below. Never use in production.
_DEV_FALLBACK_SECRET = "carebridge-dev-only-insecure-secret-change-me"

MIN_JWT_SECRET_BYTES = 32
MIN_BCRYPT_ROUNDS = 12

# Provider -> the environment variable that must be present for it to work.
# ``bedrock`` authenticates through the AWS credential chain (checked at adapter
# build time) and ``ollama`` is local, so neither has a single API-key variable.
LLM_PROVIDER_CREDENTIAL_VARS: dict[str, str] = {
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "litellm": "LITELLM_MODEL",
}


class Settings(BaseSettings):
    """Application settings loaded from environment variables / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App identity -------------------------------------------------------
    app_name: str = "CareBridge API"
    app_version: str = "1.0.0"
    environment: str = Field(
        default="development",
        validation_alias=AliasChoices("ENVIRONMENT", "APP_ENV", "ENV"),
    )

    # --- Demo bootstrap -----------------------------------------------------
    demo_mode: bool = Field(
        default=True,
        validation_alias=AliasChoices("DEMO_MODE",),
    )
    demo_user_email: str = Field(
        default="demo@carebridge.local",
        validation_alias=AliasChoices("DEMO_USER_EMAIL",),
    )
    demo_user_password: str = Field(
        default="CareBridgeDemo!2026",
        validation_alias=AliasChoices("DEMO_USER_PASSWORD",),
    )
    demo_user_role: str = Field(
        default="caregiver_primary",
        validation_alias=AliasChoices("DEMO_USER_ROLE",),
    )

    # --- Auth / JWT ---------------------------------------------------------
    jwt_secret_key: str = Field(
        default=_DEV_FALLBACK_SECRET,
        validation_alias=AliasChoices("JWT_SECRET_KEY", "JWT_SECRET"),
    )
    jwt_algorithm: str = Field(
        default="HS256",
        validation_alias=AliasChoices("JWT_ALGORITHM",),
    )
    access_token_expire_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("ACCESS_TOKEN_EXPIRE_MINUTES",),
    )
    refresh_token_expire_days: int = Field(
        default=7,
        validation_alias=AliasChoices("REFRESH_TOKEN_EXPIRE_DAYS",),
    )
    bcrypt_rounds: int = Field(
        default=12,
        validation_alias=AliasChoices("BCRYPT_ROUNDS",),
    )

    # --- CORS ---------------------------------------------------------------
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000"],
        validation_alias=AliasChoices("CORS_ORIGINS",),
    )

    # --- Persistence --------------------------------------------------------
    auth_db_path: str = Field(
        default="auth.db",
        validation_alias=AliasChoices("AUTH_DB_PATH",),
    )
    audit_db_path: str = Field(
        default="audit.db",
        validation_alias=AliasChoices("AUDIT_DB_PATH",),
    )

    # --- Rate limiting ------------------------------------------------------
    auth_rate_limit: str = Field(
        default="60/minute",
        validation_alias=AliasChoices("AUTH_RATE_LIMIT",),
    )
    global_rate_limit: str = Field(
        default="300/minute",
        validation_alias=AliasChoices("GLOBAL_RATE_LIMIT",),
    )

    # --- Observability / hardening -----------------------------------------
    json_logging: bool = Field(
        default=True,
        validation_alias=AliasChoices("JSON_LOGGING",),
    )
    log_level: str = Field(
        default="INFO",
        validation_alias=AliasChoices("LOG_LEVEL",),
    )
    max_request_bytes: int = Field(
        default=1_048_576,  # 1 MB
        validation_alias=AliasChoices("MAX_REQUEST_BYTES",),
    )

    # --- LLM provider (provider-agnostic; see src/runtime/model_factory.py) --
    # Only the provider named by LLM_PROVIDER has its adapter imported, so the
    # remaining settings are inert defaults and need no credentials.
    llm_provider: str = Field(
        default="gemini",
        validation_alias=AliasChoices("LLM_PROVIDER",),
    )

    # Google Gemini — free tier, no credit card required.
    gemini_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY",),
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        validation_alias=AliasChoices("GEMINI_MODEL",),
    )

    # Groq — OpenAI-compatible endpoint, free tier.
    groq_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("GROQ_API_KEY",),
    )
    groq_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias=AliasChoices("GROQ_MODEL",),
    )

    # Amazon Bedrock — credentials come from the AWS chain, not a single key.
    bedrock_model_id: str = Field(
        default="anthropic.claude-sonnet-4-20250514-v1:0",
        validation_alias=AliasChoices("BEDROCK_MODEL_ID",),
    )
    aws_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices("AWS_REGION",),
    )

    # Anthropic direct API.
    anthropic_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY",),
    )
    anthropic_model: str = Field(
        default="claude-sonnet-4-20250514",
        validation_alias=AliasChoices("ANTHROPIC_MODEL",),
    )
    # Strands types max_tokens as Required for the Anthropic adapter, so it is
    # configured explicitly rather than left to a provider-side default.
    anthropic_max_tokens: int = Field(
        default=4096,
        validation_alias=AliasChoices("ANTHROPIC_MAX_TOKENS",),
    )

    # OpenAI (also serves OpenRouter via the same adapter).
    openai_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY",),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL",),
    )

    # Local Ollama — no credentials.
    ollama_host: str = Field(
        default="http://localhost:11434",
        validation_alias=AliasChoices("OLLAMA_HOST",),
    )
    ollama_model: str = Field(
        default="llama3.1:8b",
        validation_alias=AliasChoices("OLLAMA_MODEL",),
    )

    # LiteLLM universal fallback — model id in provider-prefixed form.
    litellm_model: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("LITELLM_MODEL",),
    )

    # --- Firebase Authentication (hybrid identity) ----------------------------
    # Firebase handles identity (Google sign-in, email/password); the FastAPI
    # backend issues business-claim JWTs and owns authorization.  When
    # FIREBASE_AUTH_ENABLED=false (default) the Firebase endpoints return 503
    # and the frontend hides the Google button.
    firebase_project_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("FIREBASE_PROJECT_ID",),
    )
    firebase_service_account_path: str = Field(
        default="secrets/firebase-service-account.json",
        validation_alias=AliasChoices("FIREBASE_SERVICE_ACCOUNT_PATH",),
    )
    firebase_credentials_json: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("FIREBASE_CREDENTIALS_JSON",),
    )
    firebase_auth_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices("FIREBASE_AUTH_ENABLED",),
    )

    # --- Build metadata (injected by Docker/CI) -----------------------------
    build_git_sha: str = Field(
        default="dev",
        validation_alias=AliasChoices("BUILD_GIT_SHA", "GIT_SHA"),
    )
    build_timestamp: str = Field(
        default="",
        validation_alias=AliasChoices("BUILD_TIMESTAMP",),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_cors(cls, value: object) -> object:
        """Accept ``CORS_ORIGINS`` as a comma-separated string or a JSON list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_guardrails(self) -> "Settings":
        """Fail fast on insecure configuration outside demo mode (guardrail J)."""
        if not self.demo_mode:
            secret_bytes = len(self.jwt_secret_key.encode("utf-8"))
            if self.jwt_secret_key == _DEV_FALLBACK_SECRET:
                raise ValueError(
                    "JWT_SECRET/JWT_SECRET_KEY must be set when DEMO_MODE=false."
                )
            if secret_bytes < MIN_JWT_SECRET_BYTES:
                raise ValueError(
                    f"JWT secret must be >= {MIN_JWT_SECRET_BYTES} bytes "
                    f"(got {secret_bytes}) when DEMO_MODE=false."
                )
            if self.bcrypt_rounds < MIN_BCRYPT_ROUNDS:
                raise ValueError(
                    f"BCRYPT_ROUNDS must be >= {MIN_BCRYPT_ROUNDS} "
                    f"(got {self.bcrypt_rounds}) when DEMO_MODE=false."
                )
        self._warn_on_missing_llm_credentials()
        return self

    def _warn_on_missing_llm_credentials(self) -> None:
        """Log a WARNING when the selected LLM provider cannot authenticate.

        Deliberately non-fatal (spec C): the API must still boot so ``/health``,
        ``/ready`` and the read-only routes serve traffic, while LLM-dependent
        routes return 503 with a clear reason.

        Returns:
            None.
        """
        provider = (self.llm_provider or "").strip().lower()

        # Imported lazily so settings validation never depends on the runtime
        # package being importable.
        try:
            from src.runtime.model_factory import (
                SUPPORTED_PROVIDERS,
                is_placeholder_credential,
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("LLM provider list unavailable: %s", exc)
            SUPPORTED_PROVIDERS = ()

            def is_placeholder_credential(value: object) -> bool:
                """Local stand-in: only treat empty values as missing."""
                return not value or not str(value).strip()

        if SUPPORTED_PROVIDERS and provider not in SUPPORTED_PROVIDERS:
            logger.warning(
                "LLM_PROVIDER='%s' is not supported (expected one of: %s). "
                "LLM-dependent routes will return 503 until this is corrected.",
                provider, ", ".join(SUPPORTED_PROVIDERS),
            )
            return

        required_var = LLM_PROVIDER_CREDENTIAL_VARS.get(provider)
        if required_var is None:
            # bedrock authenticates via the AWS credential chain (verified when
            # the adapter is built) and ollama is local — no API key to check.
            return

        # Invariant: every entry in LLM_PROVIDER_CREDENTIAL_VARS is the uppercase
        # form of a Settings field name, so the value resolves by lowercasing.
        credential = getattr(self, required_var.lower(), None)
        if is_placeholder_credential(credential):
            logger.warning(
                "LLM_PROVIDER='%s' is set but %s is missing — the app will start, "
                "but LLM-dependent routes will return 503 and the Supervisor will "
                "use its deterministic fallback. Set %s in .env to enable LLM "
                "routing.",
                provider, required_var, required_var,
            )


@lru_cache
def get_settings() -> Settings:
    """Return the cached :class:`Settings` singleton.

    Cached so environment parsing happens once; tests clear the cache
    (``get_settings.cache_clear()``) after mutating ``os.environ``.
    """
    return Settings()


def firebase_is_configured() -> bool:
    """Return True when Firebase Auth is enabled and a project ID is set.

    This is a convenience helper for routers that need to decide whether to
    serve Firebase endpoints or return 503.  It does NOT guarantee that the
    service account file is valid — that is checked lazily by
    :func:`src.api.firebase_auth.init_firebase`.
    """
    settings = get_settings()
    return bool(settings.firebase_auth_enabled and settings.firebase_project_id)
