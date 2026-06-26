"""Modulo para la gestion de la configuracion del sistema, variables de entorno y utilidades de normalizacion."""

import os
import re
from dotenv import load_dotenv

# Cargar las variables del archivo .env local
load_dotenv()

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

def clean_collection_name(cargo_name: str) -> str:
    """Normaliza texto arbitrario segun el esquema estricto de nomenclatura de colecciones de ChromaDB."""
    cleaned = cargo_name.lower().strip()
    cleaned = re.sub(r'[^a-z0-9\-_.]', '-', cleaned)  
    cleaned = re.sub(r'-+', '-', cleaned)             
    return cleaned[:63].strip('-')