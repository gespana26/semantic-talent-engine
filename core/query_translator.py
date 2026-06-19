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
        You are a backend query translation module for ChromaDB Hybrid Search.
        Compile the user text requirement strictly into this target JSON response schema:
        {
            "query_text_conceptual": "The exact keywords, technologies, and semantic intent for dense vector search",
            "where_filter": { ... }
        }
        
        CRITICAL HYBRID SEARCH RULES:
        1. DO NOT use 'where_filter' for general skills, software, or technologies.
        2. Put ALL technologies, tools, and keywords directly into 'query_text_conceptual' so the semantic vector engine can find them natively (e.g., "Experience with SAP, JDEdwards, MFGPro, SIIGO").
        3. ONLY use 'where_filter' if the user explicitly states a requirement is MANDATORY (using words like 'Obligatorio', 'Excluyente', 'Debe tener').
        4. If a mandatory filter is needed, use: {"target_field": {"$contains": "Value"}}. Available fields: 'hard_skills', 'soft_skills'.
        5. If no explicit mandatory constraints exist, ALWAYS return an empty object {} for 'where_filter'.
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