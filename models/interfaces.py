from abc import ABC, abstractmethod
from typing import Dict, Any, List

class BaseLLMProvider(ABC):
    """Interfaz abstracta para desacoplar el orquestador de un proveedor específico de IA."""
    
    @abstractmethod
    def parse_cv_images_to_json(self, image_paths: List[str]) -> Dict[str, Any]:
        """Toma una lista de rutas de imágenes y devuelve el diccionario con los datos estructurados."""
        pass