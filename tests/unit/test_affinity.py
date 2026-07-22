"""Unit tests for `core/affinity.py`.

El contrato que fijan estos tests procede de una medición, no de una intuición:
con la fórmula anterior —la distancia de coseno normalizada— un criterio de
jardinería obtenía un 85 % de afinidad media contra un banco de perfiles
tecnológicos, porque el suelo empírico de esa escala era el 84 % y no el 0 %.

Los dos factores son multiplicativos por una razón comprobada: cuando la
experiencia se modeló como componente aditiva, un criterio de cocina alcanzaba
un 17,6 % solo por cumplir los años exigidos.
"""

from __future__ import annotations

import math

import pytest

from config import settings
from core.affinity import calcular_afinidad, explicar, factor_experiencia, factor_profesion
from core.requirements_coverage import normalizar

# ---------------------------------------------------------------------------
# Factor de experiencia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("anios", "esperado"), [(0, 0.0), (1, math.sqrt(1 / 3)), (2, math.sqrt(2 / 3))])
def test_experiencia_incompleta_sigue_una_curva_concava(anios: int, esperado: float) -> None:
    assert factor_experiencia(anios, 3) == pytest.approx(esperado)


def test_dos_de_tres_anios_penaliza_menos_que_la_proporcion_lineal() -> None:
    """El motivo del cambio: la proporción lineal hundía a quien casi cumple."""
    assert factor_experiencia(2, 3) > 2 / 3


@pytest.mark.parametrize("anios", [3, 5, 40])
def test_cumplir_o_superar_los_anios_no_penaliza(anios: int) -> None:
    assert factor_experiencia(anios, 3) == 1.0


@pytest.mark.parametrize("requeridos", [0, None, ""])
def test_sin_anios_exigidos_no_hay_penalizacion(requeridos) -> None:
    assert factor_experiencia(0, requeridos) == 1.0


def test_valores_no_numericos_no_rompen_el_calculo() -> None:
    assert factor_experiencia("muchos", 3) == 1.0


# ---------------------------------------------------------------------------
# Factor de profesión
# ---------------------------------------------------------------------------


def test_sin_titulacion_exigida_no_hay_penalizacion() -> None:
    assert factor_profesion(0.0, hay_requisito=False) == 1.0


def test_titulacion_cumplida_no_penaliza() -> None:
    assert factor_profesion(1.0, hay_requisito=True) == 1.0


def test_titulacion_ajena_penaliza_pero_conserva_el_suelo() -> None:
    """No anula: `nivel_academico_maximo` se extrae con precisión desigual."""
    assert factor_profesion(0.0, hay_requisito=True) == settings.PISO_FACTOR_PROFESION


def test_titulacion_parcial_penaliza_poco() -> None:
    """Las ofertas dicen "o afines": una carrera próxima no debe hundirse."""
    assert factor_profesion(0.5, hay_requisito=True) == pytest.approx(math.sqrt(0.5))


# ---------------------------------------------------------------------------
# Afinidad compuesta
# ---------------------------------------------------------------------------


def _embeddings_falsos(textos: list) -> list:
    """Cada habilidad tiene dirección propia; todas comparten un cono estrecho."""
    conceptos = {
        "agil": [1, 0, 0, 0, 0], "scrum": [.95, .05, 0, 0, 0],
        "predictiv": [0, 1, 0, 0, 0], "machine": [.05, .93, 0, 0, 0],
        "servidor": [0, 0, 1, 0, 0], "seguridad": [0, 0, .9, 0, 0],
        "sistemas": [0, 0, 0, 1, 0], "matematic": [0, 0, 0, .8, 0], "fisica": [0, 0, 0, .75, 0],
        "hosteler": [0, 0, 0, 0, 1], "cocina": [0, 0, 0, 0, .95], "jardin": [0, 0, 0, 0, .9],
        "telefonic": [0, 0, 0, 0, .8], "archivo": [0, 0, 0, 0, .82],
        "conduccion": [0, 0, 0, 0, .86], "contabilidad": [0, 0, 0, 0, .78],
    }
    salida = []
    for texto in textos:
        plano = normalizar(texto)
        vector = [0.0] * 5
        for clave, base in conceptos.items():
            if clave in plano:
                vector = [a + b for a, b in zip(vector, base)]
        salida.append([0.5 + v for v in vector])
    return salida


VACANTE = {
    "titulo_cargo": "Data Analyst",
    "hard_skills": ["Modelos Predictivos", "Metodologias agiles"],
    "estudios_requeridos": ["Ingenieria de Sistemas", "Matematicas"],
    "experiencia_minima_anos": 3,
}


def _candidato(skills: list, titulo: str, anios: int) -> dict:
    return {
        "hard_skills": skills, "nivel_academico_maximo": titulo,
        "educacion_detalle": [titulo], "anios_experiencia_total": anios,
        "perfil_profesional": "",
    }


def test_candidato_ideal_alcanza_la_parte_alta_de_la_escala() -> None:
    cand = _candidato(["Scrum", "Machine Learning"], "Ingenieria de Sistemas", 5)
    assert calcular_afinidad(VACANTE, cand, 0.27, _embeddings_falsos)["afinidad"] > 75


def test_regresion_chef_contra_perfiles_tecnicos() -> None:
    """El caso que motivó todo: antes daba 84 %."""
    cand = _candidato(["Cocina mediterranea"], "Escuela de Hosteleria", 12)
    assert calcular_afinidad(VACANTE, cand, 0.0, _embeddings_falsos)["afinidad"] == 0.0


def test_regresion_perfil_de_infraestructura_queda_muy_por_debajo() -> None:
    """El caso real: 87,53 % con la fórmula antigua, sin cumplir ningún requisito."""
    cand = _candidato(["Servidores", "Seguridad informatica"], "Ingenieria de Sistemas", 12)
    assert calcular_afinidad(VACANTE, cand, 0.10, _embeddings_falsos)["afinidad"] < 10


def test_la_titulacion_ajena_penaliza_aunque_cumpla_las_habilidades() -> None:
    """Un requisito de titulación no se compensa con habilidades."""
    correcta = _candidato(["Scrum", "Machine Learning"], "Ingenieria de Sistemas", 5)
    ajena = _candidato(["Scrum", "Machine Learning"], "Escuela de Hosteleria", 5)

    a_correcta = calcular_afinidad(VACANTE, correcta, 0.27, _embeddings_falsos)["afinidad"]
    a_ajena = calcular_afinidad(VACANTE, ajena, 0.27, _embeddings_falsos)["afinidad"]

    assert a_ajena < a_correcta / 2
    assert a_ajena > 0, "penaliza, pero no descarta: la extracción del título es imperfecta"


def test_una_carrera_afin_no_se_penaliza() -> None:
    """«o afines» es literal en las ofertas: Física debe valer para Matemáticas."""
    sistemas = _candidato(["Scrum", "Machine Learning"], "Ingenieria de Sistemas", 5)
    fisica = _candidato(["Scrum", "Machine Learning"], "Fisica", 5)

    a_sis = calcular_afinidad(VACANTE, sistemas, 0.27, _embeddings_falsos)["afinidad"]
    a_fis = calcular_afinidad(VACANTE, fisica, 0.27, _embeddings_falsos)["afinidad"]
    assert a_fis == pytest.approx(a_sis, rel=0.15)


def test_el_desglose_explica_el_numero() -> None:
    cand = _candidato(["Scrum"], "Ingenieria de Sistemas", 2)
    desglose = calcular_afinidad(VACANTE, cand, 0.15, _embeddings_falsos)

    texto = explicar(desglose)
    assert "cubre 1 de 2 habilidades" in texto
    assert "experiencia 2 de 3 años" in texto
    assert desglose["factor_experiencia"] < 1.0
