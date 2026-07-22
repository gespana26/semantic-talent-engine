"""Unit tests for `config/providers.py` y el contrato `BaseLLMProvider`.

El objetivo 5 del proyecto promete cambiar de proveedor de IA sin tocar la lógica
de negocio. No se cumplía: la decisión estaba repetida en cinco sitios y uno de
ellos, el traductor de consultas, vivía dentro de `core/`. Además `BaseLLMProvider`
declaraba un solo método y ninguna clase la heredaba, de modo que el contrato
existía en la memoria del proyecto pero no en el código.

Estos tests fijan las dos propiedades que hacen cierta esa promesa.
"""

from __future__ import annotations

import pytest

from models.interfaces import BaseLLMProvider

METODOS_DEL_CONTRATO = {
    "parse_cv_images_to_json",
    "parse_vacancy",
    "reconcile_vacancy_name",
    "complete_json",
}


class ProveedorDePrueba(BaseLLMProvider):
    """Tercer proveedor imaginario: mide lo que cuesta de verdad añadir uno."""

    def parse_cv_images_to_json(self, image_paths):
        return {"origen": "prueba"}

    def parse_vacancy(self, raw_text=None, image_paths=None):
        return {"origen": "prueba"}

    def reconcile_vacancy_name(self, nuevo_titulo, colecciones_existentes):
        return "NUEVA"

    def complete_json(self, system_prompt, user_prompt):
        return '{"query_text_conceptual": "prueba", "where_filter": {}}'


# ---------------------------------------------------------------------------
# El contrato
# ---------------------------------------------------------------------------


def test_la_interfaz_declara_las_cuatro_operaciones() -> None:
    assert METODOS_DEL_CONTRATO <= set(BaseLLMProvider.__abstractmethods__)


def test_no_se_puede_instanciar_la_interfaz() -> None:
    with pytest.raises(TypeError):
        BaseLLMProvider()


def test_una_implementacion_incompleta_falla_al_construirse() -> None:
    """El contrato deja de ser decorativo: no heredarlo entero impide instanciar."""

    class Incompleto(BaseLLMProvider):
        def parse_cv_images_to_json(self, image_paths):
            return {}

    with pytest.raises(TypeError):
        Incompleto()


def test_los_proveedores_reales_heredan_el_contrato() -> None:
    pytest.importorskip("ollama")
    pytest.importorskip("openai")
    from models.ai_provider import LocalOllamaProvider, OpenAIProvider

    assert issubclass(OpenAIProvider, BaseLLMProvider)
    assert issubclass(LocalOllamaProvider, BaseLLMProvider)


def test_ningun_proveedor_real_queda_con_metodos_abstractos() -> None:
    """Heredar no basta: hay que implementar las cuatro operaciones.

    `issubclass` sigue siendo cierto aunque falte un metodo, asi que por si sola
    la comprobacion de herencia no detecta que un proveedor pierda, por ejemplo,
    `complete_json` —la operacion que sostiene al traductor de consultas—. Aqui
    se exige que la clase sea instanciable, que es lo que la ABC garantiza.
    """
    pytest.importorskip("ollama")
    pytest.importorskip("openai")
    from models.ai_provider import LocalOllamaProvider, OpenAIProvider

    for clase in (OpenAIProvider, LocalOllamaProvider):
        pendientes = sorted(getattr(clase, "__abstractmethods__", frozenset()))
        assert not pendientes, (
            f"{clase.__name__} no implementa {pendientes}: el contrato vuelve a "
            f"ser decorativo y la clase no puede construirse."
        )


# ---------------------------------------------------------------------------
# El composition root
# ---------------------------------------------------------------------------


def test_un_proveedor_desconocido_falla_de_forma_explicita() -> None:
    from config.providers import get_ai_provider

    with pytest.raises(ValueError) as exc:
        get_ai_provider("proveedor-inexistente")
    assert "no soportado" in str(exc.value)


def test_anadir_un_proveedor_es_una_clase_y_una_linea() -> None:
    """La prueba del objetivo 5: registrar el nuevo no exige tocar `core/`."""
    from config import providers

    providers.PROVEEDORES["prueba"] = ProveedorDePrueba
    try:
        assert isinstance(providers.get_ai_provider("prueba"), ProveedorDePrueba)
    finally:
        del providers.PROVEEDORES["prueba"]


def test_el_traductor_acepta_cualquier_proveedor_inyectado() -> None:
    """El traductor era el único punto de `core/` que sabía con quién hablaba."""
    from core.query_translator import QueryTranslator

    traductor = QueryTranslator(ai_provider=ProveedorDePrueba())
    resultado = traductor.translate_prompt_to_chroma("ingeniero civil")

    assert resultado.query_text_conceptual == "prueba"
    assert resultado.where_filter == {}
