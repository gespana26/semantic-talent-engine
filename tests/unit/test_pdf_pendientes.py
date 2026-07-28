"""Ciclo de vida del PDF entre la extracción y la confirmación (defecto 2.6).

QUÉ FIJAN ESTOS TESTS
---------------------
`extract_candidate` copiaba el PDF directamente a `storage/cv_files/` —el
almacén **definitivo**— antes de que el candidato confirmase su postulación en
la fase 2 del portal. Si abandonaba ahí, el fichero quedaba en disco sin ningún
registro en el índice que lo referenciase, y nada lo recogía nunca.

Dos consecuencias, y la segunda pesa más que la primera: el directorio crecía sin
techo, y se retenían currículums con datos personales de personas que **decidieron
no postularse**. Un sistema que conserva el CV de quien se echó atrás no puede
sostener lo que la memoria afirma sobre tratamiento de datos.

No confundir con el defecto de las imágenes temporales, que es otro y ya estaba
resuelto: `pdf_to_images` escribía `temp_page_N.png` con nombre fijo y dos
postulaciones simultáneas se pisaban las páginas. Eso se arregló con un
directorio por invocación (`tests/unit/test_extractor_temp_files.py`). Aquel
afectaba a los PNG derivados; este, al PDF original.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from config import settings
from core import orchestrator


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    """Aísla `storage/cv_files/` para no tocar el del proyecto."""
    destino = tmp_path / "cv_files"
    monkeypatch.setattr(settings, "LOCAL_STORAGE_CV_PATH", str(destino))
    return destino


@pytest.fixture
def pdf_pendiente():
    """Simula la copia de trabajo que deja `extract_candidate`."""
    carpeta = tempfile.mkdtemp(prefix=orchestrator.PREFIJO_PENDIENTE)
    ruta = os.path.join(carpeta, "CV_abc123def456_curriculum.pdf")
    with open(ruta, "wb") as f:
        f.write(b"%PDF-1.4 contenido de prueba")
    yield ruta
    shutil.rmtree(carpeta, ignore_errors=True)


# ---------------------------------------------------------------------------
# Reconocer un pendiente
# ---------------------------------------------------------------------------


def test_la_ruta_temporal_se_reconoce_como_pendiente(pdf_pendiente) -> None:
    """El estado se lee de la ruta: no hay bandera aparte que desincronizar."""
    assert orchestrator._es_pendiente(pdf_pendiente) is True


def test_una_ruta_del_almacen_no_es_pendiente(almacen) -> None:
    assert orchestrator._es_pendiente(str(almacen / "CV_ya_persistido.pdf")) is False


def test_una_ruta_vacia_no_revienta() -> None:
    assert orchestrator._es_pendiente("") is False
    assert orchestrator._es_pendiente(None) is False


# ---------------------------------------------------------------------------
# Confirmar la postulacion
# ---------------------------------------------------------------------------


def test_confirmar_traslada_el_pdf_al_almacen(almacen, pdf_pendiente) -> None:
    """El fichero solo llega a storage cuando existe la postulacion que lo respalda."""
    final = orchestrator.persistir_pdf(pdf_pendiente)

    assert os.path.exists(final)
    assert os.path.dirname(final) == str(almacen)
    assert not os.path.exists(pdf_pendiente), "El original debe moverse, no copiarse."


def test_confirmar_conserva_el_contenido(almacen, pdf_pendiente) -> None:
    final = orchestrator.persistir_pdf(pdf_pendiente)
    with open(final, "rb") as f:
        assert f.read() == b"%PDF-1.4 contenido de prueba"


def test_confirmar_conserva_el_nombre_unico(almacen, pdf_pendiente) -> None:
    """El identificador aleatorio es lo que evita que dos "CV.pdf" se pisen."""
    final = orchestrator.persistir_pdf(pdf_pendiente)
    assert os.path.basename(final) == "CV_abc123def456_curriculum.pdf"


def test_confirmar_no_deja_atras_el_directorio_temporal(almacen, pdf_pendiente) -> None:
    carpeta = os.path.dirname(pdf_pendiente)
    orchestrator.persistir_pdf(pdf_pendiente)
    assert not os.path.exists(carpeta)


def test_confirmar_es_idempotente(almacen, pdf_pendiente) -> None:
    """Una segunda llamada sobre la ruta ya final no puede mover ni perder nada."""
    final = orchestrator.persistir_pdf(pdf_pendiente)
    assert orchestrator.persistir_pdf(final) == final
    assert os.path.exists(final)


def test_confirmar_un_fichero_inexistente_devuelve_la_ruta_sin_romper(almacen) -> None:
    fantasma = os.path.join(tempfile.gettempdir(), f"{orchestrator.PREFIJO_PENDIENTE}x", "no.pdf")
    assert orchestrator.persistir_pdf(fantasma) == fantasma


# ---------------------------------------------------------------------------
# Abandonar la postulacion: el defecto
# ---------------------------------------------------------------------------


def test_descartar_borra_la_copia_de_trabajo(pdf_pendiente) -> None:
    """El caso que motiva todo: el candidato se echa atras en la fase 2."""
    carpeta = os.path.dirname(pdf_pendiente)
    orchestrator.descartar_extraccion(pdf_pendiente)

    assert not os.path.exists(pdf_pendiente)
    assert not os.path.exists(carpeta)


def test_descartar_no_toca_un_pdf_ya_persistido(almacen, pdf_pendiente) -> None:
    """Confirmada la postulacion, el CV es del sistema: descartar no puede borrarlo."""
    final = orchestrator.persistir_pdf(pdf_pendiente)
    orchestrator.descartar_extraccion(final)
    assert os.path.exists(final)


def test_descartar_dos_veces_no_revienta(pdf_pendiente) -> None:
    """Reiniciar el borrador dos veces seguidas no puede tumbar el portal."""
    orchestrator.descartar_extraccion(pdf_pendiente)
    orchestrator.descartar_extraccion(pdf_pendiente)


def test_descartar_sin_ruta_no_revienta() -> None:
    orchestrator.descartar_extraccion(None)
    orchestrator.descartar_extraccion("")


# ---------------------------------------------------------------------------
# La propiedad de fondo
# ---------------------------------------------------------------------------


def test_el_almacen_solo_recibe_postulaciones_confirmadas(almacen, pdf_pendiente) -> None:
    """Extraer no deja nada en storage; solo confirmar lo hace.

    Es la invariante que el defecto rompia: `storage/cv_files/` contenia CV de
    personas que nunca llegaron a postularse.
    """
    assert not almacen.exists() or list(almacen.iterdir()) == []

    orchestrator.descartar_extraccion(pdf_pendiente)
    assert not almacen.exists() or list(almacen.iterdir()) == []


def test_tras_confirmar_el_almacen_contiene_exactamente_un_cv(almacen, pdf_pendiente) -> None:
    orchestrator.persistir_pdf(pdf_pendiente)
    assert [p.name for p in almacen.iterdir()] == ["CV_abc123def456_curriculum.pdf"]
