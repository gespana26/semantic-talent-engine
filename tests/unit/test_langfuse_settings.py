"""Unit tests for Langfuse settings validation (`config/settings.py`).

Scope (LLM observability slice):
- `LANGFUSE_*` defaults and environment-driven values.
- Validation: when `LANGFUSE_ENABLED=True` but public/secret keys are
  missing, tracing MUST be silently disabled with a logged warning.
- When all keys are present, `LANGFUSE_ENABLED` remains True.

These tests are pure: no network, no Langfuse client initialization, no
provider instantiation. They reuse the same isolation pattern as
`test_settings.py`: `dotenv.load_dotenv` is patched to a no-op and the
settings module is reloaded for each test so module-level env reads
re-evaluate against the `monkeypatch` state.
"""

from __future__ import annotations

import importlib
import sys

import dotenv
import pytest


def _load_settings(monkeypatch: pytest.MonkeyPatch):
    """Import or reload `config.settings` under a patched `load_dotenv`.

    Mirrors the helper in `test_settings.py` so `.env` leakage cannot
    contaminate the environment-driven assertions here.
    """
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)

    if "config.settings" in sys.modules:
        return importlib.reload(sys.modules["config.settings"])
    return importlib.import_module("config.settings")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_langfuse_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.LANGFUSE_ENABLED is False


def test_langfuse_host_default_is_self_hosted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_HOST", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.LANGFUSE_HOST == "http://localhost:3000"


def test_langfuse_keys_default_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.LANGFUSE_PUBLIC_KEY == ""
    assert settings.LANGFUSE_SECRET_KEY == ""


# ---------------------------------------------------------------------------
# Validation: enabled flag + missing keys
# ---------------------------------------------------------------------------


def test_enabled_with_missing_keys_is_disabled_and_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LANGFUSE_ENABLED=True but keys missing -> tracing disabled + warning."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    with caplog.at_level("WARNING"):
        settings = _load_settings(monkeypatch)

    assert settings.LANGFUSE_ENABLED is False
    # At least one of the missing key names is mentioned in the warning.
    joined = " ".join(rec.getMessage() for rec in caplog.records)
    assert "Langfuse" in joined
    assert "LANGFUSE" in joined
    assert "Tracing disabled" in joined


def test_enabled_with_only_public_key_missing_is_disabled(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-secret")

    settings = _load_settings(monkeypatch)

    assert settings.LANGFUSE_ENABLED is False


def test_enabled_with_only_secret_key_missing_is_disabled(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-public")
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    settings = _load_settings(monkeypatch)

    assert settings.LANGFUSE_ENABLED is False


def test_enabled_with_all_keys_present_stays_enabled(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANGFUSE_ENABLED", "True")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-public")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-secret")
    monkeypatch.setenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    settings = _load_settings(monkeypatch)

    assert settings.LANGFUSE_ENABLED is True
    assert settings.LANGFUSE_HOST == "https://cloud.langfuse.com"


def test_disabled_flag_ignores_missing_keys(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """LANGFUSE_ENABLED=False does not warn even if keys are missing."""
    monkeypatch.setenv("LANGFUSE_ENABLED", "False")
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    with caplog.at_level("WARNING"):
        settings = _load_settings(monkeypatch)

    assert settings.LANGFUSE_ENABLED is False
    assert not any("Langfuse enabled but" in rec.getMessage() for rec in caplog.records)