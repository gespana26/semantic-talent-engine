"""Modulo que actua como motor de traduccion interna de consultas, mapeando solicitudes linguisticas libres en propiedades logicas."""

from pydantic import ValidationError

from config.providers import get_ai_provider
from models.schemas import ChromaQueryStructure


class QueryTranslator:
    """Compilador NLI encargado de transformar requerimientos textuales en logica binaria de consulta estructurada."""
    
    def __init__(self, ai_provider=None):
        """Recibe el proveedor ya construido en lugar de elegirlo.

        Este componente instanciaba su propio cliente y ramificaba con `if/elif`
        segun `AI_PROVIDER_TYPE`. Era el unico punto de `core/` que sabia contra
        que proveedor hablaba, y por eso anadir un tercero exigia tocar la logica
        de negocio pese a la promesa contraria del objetivo 5. Ahora solo conoce
        el contrato `BaseLLMProvider`.
        """
        self.ai_provider = ai_provider or get_ai_provider()
        
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

    def translate(self, prompt_reclutador: str) -> ChromaQueryStructure:
        """Compila la consulta con el proveedor inyectado, sea cual sea."""
        crudo = self.ai_provider.complete_json(
            system_prompt=self.system_prompt,
            user_prompt=f"Compile the following block: '{prompt_reclutador}'"
        )
        return ChromaQueryStructure.model_validate_json(crudo)

    def translate_prompt_to_chroma(self, prompt_reclutador: str) -> ChromaQueryStructure:
        """Punto de entrada publico. Se conserva el nombre para no romper a las vistas."""
        try:
            return self.translate(prompt_reclutador)
        except ValidationError as ve:
            raise RuntimeError(
                f"Anomalia estructural en el esquema de salida durante la validacion del JSON compilado: {ve}"
            )
        except Exception as e:
            raise RuntimeError(f"Fallo en el pipeline de traduccion de la consulta: {e}")
