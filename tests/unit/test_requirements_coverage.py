"""Unit tests for `core/requirements_coverage.py`.

El caso que motiva este módulo es real: un ingeniero de infraestructura con doce
años de experiencia obtuvo un 87,53 % de afinidad frente a una vacante de Project
Manager y disparó la alerta, sin cumplir ninguna de las dos habilidades exigidas
(«Modelos Predictivos» y «Metodologías ágiles»). La afinidad, al ser una única
similitud sobre textos mezclados, no puede expresar la noción de requisito.

Estos tests fijan el contrato de la comprobación que sí puede hacerlo.
"""

from __future__ import annotations

import pytest

from core.requirements_coverage import (
    cubre_lexicamente,
    evaluar_cobertura,
    normalizar,
    tokens_significativos,
)

# ---------------------------------------------------------------------------
# Normalización y tokenización
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Metodologías Ágiles", "metodologias agiles"),
        ("  GESTIÓN   de  Proyectos ", "gestion de proyectos"),
        ("Comunicación asertiva", "comunicacion asertiva"),
    ],
)
def test_normalizar_quita_acentos_y_colapsa_espacios(entrada: str, esperado: str) -> None:
    assert normalizar(entrada) == esperado


def test_tokens_descarta_palabras_vacias_y_cortas() -> None:
    assert tokens_significativos("Gestión de la Calidad en el Proyecto") == {
        "gestion", "calidad", "proyecto"
    }


def test_tokens_conserva_simbolos_tecnicos() -> None:
    """C++, C# o .NET no deben desaparecer al tokenizar."""
    tokens = tokens_significativos("Programación en C++ y .NET")
    assert "c++" in tokens
    assert ".net" in tokens


# ---------------------------------------------------------------------------
# Cobertura léxica
# ---------------------------------------------------------------------------


def test_cubre_la_frase_completa() -> None:
    assert cubre_lexicamente("Metodologías ágiles", "Experiencia en metodologias agiles") is True


def test_cubre_aunque_cambie_el_orden_de_las_palabras() -> None:
    """«gestión de proyectos» debe cubrirse con «proyectos de gestión avanzada»."""
    assert cubre_lexicamente("Gestión de proyectos", "Proyectos de gestión avanzada") is True


def test_no_cubre_si_falta_un_token_significativo() -> None:
    assert cubre_lexicamente("Modelos Predictivos", "Modelos de datos y reportes") is False


def test_no_cubre_con_requisito_vacio() -> None:
    assert cubre_lexicamente("", "cualquier cosa") is False


# ---------------------------------------------------------------------------
# Evaluación completa
# ---------------------------------------------------------------------------


def _embeddings_falsos(textos: list) -> list:
    """Vectores sintéticos que reproducen el 'cono estrecho' de los embeddings reales.

    Todos los vectores comparten una componente común dominante, de modo que dos
    textos sin ninguna relación obtienen igualmente una similitud alta. Es la
    condición que invalida los umbrales absolutos y la que la comprobación por
    contraste debe superar.
    """
    conceptos = {
        "agil": [1.0, 0.0, 0.0], "scrum": [0.95, 0.05, 0.0], "kanban": [0.92, 0.08, 0.0],
        "predictiv": [0.0, 1.0, 0.0], "machine learning": [0.05, 0.93, 0.0],
        "proyecto": [0.35, 0.0, 0.2],
    }
    salida = []
    for texto in textos:
        plano = normalizar(texto)
        especifico = [0.0, 0.0, 0.0]
        for clave, base in conceptos.items():
            if clave in plano:
                especifico = [a + b for a, b in zip(especifico, base)]
        # Componente común: sitúa todo dentro del mismo cono. Calibrada para que
        # dos textos sin relación queden en torno a 0,87 de similitud, como ocurre
        # con los embeddings reales del proyecto.
        comun = 0.5
        salida.append([comun + c for c in especifico])
    return salida


REQUISITOS = ["Modelos Predictivos", "Metodologías ágiles"]


def test_regresion_perfil_de_infraestructura_no_cubre_requisitos_de_gestion() -> None:
    """Regresión del caso real: alta afinidad, cero requisitos cubiertos."""
    habilidades = [
        "Seguridad informática", "Gestión de Operaciones de Infraestructura tecnológica",
        "Servidores", "Base de datos", "Planeación", "Gestión de proyectos tecnológicos",
    ]
    cobertura = evaluar_cobertura(REQUISITOS, habilidades, "Ingeniero de sistemas", _embeddings_falsos)

    assert cobertura["ratio"] == 0.0
    assert sorted(cobertura["faltantes"]) == sorted(REQUISITOS)


def test_los_sinonimos_se_resuelven_por_similitud() -> None:
    """«Scrum» debe cubrir «Metodologías ágiles»: es lo que un filtro literal no puede."""
    cobertura = evaluar_cobertura(REQUISITOS, ["Scrum", "Kanban"], "", _embeddings_falsos)

    assert "Metodologías ágiles" in cobertura["cubiertos"]
    assert "Metodologías ágiles" in cobertura["por_similitud"]
    assert cobertura["faltantes"] == ["Modelos Predictivos"]
    assert cobertura["ratio"] == pytest.approx(0.5)


def test_cobertura_total_con_coincidencia_literal() -> None:
    cobertura = evaluar_cobertura(REQUISITOS, list(REQUISITOS), "", _embeddings_falsos)
    assert cobertura["ratio"] == 1.0
    assert cobertura["faltantes"] == []
    assert cobertura["por_similitud"] == {}, "la vía léxica debe resolverlo sin gastar embeddings"


def test_vacante_sin_requisitos_no_puede_incumplirse() -> None:
    cobertura = evaluar_cobertura([], ["cualquier cosa"], "", _embeddings_falsos)
    assert cobertura["ratio"] == 1.0
    assert cobertura["sin_requisitos"] is True


def test_degrada_sin_funcion_de_embeddings() -> None:
    """Si Ollama no responde, la cobertura cae a la vía léxica en lugar de fallar."""
    cobertura = evaluar_cobertura(REQUISITOS, ["Scrum"], "", None)
    assert cobertura["ratio"] == 0.0
    assert cobertura["por_similitud"] == {}


def test_degrada_si_la_funcion_de_embeddings_falla() -> None:
    def revienta(_textos):
        raise RuntimeError("Ollama no disponible")

    cobertura = evaluar_cobertura(REQUISITOS, ["Scrum"], "", revienta)
    assert cobertura["ratio"] == 0.0
    assert cobertura["faltantes"] == REQUISITOS


def test_el_perfil_profesional_tambien_cuenta_para_la_cobertura() -> None:
    """Una habilidad descrita en el perfil vale aunque no esté en la lista de skills."""
    cobertura = evaluar_cobertura(
        ["Gestión de proyectos"], [],
        "Responsable de la gestión de proyectos tecnológicos durante ocho años",
        _embeddings_falsos
    )
    assert cobertura["ratio"] == 1.0
