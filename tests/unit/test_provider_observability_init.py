"""Unit tests for provider initialization under Langfuse enable/disable.

Scope (LLM observability slice):
- Disabled state: `OpenAIProvider` and `LocalOllamaProvider` initialize
  without raising, the OpenAI client is the native SDK (no drop-in swap),
  and Ollama methods are callable through the no-op `@observe` decorator
  without exceptions.
- Enabled state (mocked Langfuse): providers initialize without raising,
  `OpenAIProvider` uses the drop-in `langfuse.openai.OpenAI` client with
  the configured `langfuse_client` injected.

Isolation: `dotenv.load_dotenv` is patched to a no-op and the settings ->
observability -> provider module chain is reloaded for each scenario so
module-level env reads re-evaluate. The `langfuse` package is mocked via
`sys.modules` injection for the enabled-state scenario (the real package
is not required to run these tests).
"""

from __future__ import annotations

import importlib
import sys
import types

import dotenv
import pytest


def _reload_chain() -> None:
    """Reload settings -> observability -> ai_provider.

    Order matters: each downstream module reads the upstream module's
    module-level state at import. Settings is reloaded first so the rest
    see fresh env-derived values.
    """
    importlib.reload(sys.modules["config.settings"])
    importlib.reload(sys.modules["models.observability"])
    if "models.ai_provider" in sys.modules:
        importlib.reload(sys.modules["models.ai_provider"])


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch):
    """Patch load_dotenv to a no-op and ensure modules are importable.

    Tests set their env vars, then call `_reload_chain()`. At teardown the
    chain is reloaded under a clean (disabled) env so later tests start
    fresh.
    """
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    import config.settings  # noqa: F401
    import models.ai_provider  # noqa: F401
    import models.observability  # noqa: F401
    yield
    # Teardown: clean env and reload so module-level caches are reset.
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    _reload_chain()


@pytest.fixture
def mocked_langfuse(monkeypatch: pytest.MonkeyPatch):
    """Inject fake `langfuse`, `langfuse.openai`, `langfuse.decorators`, and
    `langfuse.context` packages into sys.modules. Reverted by monkeypatch.
    """
    captured: dict = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            captured["langfuse_kwargs"] = kwargs

    class FakeLangfuseOpenAI:
        def __init__(self, **kwargs):
            captured["openai_kwargs"] = kwargs

    def fake_observe(*args, **kwargs):
        def decorator(func):
            return func
        if len(args) == 1 and callable(args[0]) and not kwargs:
            return args[0]
        return decorator

    class _FakeContext:
        @staticmethod
        def update_current_observation(*a, **k):
            return None

    pkg = types.ModuleType("langfuse")
    pkg.Langfuse = FakeLangfuse
    oai_sub = types.ModuleType("langfuse.openai")
    oai_sub.OpenAI = FakeLangfuseOpenAI
    dec_sub = types.ModuleType("langfuse.decorators")
    dec_sub.observe = fake_observe
    ctx_sub = types.ModuleType("langfuse.context")
    ctx_sub.langfuse_context = _FakeContext

    monkeypatch.setitem(sys.modules, "langfuse", pkg)
    monkeypatch.setitem(sys.modules, "langfuse.openai", oai_sub)
    monkeypatch.setitem(sys.modules, "langfuse.decorators", dec_sub)
    monkeypatch.setitem(sys.modules, "langfuse.context", ctx_sub)
    return captured


# ---------------------------------------------------------------------------
# Disabled state
# ---------------------------------------------------------------------------


def test_disabled_state_all_providers_init_without_errors(monkeypatch, isolated_env) -> None:
    _reload_chain()
    from models.ai_provider import LocalOllamaProvider, OpenAIProvider

    openai_provider = OpenAIProvider()
    ollama_provider = LocalOllamaProvider()

    assert openai_provider.model is not None
    assert ollama_provider.model is not None


def test_disabled_state_uses_native_openai_sdk(isolated_env) -> None:
    _reload_chain()
    from openai import OpenAI as NativeOpenAI

    from models.ai_provider import OpenAIProvider

    provider = OpenAIProvider()
    assert isinstance(provider.client, NativeOpenAI)


def test_disabled_state_ollama_methods_callable_without_decorator_exceptions(
    monkeypatch, isolated_env,
) -> None:
    """The no-op @observe decorator must not interfere with method binding."""
    _reload_chain()
    from models.ai_provider import LocalOllamaProvider

    ollama_provider = LocalOllamaProvider()

    assert callable(ollama_provider.parse_cv_images_to_json)
    assert callable(ollama_provider.parse_vacancy)
    assert callable(ollama_provider.reconcile_vacancy_name)
    assert callable(ollama_provider.complete_json)


def test_disabled_state_get_langfuse_client_returns_none(monkeypatch, isolated_env) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "False")
    _reload_chain()
    from models.observability import get_langfuse_client
    assert get_langfuse_client() is None


# ---------------------------------------------------------------------------
# Enabled state (Langfuse mocked via sys.modules injection)
# ---------------------------------------------------------------------------


def test_enabled_state_openai_provider_uses_dropin_client(
    monkeypatch, isolated_env, mocked_langfuse
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-secret")
    _reload_chain()

    from models.ai_provider import OpenAIProvider

    provider = OpenAIProvider()

    fake_openai_cls = sys.modules["langfuse.openai"].OpenAI
    assert isinstance(provider.client, fake_openai_cls)
    # El cliente Langfuse se creo con mask_pii y se registro como activo
    # del proceso. `langfuse.openai.OpenAI` lo detecta automaticamente sin
    # necesidad de pasar `langfuse_client` explicitamente.
    lf_kwargs = mocked_langfuse.get("langfuse_kwargs", {})
    assert "mask" in lf_kwargs
    assert lf_kwargs.get("public_key") == "pk-public"
    assert lf_kwargs.get("secret_key") == "sk-secret"
    # langfuse.openai.OpenAI no recibe langfuse_client — usa el activo.


def test_enabled_state_ollama_init_without_errors(
    monkeypatch, isolated_env, mocked_langfuse
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-secret")
    _reload_chain()

    from models.ai_provider import LocalOllamaProvider

    LocalOllamaProvider()