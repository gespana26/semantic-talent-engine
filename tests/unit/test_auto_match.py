"""Unit tests de la decisión de alerta (`core/auto_match.py`).

El caso que fija el contrato es real: un ingeniero de infraestructura con doce
años de experiencia obtuvo un 87,53 % frente a una vacante de Project Manager y
se le envió la alerta al reclutador, sin cumplir ninguna de las dos habilidades
exigidas. No era una alucinación —su perfil menciona gestión de proyectos— y
quedaba por debajo de la mediana de su propio silo. Ningún umbral sobre aquella
magnitud podía distinguirlo de un candidato pertinente.

Estos tests verifican además que la afinidad que viaja en el correo es la misma
que ve el reclutador en el buscador. Que fueran dos escalas distintas es parte de
cómo se llegó al problema.
"""

from __future__ import annotations

import pytest

from config import settings
from core import auto_match
from core import search_engine as motor
from tests.unit.test_search_rerank import POBLACION, VACANTE, ColeccionFalsa, _embeddings_falsos


@pytest.fixture
def silo(monkeypatch):
    """Monta el silo y el banco global sobre el mismo doble."""
    coleccion = ColeccionFalsa()

    class ClienteFalso:
        def __init__(self, *_a, **_k):
            pass

        def get_collection(self, *_a, **_k):
            return coleccion

    for modulo in (motor, auto_match):
        monkeypatch.setattr(modulo.chromadb, "PersistentClient", ClienteFalso)
        monkeypatch.setattr(
            modulo.embedding_functions, "OllamaEmbeddingFunction",
            lambda *_a, **_k: _embeddings_falsos
        )

    # El suelo de afinidad se neutraliza aquí para que estos tests no dependan
    # del valor del .env del desarrollador; los tests de la regla del suelo
    # fijan explícitamente el suyo.
    monkeypatch.setattr(settings, "UMBRAL_AFINIDAD_ALERTA", 0.0)
    return coleccion


def _datos(indice: int) -> dict:
    import json
    return json.loads(POBLACION[indice][1]["raw_json"])


# ---------------------------------------------------------------------------
# La decisión
# ---------------------------------------------------------------------------


def test_regresion_henry_no_dispara_la_alerta(silo) -> None:
    """Cubría 0 de 2 requisitos y se le notificó igualmente con un 87,53 %."""
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(0))

    assert veredicto["alertar"] is False
    assert veredicto["cobertura"]["ratio"] == 0.0
    assert "Modelos Predictivos" in veredicto["motivo"]


def test_quien_cumple_los_requisitos_si_dispara_la_alerta(silo) -> None:
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    assert veredicto["alertar"] is True
    assert veredicto["cobertura"]["ratio"] == 1.0


def test_la_equivalencia_semantica_cuenta_como_cumplimiento(silo) -> None:
    """«Scrum» cubre «Metodologías ágiles»: es lo que un filtro literal pierde."""
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    equivalencias = veredicto["cobertura"]["por_similitud"]
    assert "Metodologias agiles" in equivalencias
    assert equivalencias["Metodologias agiles"][0] == "Scrum"


def test_la_afinidad_notificada_es_la_del_buscador(silo) -> None:
    """Una escala para la alerta y otra para el ranking es como nació el problema."""
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    buscador = motor.CVSearchEngine(collection_name="project-manager")
    resultados = buscador.search_candidates(
        query_text=buscador.obtener_perfil_vacante(), limit=3, vacante=VACANTE
    )
    ana = next(c for c in resultados if c["correo"] == _datos(1)["correo_electronico"])

    assert veredicto["afinidad"] == ana["porcentaje_afinidad"]


def test_el_veredicto_llega_con_el_desglose_completo(silo) -> None:
    """La decisión automática tiene que ser auditable, no solo correcta."""
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    assert veredicto["desglose"]["factor_experiencia"] == 1.0
    assert veredicto["desglose"]["cobertura"]["total"] == 2


# ---------------------------------------------------------------------------
# Rutas que no deben alertar
# ---------------------------------------------------------------------------


def test_la_bolsa_global_no_tiene_vacante_contra_la_que_evaluar(silo) -> None:
    veredicto = auto_match.evaluar_postulacion("", _datos(1))

    assert veredicto["alertar"] is False
    assert "bolsa global" in veredicto["motivo"]


def test_un_silo_sin_vacante_registrada_no_alerta(silo) -> None:
    """El silo fantasma del error de tecleo: existe la colección, no la oferta."""
    silo.get = lambda ids=None, include=None: {"metadatas": []}
    veredicto = auto_match.evaluar_postulacion("silo-fantasma", _datos(1))

    assert veredicto["alertar"] is False
    assert "no tiene una vacante registrada" in veredicto["motivo"]


def test_un_umbral_de_cobertura_mas_estricto_frena_la_alerta(silo, monkeypatch) -> None:
    """La regla es una constante configurable, no una cifra incrustada."""
    monkeypatch.setattr(settings, "UMBRAL_COBERTURA_REQUISITOS", 1.01)
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    assert veredicto["alertar"] is False


def test_un_perfil_sospechoso_suprime_la_alerta_de_talento(silo) -> None:
    """Regresión del CV con prompt injection: recibió la alerta de «talento
    excepcional» además de la de revisión manual. Si la verificación marcó
    sospecha, la cobertura puede estar inflada y la alerta no debe salir."""
    veredicto = auto_match.evaluar_postulacion(
        "project-manager", _datos(1), verificacion={"sospechoso": True}
    )

    assert veredicto["alertar"] is False
    assert "revisión manual" in veredicto["motivo"]


def test_un_perfil_verificado_limpio_no_se_ve_afectado(silo) -> None:
    veredicto = auto_match.evaluar_postulacion(
        "project-manager", _datos(1), verificacion={"sospechoso": False}
    )

    assert veredicto["alertar"] is True


def test_el_suelo_de_afinidad_frena_al_candidato_mediocre(silo, monkeypatch) -> None:
    """Regresión del correo real con 23,44 %: cubrir el umbral de cobertura por
    lo justo, en un banco pequeño, no convierte a nadie en excepcional."""
    monkeypatch.setattr(settings, "UMBRAL_AFINIDAD_ALERTA", 99.9)
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    assert veredicto["alertar"] is False
    assert "umbral de alerta" in veredicto["motivo"]


def test_el_suelo_de_afinidad_es_configurable_y_deja_pasar_al_bueno(silo, monkeypatch) -> None:
    monkeypatch.setattr(settings, "UMBRAL_AFINIDAD_ALERTA", 0.0)
    veredicto = auto_match.evaluar_postulacion("project-manager", _datos(1))

    assert veredicto["alertar"] is True


def test_el_hilo_de_notificacion_nunca_propaga_errores(silo, monkeypatch) -> None:
    """Fire-and-forget: el candidato ya recibió su confirmación."""
    def revienta(*_a, **_k):
        raise RuntimeError("SMTP caído")

    monkeypatch.setattr(auto_match, "enviar_alerta_talento", revienta)
    veredicto = auto_match.evaluar_y_notificar("project-manager", _datos(1))

    assert veredicto["alertar"] is False
    assert "Error" in veredicto["motivo"]
