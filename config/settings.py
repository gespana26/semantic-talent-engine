"""Modulo para la gestion de la configuracion del sistema, variables de entorno y utilidades de normalizacion."""

import os
import re
import logging
from dotenv import load_dotenv

# Cargar las variables del archivo .env local
load_dotenv()

logger = logging.getLogger(__name__)

# --- RUTAS DE INFRAESTRUCTURA Y PERSISTENCIA DE DATOS ---
CHROMA_DB_PATH = "./storage/chroma_vector_db"
LOCAL_STORAGE_CV_PATH = "./storage/cv_files"
OLLAMA_EMBEDDINGS_ENDPOINT = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

# --- CONFIGURACION DINAMICA DESDE EL ENTORNO (.env) ---
AI_PROVIDER_TYPE = os.getenv("AI_PROVIDER_TYPE", "openai")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "placeholder_key_clean")

# --- CONFIGURACIÓN DE CORREO ELECTRÓNICO ---
EMAIL_SENDER_USER = os.getenv("EMAIL_SENDER_USER")
EMAIL_SENDER_PASSWORD = os.getenv("EMAIL_SENDER_PASSWORD")
EMAIL_RECRUITER_TARGET = os.getenv("EMAIL_RECRUITER_TARGET")

# --- OBSERVABILIDAD DEL SISTEMA ---
# Convertimos el string del .env a un booleano real
DEBUG_MODE = os.getenv("DEBUG_MODE", "True").lower() in ("true", "1", "t")

# --- OBSERVABILIDAD LLM (LANGFUSE) ---
# Dual backend: self-hosted (http://localhost:3000) o cloud (https://cloud.langfuse.com).
LANGFUSE_HOST = os.getenv("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_PUBLIC_KEY = os.getenv("LANGFUSE_PUBLIC_KEY", "")
LANGFUSE_SECRET_KEY = os.getenv("LANGFUSE_SECRET_KEY", "")
LANGFUSE_ENABLED = os.getenv("LANGFUSE_ENABLED", "False").lower() in ("true", "1", "t")

# Validacion: si LANGFUSE_ENABLED=True pero faltan claves, deshabilitar el tracing
# de forma silenciosa y emitir una advertencia clara. Observabilidad NUNCA debe
# romper el parsing.
if LANGFUSE_ENABLED:
    _missing_keys = [
        name for name, value in (
            ("LANGFUSE_PUBLIC_KEY", LANGFUSE_PUBLIC_KEY),
            ("LANGFUSE_SECRET_KEY", LANGFUSE_SECRET_KEY),
        ) if not value
    ]
    if _missing_keys:
        logger.warning(
            "Langfuse enabled but %s %s not set. Tracing disabled.",
            ", ".join(_missing_keys),
            "is" if len(_missing_keys) == 1 else "are",
        )
        LANGFUSE_ENABLED = False

def clean_collection_name(cargo_name: str) -> str:
    """Normaliza texto arbitrario segun el esquema estricto de nomenclatura de colecciones de ChromaDB."""
    cleaned = cargo_name.lower().strip()
    cleaned = re.sub(r'[^a-z0-9\-_.]', '-', cleaned)  
    cleaned = re.sub(r'-+', '-', cleaned)             
    return cleaned[:63].strip('-')