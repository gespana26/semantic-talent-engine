"""Unit tests for `CVSearchEngine.buscar_candidato_por_identidad`.

Es la ruta del comando `/nombre:` del reclutador. Los tests fijan dos cosas: que
la comparación sea insensible a mayúsculas y acentos —hoy buscar "maria" no
encontraba a "María" ni "pena" a "Peña"— y que la búsqueda parcial por correo se
conserve, porque es la funcionalidad que se habría perdido al escanear los
documentos en lugar de los metadatos.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

CANDIDATOS = [
    {"tipo_registro": "candidato", "nombre_completo": "LUIS FERNANDO BUITRAGO",
     "correo_electronico": "seincot@hotmail.com"},
    {"tipo_registro": "candidato", "nombre_completo": "Ana María Barreto",
     "correo_electronico": "ana@gmail.com"},
    {"tipo_registro": "candidato", "nombre_completo": "Henry Peña Espitia",
     "correo_electronico": "henry@hotmail.com"},
    {"tipo_registro": "perfil_vacante", "titulo_cargo": "Project Manager"},
]


class _ColeccionDoble:
    """Doble de ChromaDB: solo necesita responder a `get`."""

    name = "talento-global-empresa"

    def get(self, ids=None, where=None, include=None):
        if where:
            correo = where.get("correo_electronico")
            return {"ids": [], "metadatas": [
                m for m in CANDIDATOS if m.get("correo_electronico") == correo
            ]}
        return {"ids": [str(i) for i in range(len(CANDIDATOS))], "metadatas": CANDIDATOS}


@pytest.fixture()
def buscador(monkeypatch):
    """Monta el motor sobre el doble, sin ChromaDB ni Ollama.

    Se parchean los atributos del modulo ya importado en lugar de sustituir
    `chromadb` entero en `sys.modules`. La version anterior hacia lo segundo y
    solo funcionaba si este fichero se ejecutaba aislado: dentro de la suite
    completa, `core.search_engine` ya habia importado el chromadb real y seguia
    usandolo, mientras el falso quedaba en `sys.modules` rompiendo los imports
    diferidos internos del propio chromadb (`from chromadb import
    CollectionMetadata` resolvia contra el modulo falso). De ahi los 16 errores
    de `ImportError: ... (unknown location)`.
    """
    from core import search_engine as motor

    class ClienteFalso:
        def __init__(self, *_a, **_k):
            pass

        def get_collection(self, *_a, **_k):
            return _ColeccionDoble()

    monkeypatch.setattr(motor.store_client, "crear_cliente", lambda *_a, **_k: ClienteFalso())
    monkeypatch.setattr(
        motor.store_client, "crear_funcion_embeddings", lambda *_a, **_k: MagicMock()
    )
    return motor.CVSearchEngine()


def _nombres(resultados):
    return [m.get("nombre_completo") for m in resultados]


@pytest.mark.parametrize("termino", ["luis", "LUIS", "Luis", "  luis  "])
def test_insensible_a_mayusculas_y_espacios(buscador, termino: str) -> None:
    assert _nombres(buscador.buscar_candidato_por_identidad(termino)) == ["LUIS FERNANDO BUITRAGO"]


@pytest.mark.parametrize(("termino", "esperado"), [
    ("María", "Ana María Barreto"),
    ("maria", "Ana María Barreto"),
    ("Peña", "Henry Peña Espitia"),
    ("pena", "Henry Peña Espitia"),
    ("PENA", "Henry Peña Espitia"),
])
def test_insensible_a_acentos(buscador, termino: str, esperado: str) -> None:
    """El reclutador escribe rápido y sin tildes: eso no debe ocultarle candidatos."""
    assert esperado in _nombres(buscador.buscar_candidato_por_identidad(termino))


def test_conserva_la_busqueda_parcial_por_correo(buscador) -> None:
    """Se perdería al escanear documentos: el correo no está en el texto embebido."""
    encontrados = _nombres(buscador.buscar_candidato_por_identidad("hotmail"))
    assert set(encontrados) == {"LUIS FERNANDO BUITRAGO", "Henry Peña Espitia"}


def test_el_correo_completo_se_resuelve_por_metadato(buscador) -> None:
    assert _nombres(buscador.buscar_candidato_por_identidad("seincot@hotmail.com")) == [
        "LUIS FERNANDO BUITRAGO"
    ]


def test_no_devuelve_el_registro_de_la_vacante(buscador) -> None:
    """La vacante comparte colección con los candidatos y no tiene identidad."""
    for termino in ("project", "manager", "a"):
        assert all(r.get("tipo_registro") != "perfil_vacante"
                   for r in buscador.buscar_candidato_por_identidad(termino))


@pytest.mark.parametrize("termino", ["", "   ", None])
def test_termino_vacio_no_devuelve_nada(buscador, termino) -> None:
    """Sin término no hay búsqueda: devolver la colección entera sería peor que nada."""
    assert buscador.buscar_candidato_por_identidad(termino) == []


def test_sin_coincidencias_devuelve_lista_vacia(buscador) -> None:
    assert buscador.buscar_candidato_por_identidad("zzzz") == []
