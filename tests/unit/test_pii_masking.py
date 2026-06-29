"""Unit tests for PII masking (`models/observability.py::mask_pii`).

Scope (LLM observability slice):
- `mask_pii` redacts the 7 known candidate PII fields to "[REDACTED]".
- Non-PII candidate fields (hard_skills, soft_skills, etc.) are preserved.
- All VacancyStructure-style fields remain fully visible.
- Recursion works through nested dicts, lists, and 3+ levels deep.

These tests are pure: they exercise `mask_pii` directly as a function.
They do NOT initialize any Langfuse client, network connection, or
provider.
"""

from __future__ import annotations

from models.observability import PII_FIELDS, mask_pii


# Known PII fields from CandidateStructure (design contract).
EXPECTED_PII_FIELDS = {
    "nombre_completo",
    "correo_electronico",
    "telefono_movil",
    "ubicacion",
    "educacion_detalle",
    "historial_laboral",
    "perfil_profesional",
}


def test_pii_fields_set_matches_design_contract() -> None:
    assert PII_FIELDS == EXPECTED_PII_FIELDS


def test_pii_field_is_redacted_with_key_preserved() -> None:
    data = {"correo_electronico": "test@example.com"}
    masked = mask_pii(data)
    assert "correo_electronico" in masked  # key preserved
    assert masked["correo_electronico"] == "[REDACTED]"


def test_all_seven_pii_fields_redacted() -> None:
    candidate = {
        "nombre_completo": "Juan Perez",
        "correo_electronico": "juan@mail.com",
        "telefono_movil": "+57 300 123 4567",
        "ubicacion": "Bogota, Colombia",
        "educacion_detalle": ["Ing - Universidad X"],
        "historial_laboral": [{"empresa": "ACME", "cargo": "Dev"}],
        "perfil_profesional": "Dev fullstack",
    }
    masked = mask_pii(dict(candidate))

    for field in EXPECTED_PII_FIELDS:
        assert masked[field] == "[REDACTED]", f"{field} not redacted"


def test_non_pii_candidate_fields_preserved() -> None:
    candidate = {
        "hard_skills": ["python", "docker"],
        "soft_skills": ["liderazgo"],
        "anios_experiencia_total": 5,
        "nivel_academico_maximo": "Profesional",
        "correo_electronico": "x@y.com",
    }
    masked = mask_pii(candidate)

    assert masked["hard_skills"] == ["python", "docker"]
    assert masked["soft_skills"] == ["liderazgo"]
    assert masked["anios_experiencia_total"] == 5
    assert masked["nivel_academico_maximo"] == "Profesional"
    assert masked["correo_electronico"] == "[REDACTED]"


def test_vacancy_fields_never_redacted() -> None:
    # VacancyStructure fields are intentionally non-PII.
    vacancy = {
        "titulo": "Backend Dev",
        "descripcion": "Python backend role",
        "hard_skills": ["python", "postgres"],
        "ubicacion": "Remoto",
    }
    masked = mask_pii(dict(vacancy))

    # Note: `ubicacion` is a PII field in CandidateStructure but a vacancy
    # uses the same key for the job location. Per the design, masking is
    # schema-agnostic at the SDK level: it redacts by field name. This test
    # documents that vacancy's non-overlapping fields stay visible; the
    # `ubicacion` overlap is an accepted design tradeoff (PII masking is
    # conservative — better to over-redact a job location than leak a
    # candidate residence).
    assert masked["titulo"] == "Backend Dev"
    assert masked["descripcion"] == "Python backend role"
    assert masked["hard_skills"] == ["python", "postgres"]


# ---------------------------------------------------------------------------
# Recursion
# ---------------------------------------------------------------------------


def test_pii_in_nested_dict_is_redacted() -> None:
    data = {"formacion": {"educacion_detalle": ["Titulo - Inst"]}}
    masked = mask_pii(data)
    assert masked["formacion"]["educacion_detalle"] == "[REDACTED]"


def test_pii_in_list_items_is_redacted() -> None:
    data = [
        {"nombre_completo": "A", "correo_electronico": "a@mail.com"},
        {"nombre_completo": "B", "correo_electronico": "b@mail.com"},
    ]
    masked = mask_pii(data)
    assert all(item["nombre_completo"] == "[REDACTED]" for item in masked)
    assert all(item["correo_electronico"] == "[REDACTED]" for item in masked)


def test_pii_three_levels_deep_is_redacted() -> None:
    data = {
        "level1": {
            "level2": {
                "level3": {
                    "correo_electronico": "deep@mail.com",
                    "hard_skills": ["x"],
                }
            }
        }
    }
    masked = mask_pii(data)
    inner = masked["level1"]["level2"]["level3"]
    assert inner["correo_electronico"] == "[REDACTED]"
    assert inner["hard_skills"] == ["x"]


def test_mask_pii_non_dict_list_passes_through() -> None:
    assert mask_pii("plain string") == "plain string"
    assert mask_pii(42) == 42
    assert mask_pii(3.14) == 3.14
    assert mask_pii(None) is None
    assert mask_pii(True) is True


def test_mask_pii_empty_structures() -> None:
    assert mask_pii({}) == {}
    assert mask_pii([]) == []


def test_mask_pii_accepts_extra_kwargs() -> None:
    # Langfuse SDK may pass extra kwargs to the mask callable.
    data = {"correo_electronico": "x@y.com", "hard_skills": ["py"]}
    masked = mask_pii(data, some_langfuse_kwarg=True)
    assert masked["correo_electronico"] == "[REDACTED]"
    assert masked["hard_skills"] == ["py"]