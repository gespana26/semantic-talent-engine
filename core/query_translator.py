"""Modulo que actua como motor de traduccion interna de consultas, mapeando solicitudes linguisticas libres en propiedades logicas."""

import json
from openai import OpenAI
import ollama
from pydantic import ValidationError
from models.schemas import ChromaQueryStructure
from config import settings

class QueryTranslator:
    """Compilador NLI encargado de transformar requerimientos textuales en logica binaria de consulta estructurada."""
    
    def __init__(self):
        self.provider_type = settings.AI_PROVIDER_TYPE
        self.model_name = settings.MODEL_NAME
        
        if self.provider_type == "openai":
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            
        self.system_prompt = """
        You are a backend query translation module for ChromaDB.
        Compile the user text requirement strictly into this target JSON response schema:
        {
            "query_text_conceptual": "Clean keyword abstraction for spatial dense vector creation",
            "where_filter": { ... structured metadata constraint logic mapping ... }
        }
        Operational Filtering Schema Guidelines for 'where_filter':
        - Sub-string inclusion evaluation matches: {"target_field": {"$contains": "RequiredValue"}}.
        - Composite boolean grouping structures: Always utilize the {"$and": [ {...}, {...} ]} array architecture.
        Available indexed filter fields: 'hard_skills', 'soft_skills'. Return an empty object {} if no rigid hard requirements exist.
        Do not append conversational text, markdown tokens or preambles, output raw valid JSON string content only.
        """

    def _translate_via_openai(self, prompt_reclutador: str) -> ChromaQueryStructure:
        """Metodo independiente para OpenAI utilizando JSON Object Mode para dar soporte a diccionarios dinamicos."""
        response = self.openai_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Compile the following block: '{prompt_reclutador}'"}
            ],
            response_format={"type": "json_object"}  # Evita la restriccion de additionalProperties
        )
        raw_content = response.choices[0].message.content.strip()
        return ChromaQueryStructure.model_validate_json(raw_content)

    def _translate_via_ollama(self, prompt_reclutador: str) -> ChromaQueryStructure:
        """Metodo independiente para Ollama utilizando el motor de inferencia local."""
        response = ollama.chat(
            model=self.model_name,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": f"Compile the following block: '{prompt_reclutador}'"}
            ],
            format="json"
        )
        raw_content = response["message"]["content"].strip()
        return ChromaQueryStructure.model_validate_json(raw_content)

    def translate_prompt_to_chroma(self, prompt_reclutador: str) -> ChromaQueryStructure:
        """Enrutador principal que delega la ejecucion al metodo independiente correspondiente."""
        try:
            if self.provider_type == "openai":
                return self._translate_via_openai(prompt_reclutador)
            elif self.provider_type == "ollama":
                return self._translate_via_ollama(prompt_reclutador)
            else:
                raise ValueError(f"Proveedor no soportado: {self.provider_type}")
                
        except ValidationError as ve:
            raise RuntimeError(f"Anomalia estructural en el esquema de salida durante la validacion del JSON compilado: {ve}")
        except Exception as e:
            raise RuntimeError(f"Fallo en el pipeline de traduccion al conectar con el proveedor ({self.provider_type}): {e}")