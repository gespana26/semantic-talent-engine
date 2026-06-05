import json
from openai import OpenAI
from config import settings
from models.schemas import VacancyStructure, ChromaQueryStructure

class OpenAIProvider:
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.MODEL_NAME

    def parse_cv_images_to_json(self, image_paths: list) -> dict:
        """Procesa las imágenes de un CV y extrae el árbol de entidades."""
        # Nota: Aquí va tu prompt detallado de extracción de candidatos que definiste previamente
        prompt_sistema = "Extrae los datos de este currículum en formato JSON estructurado..."
        
        # Simulación de llamada multimodal standard (se omiten detalles de base64 por brevedad)
        # ... lógica de codificación de imágenes ...
        
        # Inferencia simulada (reemplazar con tu estructura real de completions)
        response_content = '{"nombre_completo": "Juan Perez", "correo": "juan@mail.com", "skills": "Python"}' 
        
        # --- CONTROL DE DEPURACIÓN SOLICITADO ---
        if settings.DEBUG_MODE:
            print("\n[DEBUG IA] === CONTENIDO CRUDO RECIBIDO DE OPENAI ===")
            print(response_content)
            print("[DEBUG IA] ===========================================" + "\n")
            
        return json.loads(response_content)

    def parse_vacancy(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Estructura una oferta de empleo a partir de texto o imágenes del PDF."""
        system_prompt = "Eres un experto en reclutamiento. Analiza la vacante y extrae sus componentes clave."
        
        if image_paths:
            content = [{"type": "text", "text": "Analiza las imágenes de la vacante."}, 
                       {"type": "image_url", "image_url": {"url": "..."}}] # Lógica base64
        else:
            content = f"Estructura la siguiente vacante laboral:\n\n{raw_text}"

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            response_format=VacancyStructure
        )
        return completion.choices[0].message.parsed

    def reconcile_vacancy_name(self, nuevo_titulo: str, colecciones_existentes: list) -> str:
        """Detecta variaciones lingüísticas para evitar duplicación de vacantes (Idempotencia)."""
        if not colecciones_existentes:
            return "NUEVA"

        system_prompt = (
            "Compara el título de la vacante contra las tablas de la BD. "
            "Si es una edición de una existente, devuelve ÚNICAMENTE el nombre de la tabla. "
            "Si es una posición totalmente diferente, devuelve la palabra: 'NUEVA'."
        )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Nuevo: '{nuevo_titulo}'\nExistentes: {colecciones_existentes}"}
            ],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()