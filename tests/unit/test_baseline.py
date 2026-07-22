"""Unit tests for `core/baseline.py`.

La línea base existe porque el cero teórico de la similitud coseno no es el cero
empírico. Entre dos textos profesionales sin relación alguna el coseno vale unos
0,68, de modo que una escala que dé por supuesto el 0 arranca en el 84 %. Estos
tests fijan que restar el suelo devuelve el cero a su sitio y que el módulo
degrada sin romperse cuando el servicio de embeddings no responde.
"""

from __future__ import annotations

import pytest

from core import baseline

# ---------------------------------------------------------------------------
# Normalización
# ---------------------------------------------------------------------------


def test_un_perfil_en_la_linea_base_vale_cero() -> None:
    """Es el punto entero del módulo: lo ajeno debe dar 0, no 84."""
    assert baseline.normalizar_similitud(0.68, 0.68) == 0.0


def test_por_debajo_de_la_linea_base_no_hay_grados() -> None:
    """No existe "peor que no tener nada que ver"."""
    assert baseline.normalizar_similitud(0.50, 0.68) == 0.0


def test_la_similitud_maxima_sigue_valiendo_uno() -> None:
    assert baseline.normalizar_similitud(1.0, 0.68) == pytest.approx(1.0)


def test_la_escala_se_reparte_sobre_el_margen_disponible() -> None:
    """0,75 sobre un suelo de 0,50 usa la mitad del margen que queda."""
    assert baseline.normalizar_similitud(0.75, 0.50) == pytest.approx(0.5)


def test_una_linea_base_degenerada_no_divide_por_cero() -> None:
    assert baseline.normalizar_similitud(1.0, 1.0) == 0.0


@pytest.mark.parametrize(("distancia", "esperado"), [(0.0, 1.0), (0.25, 0.75), (1.0, 0.0)])
def test_la_distancia_de_chroma_se_convierte_en_similitud(distancia: float, esperado: float) -> None:
    assert baseline.similitud_desde_distancia(distancia) == pytest.approx(esperado)


def test_una_distancia_ilegible_no_rompe_el_calculo() -> None:
    assert baseline.similitud_desde_distancia(None) == 0.0


# ---------------------------------------------------------------------------
# Cálculo de la línea base
# ---------------------------------------------------------------------------


def _embeddings(textos: list) -> list:
    """El criterio apunta a una dirección; los perfiles ajenos, a otra.

    El desplazamiento común de 0,5 reproduce el cono estrecho que ocupan los
    embeddings reales: es justo lo que hace que dos textos sin relación den 0,68
    en lugar de 0.
    """
    salida = []
    for texto in textos:
        eje = 1.0 if "datos" in texto.lower() else 0.0
        salida.append([0.5 + eje, 0.5, 0.5])
    return salida


def test_la_linea_base_es_el_maximo_de_los_perfiles_ajenos() -> None:
    """Con la media el listón queda más bajo; se elige la lectura estricta."""
    base = baseline.calcular_linea_base("Analisis de datos", _embeddings)
    assert 0.0 < base < 1.0


def test_sin_cliente_de_embeddings_degrada_a_cero() -> None:
    """Sin línea base la similitud queda sin descontar, pero nada se rompe."""
    assert baseline.calcular_linea_base("Analisis de datos", None) == 0.0


def test_un_fallo_del_servicio_no_propaga_la_excepcion() -> None:
    def revienta(_textos):
        raise ConnectionError("Ollama no responde")

    assert baseline.calcular_linea_base("Analisis de datos", revienta) == 0.0


def test_una_respuesta_incompleta_se_descarta() -> None:
    """Un lote con menos vectores de los pedidos desalinearía las comparaciones."""
    assert baseline.calcular_linea_base("Analisis de datos", lambda t: [[1, 0, 0]]) == 0.0


def test_un_criterio_vacio_no_gasta_una_llamada() -> None:
    llamadas = []

    def registrar(textos):
        llamadas.append(textos)
        return _embeddings(textos)

    assert baseline.calcular_linea_base("", registrar) == 0.0
    assert llamadas == []


# ---------------------------------------------------------------------------
# Caché de embeddings
# ---------------------------------------------------------------------------


def test_la_cache_no_revectoriza_lo_ya_visto() -> None:
    """Al re-puntuar, los requisitos y los conceptos de contraste no cambian."""
    lotes = []

    def contar(textos):
        lotes.append(list(textos))
        return _embeddings(textos)

    cacheada = baseline.cachear_embeddings(contar)
    cacheada(["requisito", "contraste"])
    cacheada(["requisito", "contraste", "habilidad nueva"])

    assert lotes == [["requisito", "contraste"], ["habilidad nueva"]]


def test_la_cache_conserva_el_orden_pedido() -> None:
    cacheada = baseline.cachear_embeddings(_embeddings)
    cacheada(["Analisis de datos", "Otra cosa"])
    devuelto = cacheada(["Otra cosa", "Analisis de datos"])

    assert devuelto[0] == [0.5, 0.5, 0.5]
    assert devuelto[1] == [1.5, 0.5, 0.5]


def test_la_cache_deduplica_dentro_del_mismo_lote() -> None:
    lotes = []

    def contar(textos):
        lotes.append(list(textos))
        return _embeddings(textos)

    cacheada = baseline.cachear_embeddings(contar)
    resultado = cacheada(["Analisis de datos", "Analisis de datos"])

    assert lotes == [["Analisis de datos"]]
    assert len(resultado) == 2


def test_sin_cliente_la_cache_no_inventa_uno() -> None:
    assert baseline.cachear_embeddings(None) is None
