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
        
        ''' Para el PROMPT usamos la técnica Few-Shot Prompting (Inyección de Ejemplos)
        para enseñar al modelo a generar la estructura JSON exacta que necesitamos, incluyendo la lógica de filtrado.
        inicialmente, usamos (Zero-Shot), pero el modelo "qwen2.5vl" de 7 billones es incapaz de seguir una lista larga de reglas teóricas
        '''
        self.system_prompt = """
        You are an expert query translator for a ChromaDB Hybrid Search engine.
        Convert the user's free-text request exactly into the following JSON format:
        {
            "query_text_conceptual": "Cleaned keywords for semantic search",
            "where_filter": { ... }
        }

        --- EXAMPLES OF CORRECT BEHAVIOR (LEARN THESE PATTERNS) ---
        
        User input: "Ingeniero Industrial OBLIGATORIO. Con fuertes habilidades de multitasking"
        Output: 
        {
            "query_text_conceptual": "Industrial Engineer, Ingeniero Industrial, multitasking skills, habilidades de multitarea, problem solving, resolucion de problemas",
            "where_filter": {
                "$or": [
                    {"perfil_profesional": {"$contains": "Ingeniero Industrial"}},
                    {"perfil_profesional": {"$contains": "Industrial Engineer"}}
                ]
            }
        }

        User input: "Experiencia en AWS, excluyente que sea Desarrollador Backend"
        Output:
        {
            "query_text_conceptual": "Backend development, desarrollo backend, AWS cloud, nube AWS, software architecture",
            "where_filter": {
                "$or": [
                    {"perfil_profesional": {"$contains": "Desarrollador Backend"}},
                    {"perfil_profesional": {"$contains": "Backend Developer"}}
                ]
            }
        }

        User input: "Que sepa mucho de SAP, finanzas y contabilidad"
        Output:
        {
            "query_text_conceptual": "SAP ERP, finance, finanzas, accounting, contabilidad, financial analysis",
            "where_filter": {}
        }
        -----------------------------------------------------------

        CRITICAL RULES FOR GENERATION:
        1. NEVER include instruction words (like 'OBLIGATORIO', 'EXCLUYENTE', 'MANDATORY') inside 'query_text_conceptual'. Those words destroy the mathematical vector semantics.
        2. BILINGUAL CONCEPTUALIZATION: In 'query_text_conceptual', ALWAYS include the core concepts in BOTH Spanish and English separated by commas. This guarantees mathematical vector proximity regardless of the CV's original language.
        3. ONLY output a populated 'where_filter' if the user explicitly typed 'OBLIGATORIO', 'EXCLUYENTE' or 'DEBE TENER'. Otherwise, leave it as {}.
        4. PRESERVE THE FULL EXACT PHRASE: When a mandatory profession/role is requested, NEVER summarize it into a single root word. You MUST use the exact full phrase (e.g., "Ingeniero Industrial" or "Desarrollador Backend") inside the "$contains" operator.
        5. Return ONLY a valid JSON object. No markdown formatting outside the JSON, no explanations.
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