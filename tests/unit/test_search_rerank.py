"""Unit tests del re-puntuado del buscador (`core/search_engine.py`).

QUÉ FIJAN ESTOS TESTS
---------------------
Que el orden que devuelve el motor vectorial deja de ser el orden que ve el
reclutador. El caso real que motivó el cambio es el que se reproduce aquí: un
perfil de infraestructura quedaba primero por similitud de documento completo
frente a una vacante de Project Manager sin cumplir ninguna de las dos
habilidades exigidas, mientras que quien sí las cumplía quedaba por detrás.

Se usa un doble de ChromaDB porque el comportamiento a verificar es de
composición —qué se recupera, qué se descarta y en qué orden se entrega— y no
depende del almacén. Es también la razón por la que §6.3 ya no necesita declarar
ChromaDB fuera del alcance de las pruebas.
"""

from __future__ import annotations

import json

import pytest

from config import settings
from core import search_engine as motor
from core.requirements_coverage import normalizar
from core.search_engine import CVSearchEngine


# ---------------------------------------------------------------------------
# Dobles
# ---------------------------------------------------------------------------


CONCEPTOS = {
    "agil": [1, 0, 0, 0, 0], "scrum": [.95, .05, 0, 0, 0],
    "predictiv": [0, 1, 0, 0, 0], "machine": [.05, .93, 0, 0, 0],
    "servidor": [0, 0, 1, 0, 0], "seguridad": [0, 0, .9, 0, 0],
    "sistemas": [0, 0, 0, 1, 0], "matematic": [0, 0, 0, .8, 0],
    "hosteler": [0, 0, 0, 0, 1], "cocina": [0, 0, 0, 0, .95], "jardin": [0, 0, 0, 0, .9],
    "reposter": [0, 0, 0, 0, .92],
    "enfermer": [0, 0, 0, 0, .88], "derecho": [0, 0, 0, 0, .84], "pesca": [0, 0, 0, 0, .86],
    "telefonic": [0, 0, 0, 0, .8], "archivo": [0, 0, 0, 0, .82],
    "conduccion": [0, 0, 0, 0, .86], "contabilidad": [0, 0, 0, 0, .78],
}


def _embeddings_falsos(textos: list) -> list:
    """Cada concepto tiene dirección propia, todos dentro de un cono estrecho.

    El desplazamiento de 0,5 en todas las componentes es lo que reproduce el
    fenómeno medido: dos textos sin relación alguna siguen dando una similitud
    alta, que es la razón de ser de la línea base.
    """
    salida = []
    for texto in textos:
        plano = normalizar(texto)
        vector = [0.0] * 5
        for clave, base in CONCEPTOS.items():
            if clave in plano:
                vector = [a + b for a, b in zip(vector, base)]
        salida.append([0.5 + v for v in vector])
    return salida


VACANTE = {
    "titulo_cargo": "Project Manager",
    "perfil_general": "Gestion de proyectos tecnologicos",
    "hard_skills": ["Modelos Predictivos", "Metodologias agiles"],
    "estudios_requeridos": ["Ingenieria de Sistemas", "Matematicas"],
    "experiencia_minima_anos": 3,
    "soft_skills": [],
}


def _candidato(nombre: str, correo: str, skills: list, titulo: str, anios: int) -> dict:
    """Metadato tal como lo persiste `store_candidate`."""
    perfil = {
        "nombre_completo": nombre, "correo_electronico": correo,
        "hard_skills": skills, "nivel_academico_maximo": titulo,
        "educacion_detalle": [titulo], "anios_experiencia_total": anios,
        "perfil_profesional": f"Profesional con experiencia en {', '.join(skills)}.",
    }
    return {
        "nombre_completo": nombre, "correo_electronico": correo,
        "tipo_registro": "candidato", "pdf_file_path": f"storage/{correo}.pdf",
        "origen": "portal_web", "raw_json": json.dumps(perfil),
    }


# El orden de esta lista ES el orden vectorial: Henry queda primero por similitud
# de documento completo pese a no cubrir ningún requisito.
POBLACION = [
    ("c1", _candidato("Henry Pena", "henry@mail.com",
                      ["Servidores", "Seguridad informatica"], "Ingenieria de Sistemas", 12), 0.24),
    ("c2", _candidato("Ana Ruiz", "ana@mail.com",
                      ["Scrum", "Machine Learning"], "Ingenieria de Sistemas", 5), 0.31),
    ("c3", _candidato("Marta Sol", "marta@mail.com",
                      ["Cocina mediterranea", "Reposteria"], "Escuela de Hosteleria", 12), 0.38),
]


class ColeccionFalsa:
    """Doble de una colección de ChromaDB con un silo autocontenido."""

    def __init__(self, poblacion=POBLACION, vacante=VACANTE):
        self.poblacion = poblacion
        self.vacante = vacante
        self.consultas = []

    def query(self, query_texts=None, n_results=None, include=None, where=None):
        self.consultas.append({"where": where, "n_results": n_results})
        ids = [i for i, _, _ in self.poblacion]
        return {
            "ids": [ids],
            "metadatas": [[m for _, m, _ in self.poblacion]],
            "documents": [[m["raw_json"] for _, m, _ in self.poblacion]],
            "distances": [[d for _, _, d in self.poblacion]],
        }

    def get(self, ids=None, include=None):
        if ids == [CVSearchEngine.ID_VACANTE]:
            meta = {
                "tipo_registro": "perfil_vacante",
                "titulo_cargo": self.vacante.get("titulo_cargo", ""),
                "raw_json": json.dumps(self.vacante),
            }
            return {"ids": ids, "metadatas": [meta], "documents": [""]}
        return {"ids": [i for i, _, _ in self.poblacion],
                "metadatas": [m for _, m, _ in self.poblacion],
                "documents": [m["raw_json"] for _, m, _ in self.poblacion]}


@pytest.fixture
def buscador(monkeypatch):
    """Instancia el motor sobre el doble, sin tocar disco ni Ollama."""
    coleccion = ColeccionFalsa()

    class ClienteFalso:
        def __init__(self, *_a, **_k):
            pass

        def get_collection(self, *_a, **_k):
            return coleccion

    monkeypatch.setattr(motor.chromadb, "PersistentClient", ClienteFalso)
    monkeypatch.setattr(
        motor.embedding_functions, "OllamaEmbeddingFunction",
        lambda *_a, **_k: _embeddings_falsos
    )
    engine = CVSearchEngine(collection_name="project-manager")
    engine.coleccion_falsa = coleccion
    return engine


# ---------------------------------------------------------------------------
# El re-puntuado cambia el orden
# ---------------------------------------------------------------------------


def test_sin_vacante_manda_el_orden_vectorial(buscador) -> None:
    """La búsqueda libre no tiene requisitos que verificar: no puede reordenar."""
    resultados = buscador.search_candidates(query_text="gestion de proyectos", limit=3)
    assert [c["nombre"] for c in resultados] == ["Henry Pena", "Ana Ruiz", "Marta Sol"]


def test_regresion_el_perfil_de_infraestructura_deja_de_ir_primero(buscador) -> None:
    """El caso real: 87,53 % y primera posición sin cubrir ninguna de las dos habilidades."""
    criterio = buscador.obtener_perfil_vacante()
    resultados = buscador.search_candidates(query_text=criterio, limit=3, vacante=VACANTE)

    assert resultados[0]["nombre"] == "Ana Ruiz"
    henry = next(c for c in resultados if c["nombre"] == "Henry Pena")
    assert henry["desglose"]["cobertura"]["ratio"] == 0.0
    assert henry["porcentaje_afinidad"] < resultados[0]["porcentaje_afinidad"] / 2


def test_el_perfil_de_otro_dominio_se_hunde(buscador) -> None:
    """Con la fórmula anterior obtenía un 84 % por el suelo de la escala."""
    resultados = buscador.search_candidates(
        query_text=buscador.obtener_perfil_vacante(), limit=3, vacante=VACANTE
    )
    chef = next(c for c in resultados if c["nombre"] == "Marta Sol")
    assert chef["porcentaje_afinidad"] < 5


def test_el_resultado_llega_explicado(buscador) -> None:
    """El porcentaje solo es defendible si se puede desarmar."""
    resultados = buscador.search_candidates(
        query_text=buscador.obtener_perfil_vacante(), limit=1, vacante=VACANTE
    )
    primero = resultados[0]

    assert primero["tipo_puntuacion"] == "afinidad"
    assert "habilidades" in primero["explicacion"]
    assert primero["desglose"]["cobertura"]["total"] == 2


def test_la_busqueda_libre_se_marca_como_similitud(buscador) -> None:
    """Dos números que miden cosas distintas no deben presentarse igual."""
    primero = buscador.search_candidates(query_text="gestion de proyectos", limit=1)[0]

    assert primero["tipo_puntuacion"] == "similitud"
    assert primero["desglose"] is None
    assert primero["porcentaje_afinidad"] == primero["similitud_normalizada"]


def test_la_similitud_deja_de_arrancar_en_el_ochenta_y_cuatro(buscador) -> None:
    """Descontada la línea base, ningún candidato hereda el suelo de la escala."""
    resultados = buscador.search_candidates(query_text="gestion de proyectos", limit=3)
    assert all(0.0 <= c["similitud_normalizada"] <= 100.0 for c in resultados)
    assert all(c["similitud_normalizada"] < 84.0 for c in resultados)


# ---------------------------------------------------------------------------
# Coste y ventana
# ---------------------------------------------------------------------------


def test_la_ventana_de_repuntuado_no_recorta_por_debajo_del_limite(buscador, monkeypatch) -> None:
    """Pedir más resultados que la ventana no puede devolver menos."""
    monkeypatch.setattr(settings, "TOP_N_RERANK", 1)
    resultados = buscador.search_candidates(
        query_text=buscador.obtener_perfil_vacante(), limit=3, vacante=VACANTE
    )
    assert len(resultados) == 3


def test_la_linea_base_se_calcula_una_sola_vez_por_criterio(buscador) -> None:
    """Es una llamada de embeddings: repetirla en cada búsqueda no aporta nada."""
    llamadas = []
    original = buscador.embedding_function

    def contar(textos):
        llamadas.append(list(textos))
        return original(textos)

    buscador.embedding_function = contar
    buscador.search_candidates(query_text="gestion de proyectos", limit=3)
    tras_la_primera = len(llamadas)
    buscador.search_candidates(query_text="gestion de proyectos", limit=3)

    assert len(llamadas) == tras_la_primera


# ---------------------------------------------------------------------------
# La vacante estructurada
# ---------------------------------------------------------------------------


def test_la_vacante_estructurada_se_recupera_por_clave(buscador) -> None:
    vacante = buscador.obtener_vacante_estructurada()
    assert vacante["hard_skills"] == ["Modelos Predictivos", "Metodologias agiles"]


def test_un_silo_sin_vacante_devuelve_un_diccionario_vacio(buscador) -> None:
    """El buscador no puede asumir que el silo esté bien formado."""
    buscador.coleccion_falsa.get = lambda ids=None, include=None: {"metadatas": []}
    assert buscador.obtener_vacante_estructurada() == {}


def test_la_vacante_no_aparece_entre_los_candidatos(buscador) -> None:
    """El silo es autocontenido: el pre-filtro por tipo_registro la excluye."""
    buscador.search_candidates(query_text="gestion de proyectos", limit=3)
    assert buscador.coleccion_falsa.consultas[0]["where"] == {"tipo_registro": "candidato"}
