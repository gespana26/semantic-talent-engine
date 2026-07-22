"""Capa de abstraccion para gestionar la inferencia y los pipelines de vision computacional contra endpoints LLM locales o en la nube."""

import base64
import re

import ollama
from openai import OpenAI as _NativeOpenAI

from config import settings
from core.json_sanitizer import extraer_json
from models.interfaces import BaseLLMProvider
from models.observability import _update_generation, get_langfuse_client, observe
from models.schemas import CandidateStructure, VacancyStructure

# Semilla compartida por todas las llamadas de extraccion. Junto con
# temperature=0 hace que el pipeline sea reproducible: el mismo documento
# produce el mismo perfil en ejecuciones distintas.
RANDOM_SEED = settings.RANDOM_SEED

class OpenAIProvider(BaseLLMProvider):
    """Gestiona la extraccion profunda de datos no estructurados mediante endpoints de OpenAI con ejecucion de Structured Outputs."""

    def __init__(self):
        # Drop-in tracing de Langfuse: si LANGFUSE_ENABLED, sustituimos el SDK
        # nativo por `langfuse.openai.OpenAI` inyectando el cliente configurado
        # con mask_pii. Si esta deshabilitado, usamos el SDK nativo de OpenAI.
        # En ambos casos los cuerpos de los metodos permanecen sin cambios.
        # Circuito de tracing: Langfuse se registra como cliente activo del
        # proceso al inicializarse. `langfuse.openai.OpenAI` lo detecta
        # automaticamente y aplica su configuracion (incluyendo mask_pii).
        # No se pasa langfuse_client explicitamente — la doc indica que la
        # integracion usa el cliente activo del proceso sin parametros extra.
        if get_langfuse_client() is not None:
            try:
                from langfuse.openai import OpenAI as _LangfuseOpenAI
                self.client = _LangfuseOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=1)
            except Exception:
                # Circuit breaker: caer al SDK nativo si la sustitucion falla.
                self.client = _NativeOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=1)
        else:
            self.client = _NativeOpenAI(api_key=settings.OPENAI_API_KEY, timeout=30.0, max_retries=1)
        self.model = settings.MODEL_NAME

    def _encode_image(self, image_path: str) -> str:
        """Codifica un activo de archivo local en formato de cadena binaria base64."""
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    def parse_cv_images_to_json(self, image_paths: list) -> CandidateStructure:
        """Procesa imagenes de alta resolucion de un CV para transformar componentes no estructurados en una entidad de datos rigida."""
        system_prompt = (
            "Usted es un parser de vision computacional para sistemas ATS corporativos. "
            "Mapee los elementos del documento segun el esquema solicitado. "
            "REGLA INNEGOCIABLE: si un dato de contacto (nombre, correo o telefono) no aparece "
            "literalmente en el documento, devuelva una cadena vacia. NUNCA invente, deduzca ni "
            "complete correos ni telefonos: un dato de contacto erroneo es peor que uno ausente."
        )
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
            response_format=CandidateStructure,
            # Extraer no es redactar: ante el mismo documento debe salir el mismo
            # perfil. Sin fijar estos parametros el modelo usa temperature=1.0, y
            # se midio el efecto: cuatro extracciones del mismo CV devolvieron
            # distinto numero de hard skills, de soft skills y hasta un valor
            # distinto de anios de experiencia. Esa variabilidad se propaga a la
            # cobertura de requisitos y, por tanto, a la afinidad del candidato.
            temperature=0.0,
            seed=RANDOM_SEED
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
            response_format=VacancyStructure,
            # Determinismo por el mismo motivo que en la extraccion del CV: los
            # requisitos que salgan de aqui son el criterio contra el que se mide
            # a todos los candidatos del silo.
            temperature=0.0,
            seed=RANDOM_SEED
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

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        """Completa un prompt devolviendo JSON crudo, sin esquema fijo.

        Es la operacion que sostiene al traductor de consultas. No usa Structured
        Outputs a proposito: el filtro que produce es un diccionario abierto, y
        `additionalProperties` lo prohibe. Esa es la limitacion tecnica que el
        traductor declara, no un descuido.
        """
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
            seed=RANDOM_SEED,
        )
        return extraer_json(response.choices[0].message.content)


class LocalOllamaProvider(BaseLLMProvider):
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
        return self._parse_cv_images_to_json_traced(image_paths)

    @observe()
    def _parse_cv_images_to_json_traced(self, image_paths: list) -> CandidateStructure:
        """Implementacion trazada del parseo de CV por imagenes (Ollama nativo).

        Token counts son best-effort: si el SDK de Ollama los expone se
        registran; si no, no se falla (requisito: Ollama token counts
        best-effort).
        """
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

        REGLA INNEGOCIABLE SOBRE DATOS DE CONTACTO: si el nombre, el correo o el telefono no
        aparecen literalmente en el documento, devuelve una cadena vacia ("") en ese campo.
        NUNCA inventes, deduzcas ni completes correos ni telefonos. Un dato de contacto erroneo
        es peor que uno ausente.
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

        # Token counts best-effort desde la respuesta de Ollama
        prompt_tokens = response.get("prompt_eval_count")
        completion_tokens = response.get("eval_count")
        if prompt_tokens is not None or completion_tokens is not None:
            _update_generation(
                prompt_tokens=prompt_tokens or 0,
                completion_tokens=completion_tokens or 0,
            )
        
        raw_content = response["message"]["content"]
        json_limpio = self._extract_clean_json(raw_content)
        
        return CandidateStructure.model_validate_json(json_limpio)
        

    def parse_vacancy(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Transforma una descripcion de cargo en un layout JSON estructurado."""
        return self._parse_vacancy_traced(raw_text, image_paths)

    @observe()
    def _parse_vacancy_traced(self, raw_text: str = None, image_paths: list = None) -> VacancyStructure:
        """Implementacion trazada del parseo de vacante (Ollama nativo)."""
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
        return self._reconcile_vacancy_name_traced(nuevo_titulo, colecciones_existentes)

    @observe()
    def _reconcile_vacancy_name_traced(self, nuevo_titulo: str, colecciones_existentes: list) -> str:
        """Implementacion trazada de la reconciliacion de nombre (Ollama nativo)."""
        if not colecciones_existentes:
            return "NUEVA"

        prompt = f"Evalue si la entrada '{nuevo_titulo}' coincide con el contexto de metadatos de alguno de estos indices: {colecciones_existentes}. Responda exclusivamente con la cadena del indice o devuelva la palabra 'NUEVA'."
        response = ollama.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            # Sin fijarla, Ollama aplica su propia temperatura por defecto. Esta
            # llamada decide si una vacante se actualiza o se duplica: debe dar
            # siempre la misma respuesta ante la misma entrada.
            options={"temperature": 0.0, "seed": RANDOM_SEED}
        )
        return response["message"]["content"].strip()

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        """Equivalente local. `format="json"` induce JSON pero no lo garantiza.

        Por eso pasa por el mismo saneador que la extraccion: tener dos limpiezas
        distintas para el mismo problema fue lo que dejo al traductor sin
        proteccion mientras la extraccion si la tenia.
        """
        return self._complete_json_traced(system_prompt, user_prompt)

    @observe()
    def _complete_json_traced(self, system_prompt: str, user_prompt: str) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            format="json",
            options={"temperature": 0.0, "seed": RANDOM_SEED},
        )
        return extraer_json(response["message"]["content"])