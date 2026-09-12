"""Shared pytest fixtures for CareBridge tests."""

import os
from pathlib import Path

import pytest
from unittest.mock import patch


# Environment variables that select or configure an LLM provider.  Removed for
# every test (AGENTS.md §11: tests are hermetic) so the suite exercises the
# deterministic routing path and never issues a network call — even when the
# developer running pytest has a real API key exported in their shell.
# ``ENV_FILE`` is included so pydantic-settings never reads the project .env
# (which may contain real credentials) during tests.
_LLM_ENV_VARS: tuple[str, ...] = (
    "LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "BEDROCK_MODEL_ID",
    "AWS_REGION",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_MAX_TOKENS",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "LITELLM_MODEL",
    "ENV_FILE",
)


@pytest.fixture(autouse=True)
def hermetic_llm():
    """Force every test onto the deterministic fallback routing path.

    The Supervisor routes through a real LLM whenever ``LLM_PROVIDER`` resolves
    to a configured provider, and caches that decision (plus the constructed
    model and Agent) for the life of the process.  This fixture clears the
    provider environment and all three caches around each test so no test
    depends on ambient credentials, on another test's provider choice, or on
    network access.

    ``tests/test_llm_routing.py`` deliberately re-enables a provider with
    ``monkeypatch`` *after* this fixture has run, then resets the caches itself.
    """
    saved = {name: os.environ.get(name) for name in _LLM_ENV_VARS}
    for name in _LLM_ENV_VARS:
        os.environ.pop(name, None)
    # Point pydantic-settings at a non-existent env file so the project .env
    # (which may contain real credentials) is never read during tests.
    # model_config is mutable and pydantic-settings reads it at instantiation.
    _test_env_file = str(Path(__file__).parent / ".env.test.nonexistent")
    os.environ["ENV_FILE"] = _test_env_file
    from src.api.config import Settings
    _original_env_file = Settings.model_config.get("env_file", ".env")
    Settings.model_config["env_file"] = _test_env_file

    from src.api.config import get_settings
    from src.runtime.model_factory import reset_model_cache
    import src.agents.supervisor_agent as sup_mod

    get_settings.cache_clear()
    reset_model_cache()
    sup_mod.reset_supervisor_state()
    try:
        yield
    finally:
        Settings.model_config["env_file"] = _original_env_file
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        get_settings.cache_clear()
        reset_model_cache()
        sup_mod.reset_supervisor_state()


@pytest.fixture(autouse=True)
def temp_audit_db(tmp_path):
    """Patch the audit DB path to a temp file for every test and reset supervisor state.

    Python evaluates default parameter values at function-definition time, so
    ``db_path: str = DB_PATH`` is locked to the original ``"audit.db"`` string
    regardless of ``unittest.mock.patch`` on the module attribute.  We work
    around this by rewriting ``__defaults__`` on every audit_log function that
    has a ``db_path`` default parameter, so that *all* calls (with or without
    an explicit ``db_path=``) use the temp database.
    """
    db_path = str(tmp_path / "test_audit.db")

    from src.models.audit_log import init_audit_db, write_audit_event, get_audit_events

    # Create the schema + triggers at the temp path.
    init_audit_db(db_path)

    # Collect the functions whose __defaults__ we need to rewrite.
    audit_funcs = [write_audit_event, get_audit_events]

    # Save original defaults so we can restore them.
    original_defaults = {fn: fn.__defaults__ for fn in audit_funcs}

    # Rewrite defaults: replace any occurrence of the original DB_PATH string
    # ("audit.db") with the temp path.
    import src.models.audit_log as _al
    orig_db = _al.DB_PATH  # the original module-level value

    for fn in audit_funcs:
        if fn.__defaults__ is not None:
            fn.__defaults__ = tuple(
                db_path if d == orig_db else d for d in fn.__defaults__
            )

    with patch.object(_al, "DB_PATH", db_path):
        # Reset the supervisor's one-shot audit DB flag so _ensure_audit_db()
        # calls init_audit_db() (which now uses the patched DB_PATH).
        import src.agents.supervisor_agent as sup_mod
        original_flag = sup_mod._audit_db_initialized
        sup_mod._audit_db_initialized = False
        # Also clear the resolved-action cache so tests are independent.
        original_resolved = sup_mod._resolved_action_ids.copy()
        sup_mod._resolved_action_ids.clear()
        try:
            yield db_path
        finally:
            sup_mod._audit_db_initialized = original_flag
            sup_mod._resolved_action_ids.clear()
            sup_mod._resolved_action_ids.update(original_resolved)
            # Restore function defaults.
            for fn in audit_funcs:
                fn.__defaults__ = original_defaults[fn]
