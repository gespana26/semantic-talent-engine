"""El tipo numérico del proveedor de embeddings no debe salir del dominio.

EL DEFECTO QUE CUBRE
--------------------
El dashboard rotulaba **«Léxico» todos los resultados de búsqueda**, incluidos
los que el motor había puntuado correctamente. La causa no estaba en el cálculo
sino en el tipo:

`OllamaEmbeddingFunction` devuelve arrays de NumPy en `float32`. Ese tipo se
propagaba por toda la aritmética —línea base, similitud normalizada, porcentaje
final— y `round()` lo conserva. La vista comprobaba
`isinstance(valor, (int, float))` para decidir si tenía un número que pintar, y
**`np.float32` no es subclase de `float`**. `np.float64` sí lo es, lo que explica
por qué un fallo así puede pasar inadvertido en un entorno y manifestarse en
otro según lo que devuelva el servicio de embeddings.

El resultado era el peor posible para un TFM sobre afinidad semántica: el motor
calculaba la afinidad compuesta, la interfaz la descartaba en silencio y el
reclutador veía «Léxico» donde la memoria promete un porcentaje.

Estos tests fijan la conversión en el borde. Se prueban ambos tipos de NumPy
porque el que rompe es justo el que no salta a la vista.
"""

from __future__ import annotations

import numbers

import pytest

from core import baseline, requirements_coverage

np = pytest.importorskip("numpy", reason="NumPy no instalado")


def _vector(valores, tipo):
    """Vector tal como lo entrega la función de embeddings real: ndarray de NumPy."""
    return np.array(valores, dtype=tipo)


TIPOS = [
    pytest.param(np.float32, id="float32-el-que-rompia"),
    pytest.param(np.float64, id="float64"),
]


# ---------------------------------------------------------------------------
# El borde: donde el vector se reduce a un escalar
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_coseno_devuelve_float_de_python(tipo) -> None:
    a = _vector([0.5, 0.4, 0.3], tipo)
    b = _vector([0.4, 0.5, 0.3], tipo)

    resultado = baseline.coseno(a, b)

    assert type(resultado) is float, f"Se escapó {type(resultado).__name__} al dominio."


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_coseno_de_cobertura_devuelve_float_de_python(tipo) -> None:
    """La otra implementación del coseno, en `requirements_coverage`."""
    a = _vector([0.5, 0.4, 0.3], tipo)
    b = _vector([0.4, 0.5, 0.3], tipo)

    assert type(requirements_coverage._coseno(a, b)) is float


@pytest.mark.parametrize("tipo", TIPOS)
def test_la_linea_base_devuelve_float_de_python(tipo) -> None:
    def embeddings(textos):
        return [_vector([0.5, 0.4, 0.3, 0.2, 0.1], tipo) for _ in textos]

    resultado = baseline.calcular_linea_base("gestion de proyectos", embeddings)

    assert type(resultado) is float


@pytest.mark.parametrize("tipo", TIPOS)
def test_la_similitud_normalizada_devuelve_float_de_python(tipo) -> None:
    """El punto exacto en que el tipo llegaba al porcentaje que ve el reclutador."""
    linea_base = tipo(0.70)
    similitud = baseline.similitud_desde_distancia(0.24)

    resultado = baseline.normalizar_similitud(similitud, linea_base)

    assert type(resultado) is float


# ---------------------------------------------------------------------------
# La consecuencia: el porcentaje se reconoce como numero
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tipo", TIPOS)
def test_el_porcentaje_final_se_reconoce_como_numero(tipo) -> None:
    """Reproduce la comprobación de tipo que hacía la vista y fallaba."""
    linea_base = tipo(0.70)
    normalizada = baseline.normalizar_similitud(baseline.similitud_desde_distancia(0.24), linea_base)

    porcentaje = round(normalizada * 100, 2)

    assert isinstance(porcentaje, (int, float)), (
        "La vista rechazaría este valor y rotularía «Léxico» un resultado puntuado."
    )
    assert isinstance(porcentaje, numbers.Real)


def test_numpy_float32_no_es_float_de_python() -> None:
    """Deja constancia del hecho del que depende todo lo anterior.

    Si algún día NumPy cambiara esto, la conversión explícita seguiría siendo
    correcta pero este test dejaría de explicar por qué existe.
    """
    assert isinstance(np.float64(1.0), float) is True
    assert isinstance(np.float32(1.0), float) is False
    assert isinstance(np.float32(1.0), numbers.Real) is True


# ---------------------------------------------------------------------------
# La segunda barrera, en la presentacion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor, es_numero",
    [
        (21.05, True),
        (0, True),
        (100, True),
        (np.float64(21.05), True),
        (np.float32(21.05), True),
        ("Léxico", False),
        (None, False),
        (True, False),
    ],
)
def test_el_criterio_de_la_vista_acepta_cualquier_real(valor, es_numero) -> None:
    """`numbers.Real` cubre los tipos de NumPy; `(int, float)` no.

    Se excluye `bool` explícitamente: es subclase de `int` y un `True` en el
    porcentaje sería un error, no un cero.
    """
    reconocido = isinstance(valor, numbers.Real) and not isinstance(valor, bool)
    assert reconocido is es_numero
