"""Contrato que deben cumplir los proveedores de inferencia.

La interfaz declaraba un solo método y ninguna clase la heredaba: los
proveedores encajaban por *duck typing*, de modo que el contrato existía en la
memoria del proyecto pero no en el código. Aquí se completa con las cuatro
operaciones que el dominio necesita y ambos proveedores pasan a heredarla.

`complete_json` es la que faltaba, y es la que cierra el hueco de verdad. El
traductor de consultas era el único componente que instanciaba su propio cliente
y ramificaba con `if/elif` según el proveedor configurado, lo que contradecía la
promesa de "cero cambios en la lógica de negocio al cambiar de proveedor":
añadir un tercero obligaba a tocar también `core/`. Con esta operación en la
interfaz, el traductor recibe un proveedor y deja de saber cuál es.
"""

from abc import ABC, abstractmethod
from typing import Any, List


class BaseLLMProvider(ABC):
    """Interfaz abstracta para desacoplar el dominio de un proveedor específico de IA."""

    @abstractmethod
    def parse_cv_images_to_json(self, image_paths: List[str]) -> Any:
        """Convierte las imágenes de un currículum en un perfil estructurado y validado."""

    @abstractmethod
    def parse_vacancy(self, raw_text: str = None, image_paths: List[str] = None) -> Any:
        """Convierte una oferta de empleo, en texto o en imágenes, en una vacante estructurada."""

    @abstractmethod
    def reconcile_vacancy_name(self, nuevo_titulo: str, colecciones_existentes: List[str]) -> str:
        """Resuelve si un título corresponde a una vacante ya registrada o es nueva."""

    @abstractmethod
    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        """Devuelve la respuesta del modelo saneada como cadena JSON.

        Es la operación genérica sobre la que se apoya cualquier componente que
        necesite una salida estructurada sin un esquema fijo, como la traducción
        de consultas del reclutador: su filtro es un diccionario abierto y no
        puede expresarse con Structured Outputs.
        """
