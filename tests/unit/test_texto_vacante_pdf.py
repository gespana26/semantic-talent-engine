"""La oferta subida en PDF conserva su texto.

EL DEFECTO QUE CUBRE
--------------------
`process_and_register_vacancy` guardaba `texto_original=raw_text`, y `raw_text`
es `None` cuando la vacante se sube como PDF. El campo caía entonces al literal
«Texto original no disponible» que pone `database.py`, con dos consecuencias
visibles y una sola causa:

- El visor del reclutador mostraba ese marcador donde debía ir la oferta.
- El portal del candidato, que detecta el marcador y lo convierte en cadena
  vacía, publicaba la vacante **sin descripción alguna**.

Una vacante sin texto no se puede evaluar: el candidato no sabe a qué se postula
y el reclutador no ve qué publicó.

LA CASCADA
Se reutiliza `skill_verification.extraer_texto_documento`, que ya existía para
los currículums, en lugar de inventar una segunda forma de leer un PDF. Cuando
tampoco por ahí sale texto —un escaneado sin OCR disponible— se reconstruye una
descripción a partir de los campos que el modelo extrajo, marcada como tal: el
candidato tiene derecho a saber que no está leyendo la oferta literal.
"""

from __future__ import annotations

import pytest

from core import orchestrator


class VacanteDoble:
    """Doble de `VacancyStructure` con los campos que usa la reconstrucción."""

    titulo_cargo = "Gerente de Proyectos Data & AI"
    perfil_general = "Lidera iniciativas de datos e inteligencia artificial."
    estudios_requeridos = ["Ingenieria de Sistemas", "Maestria en Datos"]
    experiencia_minima_anos = 5
    rango_salarial = "No especificado"
    hard_skills = ["Scrum", "Machine Learning"]
    soft_skills = ["Liderazgo"]


# ---------------------------------------------------------------------------
# La cascada de texto
# ---------------------------------------------------------------------------


def test_se_usa_el_texto_real_del_pdf_cuando_lo_hay(monkeypatch) -> None:
    """La capa de texto del PDF es gratuita y exacta: es la primera opción."""
    monkeypatch.setattr(
        orchestrator.skill_verification, "extraer_texto_documento",
        lambda *_a, **_k: ("Buscamos Gerente de Proyectos con foco en datos.", "texto_pdf")
    )

    texto = orchestrator.texto_de_la_oferta("/tmp/oferta.pdf", [], VacanteDoble())

    assert texto == "Buscamos Gerente de Proyectos con foco en datos."
    assert "reconstruida" not in texto


def test_se_reconstruye_si_el_pdf_no_da_texto(monkeypatch) -> None:
    """Un escaneado sin OCR disponible: mejor una reconstrucción que nada."""
    monkeypatch.setattr(
        orchestrator.skill_verification, "extraer_texto_documento",
        lambda *_a, **_k: ("", "no_disponible")
    )

    texto = orchestrator.texto_de_la_oferta("/tmp/oferta.pdf", [], VacanteDoble())

    assert texto
    assert "Gerente de Proyectos Data & AI" in texto


def test_un_fallo_de_la_cascada_no_tumba_la_creacion(monkeypatch) -> None:
    """Publicar la vacante no puede depender de que el OCR funcione."""
    def revienta(*_a, **_k):
        raise RuntimeError("tesseract no instalado")

    monkeypatch.setattr(
        orchestrator.skill_verification, "extraer_texto_documento", revienta
    )

    texto = orchestrator.texto_de_la_oferta("/tmp/oferta.pdf", [], VacanteDoble())

    assert "Gerente de Proyectos Data & AI" in texto


def test_el_texto_en_blanco_del_pdf_no_se_da_por_bueno(monkeypatch) -> None:
    """Espacios y saltos de línea no son una descripción."""
    monkeypatch.setattr(
        orchestrator.skill_verification, "extraer_texto_documento",
        lambda *_a, **_k: ("   \n\t  ", "texto_pdf")
    )

    texto = orchestrator.texto_de_la_oferta("/tmp/oferta.pdf", [], VacanteDoble())

    assert "Gerente de Proyectos Data & AI" in texto


# ---------------------------------------------------------------------------
# La reconstruccion
# ---------------------------------------------------------------------------


def test_la_reconstruccion_se_declara_como_tal() -> None:
    """El candidato tiene derecho a saber que no lee la oferta literal."""
    texto = orchestrator.describir_vacante(VacanteDoble())

    assert texto.splitlines()[0].startswith("[Descripción reconstruida")


def test_la_reconstruccion_recoge_lo_que_el_candidato_necesita() -> None:
    texto = orchestrator.describir_vacante(VacanteDoble())

    assert "Lidera iniciativas de datos" in texto
    assert "Ingenieria de Sistemas, Maestria en Datos" in texto
    assert "5 años" in texto
    assert "Scrum, Machine Learning" in texto
    assert "Liderazgo" in texto


def test_la_reconstruccion_omite_los_campos_sin_declarar() -> None:
    """«No especificado» es ruido: ocupa sitio y no informa de nada."""
    texto = orchestrator.describir_vacante(VacanteDoble())
    assert "Rango salarial" not in texto


def test_la_reconstruccion_tolera_una_vacante_incompleta() -> None:
    """El modelo puede devolver listas vacías; eso no puede reventar la creación."""

    class Minima:
        titulo_cargo = "Becario"
        perfil_general = ""
        estudios_requeridos = []
        experiencia_minima_anos = 0
        rango_salarial = ""
        hard_skills = []
        soft_skills = []

    texto = orchestrator.describir_vacante(Minima())

    assert "Becario" in texto


# ---------------------------------------------------------------------------
# La consecuencia sobre el marcador de ausencia
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("resultado_cascada", ["", "   ", None])
def test_nunca_se_devuelve_el_marcador_de_ausencia(monkeypatch, resultado_cascada) -> None:
    """El literal de `database.py` es lo que el portal convierte en vacío.

    Mientras el orquestador no aporte texto, ese marcador es lo que acaba
    almacenado, y con él la vacante se publica sin descripción.
    """
    from core.vacancy_catalog import TEXTO_AUSENTE

    monkeypatch.setattr(
        orchestrator.skill_verification, "extraer_texto_documento",
        lambda *_a, **_k: (resultado_cascada, "no_disponible")
    )

    texto = orchestrator.texto_de_la_oferta("/tmp/oferta.pdf", [], VacanteDoble())

    assert texto
    assert texto != TEXTO_AUSENTE
