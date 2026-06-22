"""Unit tests for `config/settings.py`.

Scope (first slice):
- Default values for environment-driven settings.
- Environment overrides via `monkeypatch` + `importlib.reload`.
- `clean_collection_name` normalization behavior.

These tests are pure: no network, no filesystem writes, no ChromaDB,
no AI providers.

Isolation note:
`config/settings.py` calls `load_dotenv()` at import time. If we import
`config.settings` at module-collection time (top-level import), the
developer's local `.env` is read once BEFORE any `monkeypatch` runs,
which contaminates environment-driven assertions even with later
reloads. To prevent that, this module does NOT import `config.settings`
at the top level. Instead, every test goes through `_load_settings`,
which first patches `dotenv.load_dotenv` to a no-op and only then
imports (or reloads) the settings module. This guarantees the env state
seen by `config.settings` is exactly what the test set up with
`monkeypatch`, with no `.env` leakage.
"""

from __future__ import annotations

import importlib
import sys

import dotenv
import pytest


def _load_settings(monkeypatch: pytest.MonkeyPatch):
    """Import or reload `config.settings` under a patched `load_dotenv`.

    Steps:
    1. Replace `dotenv.load_dotenv` with a no-op so neither the first
       import nor a subsequent reload can read the developer's `.env`.
       The settings module uses `from dotenv import load_dotenv`, so the
       binding is rebound from the `dotenv` namespace each time the
       module is (re)loaded — patching at the package level is what
       actually neutralizes it.
    2. If `config.settings` is not yet imported, import it now (under
       the patch). If it is already in `sys.modules` (e.g. imported by
       an earlier test), reload it so module-level env reads
       re-evaluate against the current `monkeypatch` state.

    The monkeypatch is reverted automatically at the end of the test.
    """
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)

    if "config.settings" in sys.modules:
        return importlib.reload(sys.modules["config.settings"])
    return importlib.import_module("config.settings")


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


def test_default_ai_provider_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AI_PROVIDER_TYPE", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.AI_PROVIDER_TYPE == "openai"


def test_default_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODEL_NAME", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.MODEL_NAME == "gpt-4o-mini"


def test_default_openai_api_key_is_placeholder(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.OPENAI_API_KEY == "placeholder_key_clean"


def test_default_debug_mode_is_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEBUG_MODE", raising=False)
    settings = _load_settings(monkeypatch)
    assert settings.DEBUG_MODE is True


def test_static_infrastructure_paths_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """The non-env infrastructure constants must always be defined."""
    settings = _load_settings(monkeypatch)
    assert settings.CHROMA_DB_PATH == "./storage/chroma_vector_db"
    assert settings.LOCAL_STORAGE_CV_PATH == "./storage/cv_files"
    assert settings.OLLAMA_EMBEDDINGS_ENDPOINT == "http://localhost:11434"
    assert settings.EMBEDDING_MODEL == "nomic-embed-text"


# ---------------------------------------------------------------------------
# Environment overrides
# ---------------------------------------------------------------------------


def test_override_ai_provider_type(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_PROVIDER_TYPE", "ollama")
    settings = _load_settings(monkeypatch)
    assert settings.AI_PROVIDER_TYPE == "ollama"


def test_override_model_name(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_NAME", "gemma2")
    settings = _load_settings(monkeypatch)
    assert settings.MODEL_NAME == "gemma2"


def test_override_openai_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-1234")
    settings = _load_settings(monkeypatch)
    assert settings.OPENAI_API_KEY == "sk-test-1234"


@pytest.mark.parametrize(
    "raw_value,expected",
    [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("1", True),
        ("t", True),
        ("false", False),
        ("False", False),
        ("0", False),
        ("no", False),
        ("", False),
    ],
)
def test_debug_mode_truthiness_parsing(
    monkeypatch: pytest.MonkeyPatch, raw_value: str, expected: bool
) -> None:
    monkeypatch.setenv("DEBUG_MODE", raw_value)
    settings = _load_settings(monkeypatch)
    assert settings.DEBUG_MODE is expected


# ---------------------------------------------------------------------------
# clean_collection_name
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # lowercasing + trim
        ("DataScience", "datascience"),
        ("   Backend   ", "backend"),
        # spaces become single dash
        ("Senior Backend Developer", "senior-backend-developer"),
        # special chars become dashes, collapsed
        ("C++ / Python !!!", "c-python"),
        # allowed chars (a-z, 0-9, -, _, .) preserved
        ("data_pipeline.v2", "data_pipeline.v2"),
        ("role-2025", "role-2025"),
        # collapsing runs of dashes
        ("a---b", "a-b"),
        # leading/trailing dashes stripped
        ("---hello---", "hello"),
        # numbers passthrough
        ("12345", "12345"),
    ],
)
def test_clean_collection_name_normalization(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: str
) -> None:
    settings = _load_settings(monkeypatch)
    assert settings.clean_collection_name(raw) == expected


def test_clean_collection_name_truncates_to_63_chars(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _load_settings(monkeypatch)
    raw = "a" * 100
    result = settings.clean_collection_name(raw)
    assert len(result) <= 63
    assert result == "a" * 63


def test_clean_collection_name_strips_trailing_dashes_after_truncation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 62 'a's + a run of special chars: special chars become a single '-'
    # via collapse, then truncation lands inside/at the dash region and
    # `.strip('-')` removes any trailing dash.
    settings = _load_settings(monkeypatch)
    raw = ("a" * 62) + ("!" * 10)
    result = settings.clean_collection_name(raw)
    assert not result.endswith("-")
    assert len(result) <= 63
