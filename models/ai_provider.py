"""Capa de abstraccion para gestionar la inferencia y los pipelines de vision computacional contra endpoints LLM locales o en la nube."""

import json
import base64
import re
from openai import OpenAI
import ollama
from config import settings
from models.schemas import VacancyStructure, CandidateStructure

class OpenAIProvider:
    """Gestiona la extraccion profunda de datos no estructurados mediante endpoints de OpenAI con ejecucion de Structured Outputs."""
    
    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.MODEL_NAME

    def _encode_image(self, image_path: str) -> str:
        """Codifica un activo de archivo local en formato de cadena binaria base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def parse_cv_images_to_json(self, image_paths: list) -> CandidateStructure:
        """Procesa imagenes de alta resolucion de un CV para transformar componentes no estructurados en una entidad de datos rigida."""
        system_prompt = "Usted es un parser de vision computacional para sistemas ATS corporativos. Mapee los elementos del documento segun el esquema solicitado."
        content = [{"type": "text", "text": "Extraiga todas las entidades tecnicas y personales de las imagenes del currículum provisto."}]
        
        for path in image_paths:
            base64_image = self._encode_image(path)
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{base64_image}"}
            })

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            response_format=CandidateStructure
        )
        return completion.choices[0].message.parsed

    def parse_vacancy(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Transforma descripciones no estructuradas de ofertas de empleo en un esquema corporativo estandarizado."""
        system_prompt = "Usted es un motor de ingesta de ofertas de empleo. Convierta publicaciones corporativas no estructuradas en parametros de esquema validos."
        
        if image_paths:
            content = [{"type": "text", "text": "Extraiga y estructure los requisitos de la vacante contenidos en estas de imagenes."}]
            for path in image_paths:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{self._encode_image(path)}"} })
        else:
            content = f"Procese y estructure la siguiente oferta de empleo:\n\n{raw_text}"

        completion = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content}],
            response_format=VacancyStructure
        )
        return completion.choices[0].message.parsed

    def reconcile_vacancy_name(self, nuevo_titulo: str, colecciones_existentes: list) -> str:
        """Ejecuta la resolucion semantica de entidades para evaluar correspondencia con colecciones existentes."""
        if not colecciones_existentes: 
            return "NUEVA"
            
        system_prompt = "Compare el nuevo titulo contra los indices activos de produccion. Mapee variaciones o ediciones a colecciones existentes o retorne 'NUEVA' para registros netamente nuevos."
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": f"Nuevo Titulo: '{nuevo_titulo}'\nColecciones Activas: {colecciones_existentes}"}],
            temperature=0.0
        )
        return response.choices[0].message.content.strip()


class LocalOllamaProvider:
    """Gestiona el analisis profundo de documentos mediante modelos locales contenedorizados."""
    
    def __init__(self):
        self.model = settings.MODEL_NAME

    def _extract_clean_json(self, raw_text: str) -> str:
        """Sanea y extrae unicamente el bloque JSON de respuestas conversacionales o contaminadas."""
        # 1. Eliminar tokens de control internos que Qwen pueda escupir por error
        cleaned_text = re.sub(r'<\|.*?\|>', '', raw_text) 
        
        # 2. Extraer el bloque JSON puro si el modelo uso markdown (```json ... ```)
        if "```json" in cleaned_text:
            return cleaned_text.split("```json")[1].split("```")[0].strip()
        elif "```" in cleaned_text:
            return cleaned_text.split("```")[1].strip()
            
        # Si no uso markdown, encontrar el primer '{' y el ultimo '}'
        start_idx = cleaned_text.find('{')
        end_idx = cleaned_text.rfind('}')
        if start_idx != -1 and end_idx != -1:
            return cleaned_text[start_idx:end_idx+1].strip()
            
        return cleaned_text.strip()

    def parse_cv_images_to_json(self, image_paths: list) -> CandidateStructure:
        """Procesa objetos graficos de curriculos mediante pipelines locales de vision."""
        
        # --- Prompt Engineering Estricto con Esquema Forzado ---
        system_prompt = """
        Eres un extractor de datos de CVs experto. Analiza la imagen y extrae la informacion de forma concisa.
        REGLA CRITICA: Tu respuesta DEBE ser EXCLUSIVAMENTE un objeto JSON valido usando EXACTAMENTE este esquema:
        {
            "nombre_completo": "Nombre del candidato",
            "correo_electronico": "Correo",
            "telefono_movil": "Telefono",
            "ubicacion": "Ciudad y Pais de residencia (o 'No especificada')",
            "nivel_academico_maximo": "El nivel educativo mas alto alcanzado (ej. Profesional, Maestria)",
            "educacion_detalle": ["Titulo 1 - Institucion", "Titulo 2 - Institucion"],
            "anios_experiencia_total": 5, 
            "historial_laboral": [
                {"empresa": "Nombre Empresa 1", "cargo": "Titulo del Rol", "duracion_anios": 3.5},
                {"empresa": "Nombre Empresa 2", "cargo": "Titulo del Rol", "duracion_anios": 1.5}
            ],
            "perfil_profesional": "Resumen",
            "hard_skills": ["skill1", "skill2"],
            "soft_skills": ["skill1", "skill2"]
        }
        Calcula matematicamente los 'anios_experiencia_total' sumando las duraciones. Debe ser un numero entero.
        No cambies los nombres de las claves. No agregues claves nuevas. Solo devuelve el bloque JSON.
        """
        
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": "Extrae los datos de este CV en formato JSON estricto respetando el esquema:", "images": image_paths}
            ],
            options={
                "num_ctx": 8192,
                "num_predict": -1,
                "temperature": 0.0
            }
        )
        
        raw_content = response["message"]["content"]
        json_limpio = self._extract_clean_json(raw_content)
        
        return CandidateStructure.model_validate_json(json_limpio)
        

    def parse_vacancy(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Transforma una descripcion de cargo en un layout JSON estructurado."""
        system_prompt = """
        Estructure los parametros de datos provistos.
        REGLA CRITICA: Devuelve UNICAMENTE un objeto JSON valido. Cero explicaciones extra.
        """
        content = f"Estructure los siguientes parametros:\n\n{raw_text}" if raw_text else "Extraiga atributos desde el archivo grafico:"
        images = image_paths if image_paths else []

        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt}, 
                {"role": "user", "content": content, "images": images}
            ],
            options={
                "num_ctx": 8192,      # Expande la memoria total a 8K tokens
                "num_predict": -1,    # -1 significa generacion infinita
                "temperature": 0.0
            }
        )
        
        json_limpio = self._extract_clean_json(response["message"]["content"])
        return VacancyStructure.model_validate_json(json_limpio)

    def reconcile_vacancy_name(self, nuevo_titulo: str, colecciones_existentes: list) -> str:
        """Resuelve la distancia semantica de strings sobre esquemas activos."""
        if not colecciones_existentes: 
            return "NUEVA"
            
        prompt = f"Evalue si la entrada '{nuevo_titulo}' coincide con el contexto de metadatos de alguno de estos indices: {colecciones_existentes}. Responda exclusivamente con la cadena del indice o devuelva la palabra 'NUEVA'."
        response = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
        return response["message"]["content"].strip()