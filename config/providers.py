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


def _resolver(destino):
    """Obtiene la clase del proveedor, importándola solo si hace falta."""
    if isinstance(destino, type):
        return destino
    modulo, nombre = destino
    return getattr(importlib.import_module(modulo), nombre)


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
    return _resolver(destino)()
