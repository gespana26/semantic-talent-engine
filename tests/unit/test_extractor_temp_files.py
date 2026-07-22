"""Aislamiento y limpieza de las imágenes temporales del extractor.

REGRESIÓN QUE CUBRE
-------------------
`pdf_to_images` escribía `temp_page_N.png` con nombre fijo en el directorio de
trabajo. Dos consecuencias reales: dos postulaciones simultáneas en el portal
compartían (y se pisaban) las mismas imágenes, mezclando los CV de dos
candidatos; y en Windows, un fichero de una ejecución anterior retenido por
otro proceso abortaba la extracción con "cannot remove file: Permission
denied". El contrato actual: cada invocación escribe en su propio directorio
temporal y la limpieza retira ficheros y directorio sin propagar errores.
"""

import os

import fitz
import pytest

from core.extractor import CVImageExtractor


@pytest.fixture
def pdf_de_prueba(tmp_path):
    ruta = tmp_path / "cv.pdf"
    doc = fitz.open()
    for _ in range(2):
        pagina = doc.new_page()
        pagina.insert_text((72, 72), "CV de prueba")
    doc.save(str(ruta))
    doc.close()
    return str(ruta)


def test_cada_invocacion_usa_un_directorio_propio(pdf_de_prueba):
    extractor = CVImageExtractor()
    rutas_a = extractor.pdf_to_images(pdf_de_prueba)
    rutas_b = extractor.pdf_to_images(pdf_de_prueba)
    try:
        assert len(rutas_a) == 2 and len(rutas_b) == 2
        assert all(os.path.exists(r) for r in rutas_a + rutas_b)
        # Ningún fichero compartido entre invocaciones: sin colisiones posibles.
        assert set(rutas_a).isdisjoint(rutas_b)
        assert os.path.dirname(rutas_a[0]) != os.path.dirname(rutas_b[0])
    finally:
        extractor.clear_temp_images(rutas_a)
        extractor.clear_temp_images(rutas_b)


def test_no_escribe_en_el_directorio_de_trabajo(pdf_de_prueba):
    extractor = CVImageExtractor()
    rutas = extractor.pdf_to_images(pdf_de_prueba)
    try:
        for ruta in rutas:
            assert os.path.isabs(ruta)
            assert os.path.dirname(ruta) != os.getcwd()
            assert os.path.basename(os.path.dirname(ruta)).startswith("cv_pages_")
    finally:
        extractor.clear_temp_images(rutas)


def test_la_limpieza_retira_ficheros_y_directorio(pdf_de_prueba):
    extractor = CVImageExtractor()
    rutas = extractor.pdf_to_images(pdf_de_prueba)
    directorio = os.path.dirname(rutas[0])
    extractor.clear_temp_images(rutas)
    assert not any(os.path.exists(r) for r in rutas)
    assert not os.path.exists(directorio)


def test_la_limpieza_no_propaga_errores(pdf_de_prueba):
    """Un fichero ya inexistente o una lista con rutas extrañas no debe lanzar."""
    extractor = CVImageExtractor()
    rutas = extractor.pdf_to_images(pdf_de_prueba)
    extractor.clear_temp_images(rutas)
    extractor.clear_temp_images(rutas)          # segunda pasada: ya no existen
    extractor.clear_temp_images(["/ruta/inexistente/pagina.png"])


def test_dimensiones_multiplos_de_28(pdf_de_prueba):
    """El parche de compatibilidad con Qwen2.5-VL se conserva tras el cambio."""
    from PIL import Image
    extractor = CVImageExtractor()
    rutas = extractor.pdf_to_images(pdf_de_prueba)
    try:
        for ruta in rutas:
            with Image.open(ruta) as img:
                assert img.width % 28 == 0
                assert img.height % 28 == 0
    finally:
        extractor.clear_temp_images(rutas)
