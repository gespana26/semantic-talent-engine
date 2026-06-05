import os
import re

# --- CONFIGURACIÓN DE INFRAESTRUCTURA LOCAL ---
CHROMA_DB_PATH = "./storage/chroma_vector_db"
LOCAL_STORAGE_CV_PATH = "./storage/cv_files"
OLLAMA_EMBEDDINGS_ENDPOINT = "http://localhost:11434"
EMBEDDING_MODEL = "nomic-embed-text"

# --- CONFIGURACIÓN DE INTELIGENCIA ARTIFICIAL (CONMUTABLE) ---
# Cambiar a "gpt-4o-mini" u "ollama" según el entorno de pruebas
AI_PROVIDER_TYPE = "openai" 
MODEL_NAME = "gpt-4o-mini" # O el modelo local de Ollama (ej: 'gemma4:26b')
OPENAI_API_KEY = "tu_api_key_aqui"

# --- BANDERAS DE DEPURACIÓN PARA EL MVP ---
# True = Imprime el JSON crudo de la IA y CONSERVA las imágenes PNG temporales en disco
DEBUG_MODE = True 

# --- FUNCIONES UTILITARIAS DE INFRAESTRUCTURA ---
def clean_collection_name(cargo_name: str) -> str:
    """Normaliza nombres de cargos para cumplir estrictamente con las
    reglas de nombres de colecciones en ChromaDB.
    """
    cleaned = cargo_name.lower().strip()
    # Reemplaza cualquier carácter no alfanumérico por un guión
    cleaned = re.sub(r'[^a-z0-9\-_.]', '-', cleaned)  
    # Elimina guiones consecutivos duplicados
    cleaned = re.sub(r'-+', '-', cleaned)             
    return cleaned[:63].strip('-')