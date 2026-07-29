"""Coherencia de la función de embeddings en el registro de vacantes.

REGRESIÓN QUE CUBRE
-------------------
El orquestador reasignaba `db_manager.collection` con un
`get_or_create_collection(name)` sin `embedding_function`. Ese objeto queda
ligado a la EF por defecto de ChromaDB (MiniLM, 384 dims), de modo que la
vacante podía vectorizarse en un espacio distinto al de los candidatos del
mismo silo (nomic-embed-text, 768 dims). Con chromadb 0.6.x la vacante fijaba
la dimensión de la colección y las postulaciones posteriores fallaban por
conflicto de dimensión; con 1.x el daño dependía de que la colección existiera
previamente con su EF correcta.

El contrato que estos tests protegen: **toda colección que participa en la
escritura de una vacante se crea u obtiene con la EF del proyecto y distancia
coseno**, y el upsert de la vacante ocurre sobre una de esas colecciones.
"""

import sys
import types

import pytest

# Ya no hace falta fabricar un `chromadb` falso en `sys.modules`. Los modulos del
# dominio construyen su cliente a traves de `core.store_client`, que difiere el
# import, de modo que importarlos no arrastra el almacen y basta con sustituir la
# costura. Aquel apano solo funcionaba si este fichero se ejecutaba aislado.
import core.database as database_mod
import core.orchestrator as orchestrator_mod
from core import store_client
from core.orchestrator import VacancyOrchestrator
from models.schemas import VacancyStructure

EF_DEL_PROYECTO = object()  # centinela: la EF nomic construida por el manager


class ColeccionDoble:
    def __init__(self, name, embedding_function=None, metadata=None):
        self.name = name
        self.embedding_function = embedding_function
        self.metadata = metadata or {}
        self.upserts = []

    def upsert(self, documents, metadatas, ids):
        self.upserts.append({"documents": documents, "metadatas": metadatas, "ids": ids})


class ClienteDoble:
    """Registra cada get_or_create_collection para poder auditar sus argumentos."""

    llamadas = []       # compartido entre instancias (orquestador y manager)
    existentes = []     # nombres que list_collections debe devolver

    def __init__(self, path=None):
        self.path = path

    def get_or_create_collection(self, name, embedding_function=None, metadata=None):
        coleccion = ColeccionDoble(name, embedding_function, metadata)
        ClienteDoble.llamadas.append(coleccion)
        return coleccion

    def list_collections(self):
        return [types.SimpleNamespace(name=n) for n in ClienteDoble.existentes]


class ProveedorDoble:
    def __init__(self, decision="NUEVA"):
        self.decision = decision

    def parse_vacancy(self, raw_text=None, image_paths=None):
        return VacancyStructure(
            titulo_cargo="Analista de Datos",
            perfil_general="Análisis de información comercial",
            estudios_requeridos=["Ingeniería de Sistemas"],
            experiencia_minima_anos=2,
            rango_salarial="No especificado",
            hard_skills=["SQL", "Python"],
            soft_skills=["Comunicación"],
        )

    def reconcile_vacancy_name(self, nuevo_titulo, colecciones_existentes):
        return self.decision


@pytest.fixture
def entorno(monkeypatch):
    ClienteDoble.llamadas = []
    ClienteDoble.existentes = []
    monkeypatch.setattr(store_client, "crear_cliente", lambda *_a, **_k: ClienteDoble())
    monkeypatch.setattr(
        store_client, "crear_funcion_embeddings", lambda *_a, **_k: EF_DEL_PROYECTO
    )
    return ClienteDoble


def test_toda_coleccion_del_flujo_lleva_la_ef_del_proyecto(entorno):
    orq = VacancyOrchestrator(ai_provider=ProveedorDoble())
    resultado = orq.process_and_register_vacancy(raw_text="Se busca analista de datos")

    assert resultado["status"] == "success"
    assert entorno.llamadas, "el flujo no creó ninguna colección"
    for col in entorno.llamadas:
        assert col.embedding_function is EF_DEL_PROYECTO, (
            f"la colección '{col.name}' se obtuvo sin la EF del proyecto: "
            "la vacante se vectorizaría en un espacio distinto al de los candidatos"
        )
        assert col.metadata.get("hnsw:space") == "cosine"


def test_el_upsert_de_la_vacante_ocurre_sobre_una_coleccion_coherente(entorno):
    orq = VacancyOrchestrator(ai_provider=ProveedorDoble())
    orq.process_and_register_vacancy(raw_text="Se busca analista de datos")

    con_upsert = [c for c in entorno.llamadas if c.upserts]
    assert len(con_upsert) == 1
    coleccion = con_upsert[0]
    assert coleccion.embedding_function is EF_DEL_PROYECTO
    assert coleccion.upserts[0]["ids"] == ["VACANTE_PRINCIPAL"]


def test_creacion_usa_el_nombre_saneado_del_titulo(entorno):
    orq = VacancyOrchestrator(ai_provider=ProveedorDoble(decision="NUEVA"))
    resultado = orq.process_and_register_vacancy(raw_text="texto")
    assert resultado["operacion"] == "creacion"
    assert resultado["coleccion"] == "analista-de-datos"


def test_edicion_dirige_la_escritura_a_la_coleccion_conciliada(entorno):
    entorno.existentes = ["analista-de-datos", "otro-cargo"]
    orq = VacancyOrchestrator(ai_provider=ProveedorDoble(decision="analista-de-datos"))
    resultado = orq.process_and_register_vacancy(raw_text="texto")

    assert resultado["operacion"] == "edicion"
    assert resultado["coleccion"] == "analista-de-datos"
    con_upsert = [c for c in entorno.llamadas if c.upserts]
    assert con_upsert[0].name == "analista-de-datos"
    assert con_upsert[0].embedding_function is EF_DEL_PROYECTO


def test_decision_no_listada_no_se_trata_como_edicion(entorno):
    """Una respuesta del LLM que no pertenece a la lista cerrada no enruta la escritura."""
    entorno.existentes = ["otro-cargo"]
    orq = VacancyOrchestrator(ai_provider=ProveedorDoble(decision="coleccion-inventada"))
    resultado = orq.process_and_register_vacancy(raw_text="texto")
    assert resultado["operacion"] == "creacion"
    assert resultado["coleccion"] == "analista-de-datos"
