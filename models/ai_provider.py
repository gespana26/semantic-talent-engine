"""Capa de abstraccion para gestionar la inferencia y los pipelines de vision computacional contra endpoints LLM locales o en la nube."""

import json
import base64
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
    """Gestiona el analisis profundo de documentos mediante modelos locales contenedorizados con esquemas forzados de sintaxis JSON."""
    
    def __init__(self):
        self.model = settings.MODEL_NAME

    def parse_cv_images_to_json(self, image_paths: list) -> CandidateStructure:
        """Procesa objetos graficos de curriculos mediante pipelines locales de vision para extraer capas de datos no estructuradas."""
        system_prompt = "Extraiga las metricas del candidato de la imagen de origen. La salida debe coincidir rigurosamente con los campos estructurados en formato JSON crudo."
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": "Analice el perfil del CV:", "images": image_paths}],
            format="json"
        )
        return CandidateStructure.model_validate_json(response["message"]["content"].strip())

    def parse_vacancy(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Transforma una descripcion de cargo en un layout JSON estructurado utilizando pesos multimodales locales."""
        system_prompt = "Estructure los parametros de datos provistos dentro del formato de esquema transaccional solicitado."
        content = f"Estructure los siguientes parametros de requerimiento:\n\n{raw_text}" if raw_text else "Extraiga atributos de perfil desde el archivo grafico:"
        images = image_paths if image_paths else []

        response = ollama.chat(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": content, "images": images}],
            format="json"
        )
        return VacancyStructure.model_validate_json(response["message"]["content"].strip())

    def reconcile_vacancy_name(self, nuevo_titulo: str, colecciones_existentes: list) -> str:
        """Resuelve la distancia semantica de strings sobre esquemas de almacenamiento activos de forma local para garantizar la idempotencia."""
        if not colecciones_existentes: 
            return "NUEVA"
            
        prompt = f"Evalue si la entrada '{nuevo_titulo}' coincide con el contexto de metadatos de alguno de estos indices: {colecciones_existentes}. Responda exclusivamente con la cadena del indice o devuelva la palabra 'NUEVA'."
        response = ollama.chat(model=self.model, messages=[{"role": "user", "content": prompt}])
        return response["message"]["content"].strip()