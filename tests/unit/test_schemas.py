"""Unit tests for `models/schemas.py`.

Scope (first slice):
- `VacancyStructure`: valid construction, default `dias_vigencia`,
  rejection on missing required field, rejection on bad type.
- `CandidateStructure`: valid construction with nested
  `ExperienciaLaboral`, default `ubicacion`, rejection on missing
  required field.
- `ChromaQueryStructure`: minimal valid construction.

These tests must NOT import from `core/`, `ui/`, or any AI provider.
They exercise Pydantic v2 validation behavior at the contract level
for fields and defaults this project actually defines.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from models.schemas import (
    CandidateStructure,
    ChromaQueryStructure,
    ExperienciaLaboral,
    VacancyStructure,
)


# ---------------------------------------------------------------------------
# VacancyStructure
# ---------------------------------------------------------------------------


def _valid_vacancy_payload() -> dict:
    return {
        "titulo_cargo": "Senior Backend Developer",
        "perfil_general": "Owns the backend platform and integrations.",
        "estudios_requeridos": ["Ingenieria de Sistemas"],
        "experiencia_minima_anos": 5,
        "rango_salarial": "No especificado",
        "hard_skills": ["Python", "PostgreSQL"],
        "soft_skills": ["Comunicacion"],
    }


def test_vacancy_valid_payload_is_accepted() -> None:
    vacancy = VacancyStructure(**_valid_vacancy_payload())
    assert vacancy.titulo_cargo == "Senior Backend Developer"
    assert vacancy.experiencia_minima_anos == 5
    assert vacancy.hard_skills == ["Python", "PostgreSQL"]


def test_vacancy_dias_vigencia_default_is_applied() -> None:
    """`dias_vigencia` is optional with a default of 30."""
    vacancy = VacancyStructure(**_valid_vacancy_payload())
    assert vacancy.dias_vigencia == 30


def test_vacancy_dias_vigencia_override_is_respected() -> None:
    payload = _valid_vacancy_payload() | {"dias_vigencia": 7}
    vacancy = VacancyStructure(**payload)
    assert vacancy.dias_vigencia == 7


@pytest.mark.parametrize(
    "missing_field",
    [
        "titulo_cargo",
        "perfil_general",
        "estudios_requeridos",
        "experiencia_minima_anos",
        "rango_salarial",
        "hard_skills",
        "soft_skills",
    ],
)
def test_vacancy_missing_required_field_is_rejected(missing_field: str) -> None:
    payload = _valid_vacancy_payload()
    payload.pop(missing_field)
    with pytest.raises(ValidationError) as exc_info:
        VacancyStructure(**payload)
    # The offending field must appear in the validation error locations.
    error_fields = {err["loc"][0] for err in exc_info.value.errors()}
    assert missing_field in error_fields


def test_vacancy_rejects_non_integer_experience() -> None:
    payload = _valid_vacancy_payload() | {
        "experiencia_minima_anos": "five-ish",
    }
    with pytest.raises(ValidationError):
        VacancyStructure(**payload)


# ---------------------------------------------------------------------------
# ExperienciaLaboral
# ---------------------------------------------------------------------------


def test_experiencia_laboral_valid_payload() -> None:
    exp = ExperienciaLaboral(
        empresa="Acme Corp",
        cargo="Backend Engineer",
        duracion_anios=2.5,
    )
    assert exp.empresa == "Acme Corp"
    assert exp.duracion_anios == pytest.approx(2.5)


def test_experiencia_laboral_missing_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ExperienciaLaboral(empresa="Acme", cargo="Dev")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# CandidateStructure
# ---------------------------------------------------------------------------


def _valid_candidate_payload() -> dict:
    return {
        "nombre_completo": "Jane Doe",
        "correo_electronico": "jane@example.com",
        "telefono_movil": "+57 300 000 0000",
        "nivel_academico_maximo": "Profesional",
        "educacion_detalle": ["Ingenieria de Sistemas"],
        "anios_experiencia_total": 6,
        "historial_laboral": [
            {
                "empresa": "Acme Corp",
                "cargo": "Backend Engineer",
                "duracion_anios": 2.5,
            }
        ],
        "perfil_profesional": "Backend engineer focused on data platforms.",
        "hard_skills": ["Python", "SQL"],
        "soft_skills": ["Comunicacion"],
    }


def test_candidate_valid_payload_is_accepted() -> None:
    candidate = CandidateStructure(**_valid_candidate_payload())
    assert candidate.nombre_completo == "Jane Doe"
    assert len(candidate.historial_laboral) == 1
    assert isinstance(candidate.historial_laboral[0], ExperienciaLaboral)
    assert candidate.historial_laboral[0].empresa == "Acme Corp"


def test_candidate_default_ubicacion_is_applied() -> None:
    candidate = CandidateStructure(**_valid_candidate_payload())
    assert candidate.ubicacion == "No especificada"


def test_candidate_ubicacion_override_is_respected() -> None:
    payload = _valid_candidate_payload() | {"ubicacion": "Bogota, CO"}
    candidate = CandidateStructure(**payload)
    assert candidate.ubicacion == "Bogota, CO"


@pytest.mark.parametrize(
    "missing_field",
    [
        "nombre_completo",
        "correo_electronico",
        "telefono_movil",
        "nivel_academico_maximo",
        "educacion_detalle",
        "anios_experiencia_total",
        "historial_laboral",
        "perfil_profesional",
        "hard_skills",
        "soft_skills",
    ],
)
def test_candidate_missing_required_field_is_rejected(missing_field: str) -> None:
    payload = _valid_candidate_payload()
    payload.pop(missing_field)
    with pytest.raises(ValidationError) as exc_info:
        CandidateStructure(**payload)
    error_fields = {err["loc"][0] for err in exc_info.value.errors()}
    assert missing_field in error_fields


# ---------------------------------------------------------------------------
# ChromaQueryStructure
# ---------------------------------------------------------------------------


def test_chroma_query_valid_payload() -> None:
    query = ChromaQueryStructure(
        query_text_conceptual="senior python backend",
        where_filter={"anios_experiencia_total": {"$gte": 5}},
    )
    assert query.query_text_conceptual == "senior python backend"
    assert query.where_filter == {"anios_experiencia_total": {"$gte": 5}}


def test_chroma_query_missing_field_rejected() -> None:
    with pytest.raises(ValidationError):
        ChromaQueryStructure(query_text_conceptual="x")  # type: ignore[call-arg]
