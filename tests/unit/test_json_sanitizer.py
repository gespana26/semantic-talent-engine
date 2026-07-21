"""Unit tests for `core/json_sanitizer.py`.

El saneamiento existía como método privado de `LocalOllamaProvider`, de modo que
el traductor de consultas —que llama a Ollama exactamente igual— no lo aplicaba
y fallaba con respuestas que el extractor de CV habría recuperado sin problema.
Estos tests fijan el contrato de la utilidad ahora compartida.
"""

from __future__ import annotations

import json

import pytest

from core.json_sanitizer import extraer_json

ESPERADO = {"query_text_conceptual": "python backend", "where_filter": {}}


@pytest.mark.parametrize(
    ("etiqueta", "crudo"),
    [
        ("json puro", '{"query_text_conceptual": "python backend", "where_filter": {}}'),
        ("bloque markdown etiquetado",
         '```json\n{"query_text_conceptual": "python backend", "where_filter": {}}\n```'),
        ("bloque markdown sin etiqueta",
         '```\n{"query_text_conceptual": "python backend", "where_filter": {}}\n```'),
        ("con frase de cortesia delante",
         'Claro, aquí tienes el JSON:\n{"query_text_conceptual": "python backend", "where_filter": {}}'),
        ("con texto delante y detras",
         'Resultado:\n{"query_text_conceptual": "python backend", "where_filter": {}}\nEspero que sirva.'),
        ("con tokens de control de plantilla",
         '<|im_start|>{"query_text_conceptual": "python backend", "where_filter": {}}<|im_end|>'),
    ],
)
def test_recupera_el_json_de_una_respuesta_contaminada(etiqueta: str, crudo: str) -> None:
    assert json.loads(extraer_json(crudo)) == ESPERADO, etiqueta


def test_conserva_las_llaves_anidadas() -> None:
    crudo = '```json\n{"where_filter": {"$or": [{"perfil_profesional": {"$contains": "Ingeniero"}}]}}\n```'
    datos = json.loads(extraer_json(crudo))
    assert datos["where_filter"]["$or"][0]["perfil_profesional"]["$contains"] == "Ingeniero"


@pytest.mark.parametrize("entrada", ["", None, "   "])
def test_entradas_vacias_no_rompen(entrada) -> None:
    assert extraer_json(entrada) == ""


def test_texto_sin_json_se_devuelve_tal_cual() -> None:
    """No inventa: si no hay JSON, quien llama decide qué hacer con el error."""
    assert extraer_json("No he podido procesar la solicitud") == "No he podido procesar la solicitud"


def test_el_proveedor_local_delega_en_la_utilidad_compartida() -> None:
    """La robustez debe ser la misma se llame desde donde se llame."""
    # El proveedor arrastra los SDK de los modelos; el resto de la suite no los
    # necesita y no debe exigirlos para poder ejecutarse.
    pytest.importorskip("ollama")
    pytest.importorskip("openai")
    from models.ai_provider import LocalOllamaProvider

    proveedor = LocalOllamaProvider.__new__(LocalOllamaProvider)
    crudo = '```json\n{"a": 1}\n```'
    assert proveedor._extract_clean_json(crudo) == extraer_json(crudo)
