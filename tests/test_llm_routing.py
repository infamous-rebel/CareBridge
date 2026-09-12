"""Proof that the Supervisor's routing decision is made by a real LLM (spec G).

Three questions this file answers:

1. When a provider is configured, is the Supervisor built with a *real* model
   adapter and are all four specialists attached as tools the model can choose
   from — with no leftover ``if event_type == ...`` dispatch in the source?
2. When no provider is configured, does everything degrade gracefully instead
   of crashing?
3. Can a customer swap providers by changing an environment variable alone,
   with no code change?

A fourth test closes the loop that the first three cannot: it drives
``process_event()`` with a fake ``Model.stream`` and shows the route taken
follows the *model's* tool choice rather than the deterministic fallback table.

Hermeticity: the root ``conftest.py`` clears every provider variable before each
test, so each case here re-enables what it needs via ``monkeypatch`` and then
drops the settings / model / supervisor caches that memoise those variables.
Adapter construction is offline — no test issues an inference request. The only
test that exercises the inference call uses :class:`_FakeModel`.
"""

import ast
import re
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import pytest
from strands.models import Model

from src.agents import supervisor_agent as sup_mod
from src.agents.supervisor_agent import (
    create_supervisor_agent,
    get_routing_mode,
    get_supervisor_tool_names,
    process_event,
    reset_supervisor_state,
)
from src.api.config import get_settings
from src.models.audit_log import get_audit_events
from src.models.schemas import CareEvent, ResolutionResult
from src.runtime.model_factory import (
    SUPPORTED_PROVIDERS,
    get_configured_model_id,
    get_model,
    get_provider_name,
    reset_model_cache,
)

SUPERVISOR_SOURCE = (
    Path(__file__).resolve().parent.parent / "src" / "agents" / "supervisor_agent.py"
)

# The four specialists the Supervisor must expose to the LLM as tools.
EXPECTED_SPECIALISTS = [
    "CareBridgeMedication",
    "CareBridgeAppointment",
    "CareBridgeLogistics",
    "CareBridgeCommunication",
]

# Every variable the root hermetic_llm fixture clears. Redeclared here so the
# "no LLM" test is explicit about what it removes rather than relying on the
# fixture having already done it.
ALL_PROVIDER_ENV_VARS = (
    "LLM_PROVIDER",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "GROQ_API_KEY",
    "GROQ_MODEL",
    "BEDROCK_MODEL_ID",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "ANTHROPIC_MAX_TOKENS",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "OLLAMA_HOST",
    "OLLAMA_MODEL",
    "LITELLM_MODEL",
)

# A syntactically plausible, non-functional key. Adapter construction is offline
# so it is never sent anywhere, and is_placeholder_credential() must accept it
# (it only rejects obvious .env.example templates such as "your-gemini-api-key").
DUMMY_GEMINI_KEY = "AIzaSyTEST-ROUTING-PROBE-0000000000"

# Clearly not credentials: boto3 only needs *something* resolvable to construct
# a client offline, and no request is ever made.
DUMMY_AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7TESTONLY"
DUMMY_AWS_SECRET_ACCESS_KEY = "test-only-secret-not-a-real-credential"

# provider -> (env vars to set, expected Strands adapter class name)
PROVIDER_MATRIX: dict[str, tuple[dict[str, str], str]] = {
    "gemini": ({"GEMINI_API_KEY": DUMMY_GEMINI_KEY}, "GeminiModel"),
    "groq": ({"GROQ_API_KEY": "gsk-test-only-not-a-real-key"}, "OpenAIModel"),
    "bedrock": (
        {
            "AWS_REGION": "us-east-1",
            "AWS_ACCESS_KEY_ID": DUMMY_AWS_ACCESS_KEY_ID,
            "AWS_SECRET_ACCESS_KEY": DUMMY_AWS_SECRET_ACCESS_KEY,
        },
        "BedrockModel",
    ),
    "anthropic": (
        {"ANTHROPIC_API_KEY": "sk-ant-test-only-not-a-real-key"},
        "AnthropicModel",
    ),
}


def _reset_caches() -> None:
    """Drop every cache that memoises provider configuration."""
    get_settings.cache_clear()
    reset_model_cache()
    reset_supervisor_state()


def _configure(monkeypatch: pytest.MonkeyPatch, **env: str) -> None:
    """Set provider env vars, then reset the caches that memoise them.

    Args:
        monkeypatch: Pytest monkeypatch, so the change is undone after the test.
        **env: Environment variable name/value pairs to set.
    """
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    _reset_caches()


def _clear_all_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every provider variable and reset the caches."""
    for name in ALL_PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    _reset_caches()


def _executable_event_type_branches(source: str) -> list[str]:
    """Return source locations that *branch on* ``event_type``.

    A regex over the file would flag the two places where the phrase appears in
    prose (the module docstring and a comment explaining that the pattern was
    removed), so this parses the AST instead and inspects only branch
    conditions. Mentions of ``event_type`` inside a branch *body* are legitimate
    (building a rationale string, a dict lookup) and are not reported.

    Args:
        source: Full text of ``supervisor_agent.py``.

    Returns:
        List of ``"line N: <condition>"`` strings; empty when routing contains no
        conditional dispatch on event type.
    """
    offenders: list[str] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        condition: Optional[ast.expr]
        if isinstance(node, ast.If):
            condition = node.test
        elif isinstance(node, ast.Match):  # `match event.event_type:` is dispatch too
            condition = node.subject
        else:
            continue
        condition_src = ast.get_source_segment(source, condition) or ""
        if "event_type" in condition_src:
            offenders.append(f"line {node.lineno}: {condition_src}")
    return offenders


# ---------------------------------------------------------------------------
# Test 1 — the LLM is wired in when a provider is configured
# ---------------------------------------------------------------------------


def test_supervisor_uses_llm_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """With a provider configured the Supervisor is a real LLM-driven agent."""
    _configure(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY=DUMMY_GEMINI_KEY)

    supervisor = create_supervisor_agent()

    # --- (a) constructed with a real model adapter, not None -----------------
    assert supervisor is not None, (
        "Supervisor must build when LLM_PROVIDER and its API key are set"
    )
    assert supervisor.model is not None, "Supervisor must carry a model adapter"
    assert isinstance(supervisor.model, Model), (
        f"expected a strands Model adapter, got {type(supervisor.model).__name__}"
    )
    assert type(supervisor.model).__name__ == "GeminiModel"
    assert get_provider_name() == "gemini"
    assert get_configured_model_id() == "gemini-2.5-flash"
    assert get_routing_mode() == "llm"

    # --- (b) all four specialists are tools the model can choose from --------
    # Strands 1.55 exposes no Agent.tools attribute; tool_names and the tool
    # registry are the introspection points, so the assertion goes through them
    # (supervisor_agent.get_supervisor_tool_names wraps exactly that).
    assert get_supervisor_tool_names(supervisor) == EXPECTED_SPECIALISTS

    specs = supervisor.tool_registry.get_all_tool_specs()
    assert len(specs) == 4, "the LLM must see all four specialists as tools"
    assert sorted(spec["name"] for spec in specs) == sorted(EXPECTED_SPECIALISTS)
    for spec in specs:
        # Without a description the model can only guess from the tool name, so
        # an empty description would silently degrade routing quality.
        assert len(spec["description"]) > 80, (
            f"{spec['name']} is exposed to the routing LLM without a usable "
            f"description"
        )
        assert spec["inputSchema"], f"{spec['name']} has no input schema"

    # --- (c) no top-level `if event_type == ...` routing remains -------------
    source = SUPERVISOR_SOURCE.read_text(encoding="utf-8")

    # Grep-style check, as specified: no line opens an if/elif on event_type.
    pattern = re.compile(r"^[ \t]*(?:if|elif)\b.*event_type\s*==", re.MULTILINE)
    matches = pattern.findall(source)
    assert not matches, f"found if/elif dispatch on event_type: {matches}"

    # Stronger AST check: nothing branches on event_type anywhere in the module.
    offenders = _executable_event_type_branches(source)
    assert offenders == [], f"routing still branches on event type: {offenders}"


# ---------------------------------------------------------------------------
# Test 2 — graceful degradation with no LLM
# ---------------------------------------------------------------------------


async def test_supervisor_degrades_gracefully_without_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With no credentials the Supervisor returns None and events still resolve."""
    _clear_all_providers(monkeypatch)

    # get_model() must fail loudly and name the exact env var, not return None.
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_model()

    assert create_supervisor_agent() is None, (
        "no LLM configured: the factory must return None rather than build an "
        "agent that cannot think"
    )
    assert get_routing_mode() == "fallback"

    # The deterministic path still resolves events end to end.
    event = CareEvent(
        event_type="refill_low",
        care_recipient_id="cr-001",
        payload={"medication_id": "med-001"},
    )
    result: ResolutionResult = await process_event(event)

    assert isinstance(result, ResolutionResult)
    assert result.resolved is True
    assert any("medication" in action.lower() for action in result.actions_taken)
    # Audit-before-execute: a "pending" event plus a final-outcome event.
    assert len(result.audit_event_ids) >= 2


# ---------------------------------------------------------------------------
# Test 3 — providers are swappable by env alone
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("provider", ["gemini", "groq", "bedrock", "anthropic"])
def test_provider_switch_does_not_change_code(
    monkeypatch: pytest.MonkeyPatch, provider: str
) -> None:
    """Switching provider is an env change: same code, different adapter.

    Each case imports the same modules and calls the same functions; only the
    environment differs. That a distinct adapter class comes back for each
    provider is the proof that the customer can swap providers without a code
    change or a rebuild.
    """
    env, expected_adapter = PROVIDER_MATRIX[provider]
    _clear_all_providers(monkeypatch)
    _configure(monkeypatch, LLM_PROVIDER=provider, **env)

    assert get_provider_name() == provider
    assert provider in SUPPORTED_PROVIDERS

    model = get_model()
    assert type(model).__name__ == expected_adapter, (
        f"LLM_PROVIDER={provider} built {type(model).__name__}, "
        f"expected {expected_adapter}"
    )
    assert get_configured_model_id(), f"{provider} resolved no model id"

    # The Supervisor builds on the swapped provider with all four specialists.
    supervisor = create_supervisor_agent()
    assert supervisor is not None, f"Supervisor failed to build for {provider}"
    assert type(supervisor.model).__name__ == expected_adapter
    assert get_supervisor_tool_names(supervisor) == EXPECTED_SPECIALISTS


def test_unsupported_provider_is_rejected_with_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A typo in LLM_PROVIDER fails loudly and lists the supported values."""
    _clear_all_providers(monkeypatch)
    _configure(monkeypatch, LLM_PROVIDER="not-a-provider")

    with pytest.raises(RuntimeError) as excinfo:
        get_model()

    message = str(excinfo.value)
    assert "not-a-provider" in message
    for provider in SUPPORTED_PROVIDERS:
        assert provider in message, f"{provider} missing from the error message"


def test_missing_key_error_names_the_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each provider's failure message names its own credential variable."""
    expected_var = {
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
    }
    for provider, env_var in expected_var.items():
        _clear_all_providers(monkeypatch)
        _configure(monkeypatch, LLM_PROVIDER=provider)
        with pytest.raises(RuntimeError, match=env_var):
            get_model()


def test_placeholder_key_is_treated_as_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unedited .env.example template must not masquerade as a credential.

    Adapters construct offline, so a copied template value would otherwise make
    the deployment report llm_available=true and then fail opaquely at the first
    inference call.
    """
    _configure(
        monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY="your-gemini-api-key"
    )
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        get_model()
    assert get_routing_mode() == "fallback"


# ---------------------------------------------------------------------------
# Test 4 — the model's choice, not the fallback table, decides the route
# ---------------------------------------------------------------------------


class _FakeModel(Model):
    """A ``strands.models.Model`` whose ``stream`` returns a scripted tool choice.

    Lets ``process_event()`` run the real LLM routing path — real Agent, real
    specialist tool specs — without any network call. It subclasses the real ABC
    because ``Agent.__init__`` inspects the model (``stateful``) and would reject
    a plain duck-typed object.
    """

    def __init__(self, chosen_tool: str, envelope: str) -> None:
        self.chosen_tool = chosen_tool
        self.envelope = envelope
        self.calls: list[dict[str, Any]] = []
        self.model_id = "fake-routing-model"
        self._config: dict[str, Any] = {"model_id": self.model_id}

    def update_config(self, **model_config: Any) -> None:
        """Record configuration overrides (never used by these tests)."""
        self._config.update(model_config)

    def get_config(self) -> Any:
        """Return the fake model configuration."""
        return self._config

    async def structured_output(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict]:
        """Not used by routing; present to satisfy the abstract interface."""
        raise NotImplementedError("structured_output is unused in routing tests")
        yield {}  # pragma: no cover - makes this an async generator

    async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict]:
        """Yield one tool-use block and one JSON envelope, as a provider would."""
        self.calls.append(kwargs)
        yield {
            "contentBlockStart": {"toolUse": {"name": self.chosen_tool}},
        }
        yield {"contentBlockDelta": {"delta": {"text": self.envelope}}}


async def test_route_follows_the_model_not_the_fallback_table(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LLM owns routing: its tool choice wins over the deterministic table.

    ``refill_low`` is mapped to *medication* in the fallback table. The fake
    model is scripted to choose *appointment* instead. If the route follows the
    model, the event is handled by the appointment specialist — which is only
    possible if the decision genuinely came from the inference turn. (This is a
    mechanism proof, not a recommendation: a real model choosing this would be a
    misroute, and the divergence WARNING in ``_route_via_llm`` exists to surface
    exactly that.)
    """
    _configure(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY=DUMMY_GEMINI_KEY)

    fake = _FakeModel(
        chosen_tool="CareBridgeAppointment",
        envelope=(
            '{"routed_to": "appointment", '
            '"rationale": "Scripted choice to prove the model owns routing.", '
            '"actions_taken": [], "escalation_recommended": "info"}'
        ),
    )
    monkeypatch.setattr(sup_mod, "get_model", lambda: fake)
    _reset_caches()
    # get_model is patched, so re-resolve the routing mode against the fake.
    assert get_routing_mode() == "llm"

    event = CareEvent(
        event_type="refill_low",
        care_recipient_id="cr-001",
        payload={"medication_id": "med-001"},
    )
    result: ResolutionResult = await process_event(event)

    # The model was actually consulted, with the four real specialist specs.
    assert fake.calls, "process_event never called the model — routing is not LLM-driven"
    tool_specs = fake.calls[0].get("tool_specs") or []
    assert sorted(spec["name"] for spec in tool_specs) == sorted(EXPECTED_SPECIALISTS)

    # And its choice decided the route.
    assert result.resolved is True
    assert any("appointment agent" in action.lower() for action in result.actions_taken), (
        f"expected the model's choice to win, got: {result.actions_taken}"
    )

    # The audit trail records which routing path produced the decision, so an
    # operator can tell an LLM route from a fallback route after the fact.
    audit_rows = get_audit_events(care_recipient_id="cr-001")
    assert audit_rows, "process_event wrote no audit events"
    assert any("routing=LLM" in str(row.get("rationale", "")) for row in audit_rows), (
        "no audit entry records routing=LLM: "
        f"{[str(row.get('rationale', ''))[:90] for row in audit_rows]}"
    )


async def test_llm_failure_degrades_that_event_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed inference call degrades one event, loudly, without losing it."""

    class _FailingModel(_FakeModel):
        async def stream(self, *args: Any, **kwargs: Any) -> AsyncIterator[dict]:
            raise RuntimeError("simulated provider outage")
            yield {}  # pragma: no cover - makes this an async generator

    _configure(monkeypatch, LLM_PROVIDER="gemini", GEMINI_API_KEY=DUMMY_GEMINI_KEY)
    monkeypatch.setattr(
        sup_mod, "get_model", lambda: _FailingModel("unused", "{}")
    )
    _reset_caches()

    event = CareEvent(
        event_type="refill_low",
        care_recipient_id="cr-001",
        payload={"medication_id": "med-001"},
    )
    result: ResolutionResult = await process_event(event)

    assert result.resolved is True, "a provider outage must not drop the event"
    joined = " ".join(result.actions_taken).lower()
    assert "medication" in joined, "fallback routing should still handle the event"
    assert "llm routing failed" in joined, (
        "the degradation must be visible in the result, not silent"
    )
    assert "simulated provider outage" in joined, (
        "the underlying provider error must be recorded, not swallowed"
    )
