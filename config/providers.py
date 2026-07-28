"""Punto único donde se elige el proveedor de inferencia.

Antes, la decisión estaba repetida en cinco sitios —`main.py`, el portal, el
dashboard dos veces y el traductor de consultas— cada uno con su propio `if`
sobre `AI_PROVIDER_TYPE`. Añadir un tercer proveedor obligaba a encontrarlos
todos, y uno de ellos vivía dentro de `core/`, lo que contradecía la promesa de
"cero cambios en la lógica de negocio al cambiar de proveedor".

Concentrarlo aquí deja la incorporación de un proveedor nuevo en una clase más y
una línea en el registro. Nada de `core/` ni de `views/` cambia.

**No es una Factory del catálogo GoF.** No hay jerarquía de fábricas ni
polimorfismo en la creación: es el borde de la aplicación donde se resuelve qué
estrategia concreta se inyecta, coherente con el patrón Strategy que describe la
memoria. La distinción importa porque el documento afirma usar Strategy con
inyección de dependencias, no Factory.

**La carga es diferida a propósito.** Cada proveedor se importa solo cuando se
elige, de modo que instalar el SDK de uno no obliga a instalar el del otro. Un
despliegue que solo use el modelo local no necesita la biblioteca de OpenAI, y
un proveedor nuevo puede probarse sin tener ninguno de los dos.
"""

import importlib

from config import settings
from models.interfaces import BaseLLMProvider

# El valor puede ser una clase ya cargada o la pareja (módulo, clase) que se
# resolverá en el momento de usarla.
PROVEEDORES = {
    "openai": ("models.ai_provider", "OpenAIProvider"),
    "ollama": ("models.ai_provider", "LocalOllamaProvider"),
}


# Configuración que cada proveedor necesita para poder trabajar. Se declara aquí
# y no dentro de la clase porque es una condición del despliegue, no del
# algoritmo: qué credenciales hacen falta depende de a quién se decida llamar, y
# esa decisión se toma en este módulo.
REQUISITOS = {
    "openai": ("OPENAI_API_KEY", "la clave de API de OpenAI"),
}


def _resolver(destino):
    """Obtiene la clase del proveedor, importándola solo si hace falta."""
    if isinstance(destino, type):
        return destino
    modulo, nombre = destino
    return getattr(importlib.import_module(modulo), nombre)


def _verificar_requisitos(clave: str) -> None:
    """Comprueba que el proveedor elegido tiene lo que necesita para funcionar.

    `OPENAI_API_KEY` caía antes a `"placeholder_key_clean"`, y con ese valor el
    cliente se construye sin protestar. El fallo no aparecía aquí sino mucho
    después, ya dentro de la extracción, con el texto «Fallo crítico en el
    procesamiento multimodal» —que no menciona la clave— o como un 401 de OpenAI
    a mitad de una postulación. Comprobarlo en el momento de elegir el proveedor
    convierte media sesión de diagnóstico en una línea de error.
    """
    requisito = REQUISITOS.get(clave)
    if requisito is None:
        return
    variable, descripcion = requisito
    if not str(getattr(settings, variable, "") or "").strip():
        raise ValueError(
            f"El proveedor '{clave}' necesita {descripcion}, y {variable} está "
            f"vacía o no definida. Declárela en el .env:\n"
            f"  {variable}=<su valor>\n"
            f"O cambie de proveedor con AI_PROVIDER_TYPE=ollama, que se ejecuta "
            f"en local y no requiere credenciales."
        )


def verificar_configuracion() -> None:
    """Valida al arrancar lo que de otro modo fallaría en mitad de una extracción.

    Se invoca desde los puntos de entrada (`app.py`, `main.py`). Es el mismo
    criterio que sigue `core.security.verificar_configuracion`: una configuración
    incompleta debe impedir el arranque, no degradar el comportamiento a mitad de
    camino y con un mensaje que no señala la causa.
    """
    _verificar_requisitos(str(settings.AI_PROVIDER_TYPE or "").lower().strip())


def get_ai_provider(tipo: str = None) -> BaseLLMProvider:
    """Devuelve la implementación configurada del contrato `BaseLLMProvider`.

    `tipo` permite forzar un proveedor concreto, lo que sirve sobre todo para
    pruebas; en ejecución normal se toma de la configuración.
    """
    clave = str(tipo or settings.AI_PROVIDER_TYPE or "").lower().strip()
    destino = PROVEEDORES.get(clave)
    if destino is None:
        raise ValueError(
            f"Proveedor de IA no soportado: '{clave}'. "
            f"Disponibles: {', '.join(sorted(PROVEEDORES))}."
        )
    _verificar_requisitos(clave)
    return _resolver(destino)()
