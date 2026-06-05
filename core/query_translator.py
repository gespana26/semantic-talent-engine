import json
import ollama
from pydantic import ValidationError
from models.schemas import ChromaQueryStructure
from config import settings

class LocalQueryTranslator:
    def __init__(self):
        self.model_name = settings.MODEL_NAME
        self.system_prompt = """
        Eres un experto en la base de datos vectorial ChromaDB.
        Traduce el requerimiento del reclutador en esta estructura JSON exacta:
        {
            "query_text_conceptual": "conceptos abstractos de habilidades o roles",
            "where_filter": { ... filtros basados en metadatos ... }
        }
        Reglas de filtrado para 'where_filter':
        - Búsqueda parcial por palabra: {"campo": {"$contains": "Valor"}}.
        - Múltiples condiciones: Usa {"$and": [{"c1": {"$contains": "A"}}, {"c2": {"$contains": "B"}}]}.
        Campos válidos: 'hard_skills', 'soft_skills'. Si no hay filtros obligatorios, devuelve {}.
        Responde exclusivamente con el objeto JSON puro.
        """

    def translate_prompt_to_chroma(self, prompt_reclutador: str) -> ChromaQueryStructure:
        try:
            response = ollama.chat(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": f"Traduce: '{prompt_reclutador}'"}
                ],
                format="json"
            )
            raw_content = response["message"]["content"].strip()
            # Valida e inmuniza la respuesta del modelo mediante Pydantic
            return ChromaQueryStructure.model_validate_json(raw_content)
        except ValidationError as ve:
            raise RuntimeError(f"La IA local falló al estructurar el JSON de consulta: {ve}")
        except Exception as e:
            raise RuntimeError(f"Error en traducción local: {e}")