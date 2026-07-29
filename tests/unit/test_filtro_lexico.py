"""Unit tests del filtro léxico de requisitos obligatorios (`CVSearchEngine`).

QUÉ FIJAN ESTOS TESTS
---------------------
El filtro comparaba por subcadena sobre el texto aplanado del candidato, y eso
vuelve inservible cualquier requisito corto: «R» aparece dentro de "Ruby",
"Scrum" y "Barcelona"; «Go» dentro de "Google" y "Gomez"; «SQL» dentro de
"PostgreSQL". El reclutador marcaba la habilidad como innegociable y el sistema
la daba por cumplida sin avisar a nadie.

Un falso positivo aquí es de la peor clase posible: no produce error, no aparece
en ningún log y el resultado parece razonable. Solo se detecta leyendo el CV del
candidato que no debería estar ahí.

La otra mitad de estos tests protege lo contrario: que al apretar el emparejado
no se rompan los nombres que llevan símbolos —"C++", "C#", ".NET"—, que es
exactamente lo que ocurriría con un `\\b` ingenuo.
"""

from __future__ import annotations

import json

import pytest

from core.search_engine import CVSearchEngine


@pytest.fixture
def motor():
    """Instancia sin `__init__`: el filtro léxico no toca ni ChromaDB ni Ollama."""
    return CVSearchEngine.__new__(CVSearchEngine)


def _metadata(perfil: str, skills: list) -> dict:
    """Metadato de candidato tal como lo persiste `store_candidate`."""
    return {
        "nombre_completo": "Persona De Prueba",
        "correo_electronico": "persona@mail.com",
        "tipo_registro": "candidato",
        "pdf_file_path": "storage/web/persona.pdf",
        "origen": "portal_web",
        "perfil_profesional": perfil,
        "raw_json": json.dumps({"hard_skills": skills, "perfil_profesional": perfil}),
    }


# ---------------------------------------------------------------------------
# Regresión: el requisito corto dejaba de filtrar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino, texto",
    [
        ("r", "experiencia en ruby y scrum, reside en barcelona"),
        ("go", "trabajo en google, tutelado por gomez"),
        ("sql", "administracion de postgresql avanzado"),
        ("java", "cinco anios de javascript y typescript"),
        ("c", "documentacion y comunicacion corporativa"),
    ],
)
def test_el_requisito_corto_ya_no_casa_dentro_de_otra_palabra(motor, termino, texto) -> None:
    """El caso que anulaba el filtro: una letra o dos casan con casi cualquier CV."""
    assert motor._coincide_termino(termino, texto) is False


@pytest.mark.parametrize(
    "termino, texto",
    [
        ("r", "analisis estadistico con r y python"),
        ("go", "microservicios en go y rust"),
        ("sql", "modelado de datos y sql avanzado"),
        ("java", "backend en java y kotlin"),
    ],
)
def test_el_requisito_corto_sigue_casando_como_palabra(motor, termino, texto) -> None:
    """Apretar el filtro no puede convertirlo en inservible por el otro extremo."""
    assert motor._coincide_termino(termino, texto) is True


# ---------------------------------------------------------------------------
# Los nombres con símbolos, que un `\b` ingenuo rompería
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "termino, texto",
    [
        ("c++", "desarrollo de motores en c++ y python"),
        ("c#", "backend en c# sobre .net"),
        (".net", "backend en c# sobre .net"),
        ("node.js", "servicios en node.js y express"),
    ],
)
def test_los_nombres_con_simbolos_siguen_casando(motor, termino, texto) -> None:
    """`\\bc\\+\\+\\b` no casa nunca: el límite final exige un carácter de palabra."""
    assert motor._coincide_termino(termino, texto) is True


def test_la_frase_exacta_tolera_el_espaciado_del_documento(motor) -> None:
    """El CV parte la frase con un salto de línea; el requisito sigue siendo el mismo."""
    texto = "titulacion: ingeniero\n   industrial por la politecnica"
    assert motor._coincide_termino("ingeniero industrial", texto) is True


def test_el_termino_vacio_no_casa_con_nada(motor) -> None:
    """Un requisito vacío no puede darse por cumplido por omisión."""
    assert motor._coincide_termino("", "cualquier texto") is False
    assert motor._coincide_termino("   ", "cualquier texto") is False


# ---------------------------------------------------------------------------
# El filtro completo, sobre metadatos reales
# ---------------------------------------------------------------------------


def test_el_filtro_obligatorio_descarta_al_que_no_lo_cumple(motor) -> None:
    meta = _metadata("Desarrollador con experiencia en Ruby on Rails", ["Ruby", "Rails"])
    filtro = {"perfil_profesional": {"$contains": "r"}}
    assert motor._evaluar_filtro_python(meta, filtro) is False


def test_el_filtro_obligatorio_acepta_al_que_si_lo_cumple(motor) -> None:
    meta = _metadata("Analista con R y modelos estadisticos", ["R", "SPSS"])
    filtro = {"perfil_profesional": {"$contains": "r"}}
    assert motor._evaluar_filtro_python(meta, filtro) is True


def test_el_arreglo_bilingue_acepta_por_cualquiera_de_sus_ramas(motor) -> None:
    """La forma `$or` que emite el traductor para cubrir español e inglés."""
    meta = _metadata("Industrial Engineer con diez anios de planta", ["Lean", "Six Sigma"])
    filtro = {
        "$or": [
            {"perfil_profesional": {"$contains": "ingeniero industrial"}},
            {"perfil_profesional": {"$contains": "industrial engineer"}},
        ]
    }
    assert motor._evaluar_filtro_python(meta, filtro) is True


def test_el_arreglo_bilingue_descarta_si_ninguna_rama_casa(motor) -> None:
    meta = _metadata("Chef de cocina mediterranea", ["Reposteria"])
    filtro = {
        "$or": [
            {"perfil_profesional": {"$contains": "ingeniero industrial"}},
            {"perfil_profesional": {"$contains": "industrial engineer"}},
        ]
    }
    assert motor._evaluar_filtro_python(meta, filtro) is False


def test_los_metadatos_de_infraestructura_no_satisfacen_un_requisito(motor) -> None:
    """Postularse desde el portal web no es saber de «web». Comportamiento ya existente."""
    meta = _metadata("Contable con experiencia en cierre mensual", ["Contabilidad"])
    filtro = {"perfil_profesional": {"$contains": "web"}}
    assert motor._evaluar_filtro_python(meta, filtro) is False


def test_sin_filtro_pasan_todos(motor) -> None:
    meta = _metadata("Cualquier perfil", ["Cualquier skill"])
    assert motor._evaluar_filtro_python(meta, {}) is True
    assert motor._evaluar_filtro_python(meta, None) is True


def test_un_filtro_no_interpretable_descarta_en_vez_de_dejar_pasar(motor) -> None:
    """Comportamiento ya existente: si el reclutador exigió algo y no se supo
    comprobar, el sistema no puede afirmar que se cumple."""
    meta = _metadata("Cualquier perfil", ["Cualquier skill"])
    assert motor._evaluar_filtro_python(meta, {"perfil_profesional": {"$eq": "x"}}) is False
