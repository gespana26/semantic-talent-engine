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


# ---------------------------------------------------------------------------
# Requisitos de configuración del proveedor
# ---------------------------------------------------------------------------


def test_openai_sin_clave_falla_al_elegir_el_proveedor(monkeypatch) -> None:
    """El fallo se adelanta al momento de decidir, en vez de aflorar en la extracción."""
    from config import providers, settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError) as exc:
        providers.get_ai_provider("openai")

    assert "OPENAI_API_KEY" in str(exc.value)


def test_el_mensaje_ofrece_la_alternativa_local(monkeypatch) -> None:
    """Un error de configuración que no dice cómo salir del paso cuesta una sesión."""
    from config import providers, settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "   ")
    with pytest.raises(ValueError) as exc:
        providers.verificar_configuracion() if settings.AI_PROVIDER_TYPE == "openai" \
            else providers.get_ai_provider("openai")

    assert "ollama" in str(exc.value).lower()


def test_ollama_no_exige_credenciales(monkeypatch) -> None:
    """El proveedor local no declara requisitos: no puede fallar por falta de clave."""
    from config import providers, settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    monkeypatch.setattr(settings, "AI_PROVIDER_TYPE", "ollama")
    providers.verificar_configuracion()


def test_verificar_configuracion_sigue_al_proveedor_declarado(monkeypatch) -> None:
    """Comprueba lo que exige el proveedor configurado, no todos los posibles."""
    from config import providers, settings

    monkeypatch.setattr(settings, "AI_PROVIDER_TYPE", "openai")
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "")
    with pytest.raises(ValueError):
        providers.verificar_configuracion()

    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-una-clave-cualquiera")
    providers.verificar_configuracion()


# ---------------------------------------------------------------------------
# Las vistas no deciden
# ---------------------------------------------------------------------------


def test_ninguna_vista_decide_el_proveedor() -> None:
    """Regresión de 2.2: el `if AI_PROVIDER_TYPE` volvía a aparecer en `views/`.

    `config/providers.py` existe para que la elección viva en un solo sitio, y su
    docstring lo declara. Las vistas lo reintroducían en tres puntos, con el
    agravante de que devolvían `None` ante un valor desconocido: el fallo afloraba
    como `AttributeError: 'NoneType'` en mitad de la extracción en lugar del
    `ValueError` explícito del composition root.

    Se analiza el **árbol sintáctico** y no el texto del fichero. Un `grep` sobre
    el fuente también encuentra estos nombres dentro de un comentario que explica
    por qué se quitaron, y un test que obliga a no documentar lo que se corrigió
    empuja justo en la dirección contraria a la que este proyecto quiere.
    """
    import ast
    from pathlib import Path

    PROHIBIDOS = {"OpenAIProvider", "LocalOllamaProvider"}
    vistas = Path(__file__).resolve().parents[2] / "views"

    for fichero in sorted(vistas.glob("*.py")):
        arbol = ast.parse(fichero.read_text(encoding="utf-8"))
        importados, usados, atributos = set(), set(), set()

        for nodo in ast.walk(arbol):
            if isinstance(nodo, (ast.Import, ast.ImportFrom)):
                importados.update(alias.name for alias in nodo.names)
            elif isinstance(nodo, ast.Name):
                usados.add(nodo.id)
            elif isinstance(nodo, ast.Attribute):
                atributos.add(nodo.attr)

        assert not (PROHIBIDOS & importados), (
            f"{fichero.name} importa un proveedor concreto: "
            f"{sorted(PROHIBIDOS & importados)}"
        )
        assert not (PROHIBIDOS & usados), (
            f"{fichero.name} instancia un proveedor concreto: "
            f"{sorted(PROHIBIDOS & usados)}"
        )
        assert "AI_PROVIDER_TYPE" not in atributos | usados, (
            f"{fichero.name} vuelve a ramificar sobre AI_PROVIDER_TYPE."
        )


def test_el_traductor_acepta_cualquier_proveedor_inyectado() -> None:
    """El traductor era el único punto de `core/` que sabía con quién hablaba."""
    from core.query_translator import QueryTranslator

    traductor = QueryTranslator(ai_provider=ProveedorDePrueba())
    resultado = traductor.translate_prompt_to_chroma("ingeniero civil")

    assert resultado.query_text_conceptual == "prueba"
    assert resultado.where_filter == {}
