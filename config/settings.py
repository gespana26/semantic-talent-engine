"""Modulo para la gestion de la configuracion del sistema, variables de entorno y utilidades de normalizacion."""

import logging
import os
import re

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

# --- DETERMINISMO DE LAS LLAMADAS AL LLM ---
# Extraer no es redactar. Se midió el efecto de no fijarlo: cuatro extracciones
# del mismo CV devolvieron distinto número de hard skills, de soft skills y hasta
# un valor distinto de años de experiencia, y esa variabilidad se propaga a la
# cobertura de requisitos y a la afinidad final.
RANDOM_SEED = int(os.getenv("RANDOM_SEED", "42"))

# --- CÁLCULO DE AFINIDAD POR COMPONENTES ---
# La afinidad no se deriva ya de la distancia de coseno directa: la medición
# mostró que su suelo empírico era el 84 % y que apenas separaba a un candidato
# pertinente de uno ajeno. Se compone de partes cuyo cero es un cero real.
PESO_COBERTURA = float(os.getenv("PESO_COBERTURA", "0.75"))
PESO_SIMILITUD = float(os.getenv("PESO_SIMILITUD", "0.25"))
# Suelo del multiplicador por titulación. Evita que un fallo de extracción del
# nivel académico (a veces devuelve genéricos como "Profesional") descarte por
# completo a un candidato válido.
PISO_FACTOR_PROFESION = float(os.getenv("PISO_FACTOR_PROFESION", "0.4"))
# Tamaño de la ventana que se re-puntúa con la fórmula compuesta (patrón
# retrieve-and-rerank). La recuperación vectorial trae 50 resultados; verificar
# requisito a requisito los 50 multiplicaría por diez el coste de una búsqueda
# para reordenar posiciones que nadie mira. Por encima de la ventana sigue
# mandando el orden vectorial, y esa es la limitación que hereda del techo de
# recall del post-filtrado.
# Tamaño de la ventana de re-puntuado. Se elevó de 20 a 100 al medir cuánto pesa
# realmente cada señal: el rango COMPLETO de la distancia vectorial vale 4,4
# puntos de afinidad, mientras que cubrir un requisito más vale entre 15 y 37,5.
# Ordenar por el vector para decidir a quién se le calcula la cobertura es
# ordenar por la señal que menos aporta, así que la ventana debe ser amplia.
TOP_N_RERANK = int(os.getenv("TOP_N_RERANK", "100"))

# Máximo de vecinos a recuperar. El valor efectivo se adapta al tamaño real de la
# colección: en un silo, que contiene los postulantes de una sola vacante, se
# recuperan todos y el techo de recall desaparece. El tope solo actúa sobre la
# bolsa global.
MAX_RECUPERACION = int(os.getenv("MAX_RECUPERACION", "500"))

# Margen bajo la línea base a partir del cual un perfil se considera no
# pertinente. Sustituye al umbral fijo de distancia 1.2, que exigía similitud
# coseno negativa y nunca llegó a activarse: las distancias reales del proyecto
# van de 0,18 a 0,36. Se exige estar claramente por debajo de un perfil ajeno, no
# solo empatar con él, porque se midió que un CV en inglés pierde ~26 puntos de
# similitud normalizada por el idioma y no debe caer por eso.
MARGEN_CORTE_PERTINENCIA = float(os.getenv("MARGEN_CORTE_PERTINENCIA", "0.02"))

# --- REGLA DE ALERTA DE AUTO-MATCH ---
# La afinidad absoluta no sostiene un umbral fijo: se comprime en una franja
# estrecha y crece con la longitud del texto de consulta. La alerta se decide con
# dos señales complementarias y verificables.
#
# 1. Cobertura de requisitos: qué proporción de las habilidades exigidas cumple
#    el candidato. Responde "¿cumple?", que es una pregunta absoluta.
UMBRAL_COBERTURA_REQUISITOS = float(os.getenv("UMBRAL_COBERTURA_REQUISITOS", "0.5"))
# Margen de contraste para aceptar dos habilidades como equivalentes ("Scrum"
# cubre "Metodologías ágiles"). No es una similitud absoluta: es cuánto debe
# superar la habilidad del candidato a la mejor de un conjunto de conceptos
# ajenos. Se mide así porque los embeddings ocupan un cono estrecho y una
# similitud alta, por sí sola, no significa parecido.
MARGEN_CONTRASTE_REQUISITO = float(os.getenv("MARGEN_CONTRASTE_REQUISITO", "0.08"))
# 1.b Suelo de afinidad compuesta para la alerta. Un umbral fijo sobre la
#    afinidad antigua (coseno reescalado) era insostenible porque su suelo
#    empírico rondaba el 84 %; sobre la afinidad COMPUESTA sí es significativo,
#    porque su cero es un cero real y la cobertura pesa el 75 %. Evita alertar
#    de "talento excepcional" a un candidato que apenas roza el umbral de
#    cobertura en un banco pequeño (caso medido: alerta enviada con 23,44 %).
#    Con cobertura total y sin penalizaciones la afinidad parte de 75 puntos;
#    un valor muy alto (>85) puede silenciar a buenos candidatos que pierden
#    similitud por el idioma del CV (~26 puntos medidos).
UMBRAL_AFINIDAD_ALERTA = float(os.getenv("UMBRAL_AFINIDAD_ALERTA", "70"))
# 2. Percentil dentro del banco de talento para esa vacante. Sitúa al candidato
#    contra la distribución real en lugar de contra una escala comprimida.
PERCENTIL_ALERTA = float(os.getenv("PERCENTIL_ALERTA", "80"))
# Tamaño mínimo del banco para que el percentil sea informativo. Por debajo, la
# decisión recae solo en la cobertura de requisitos.
MIN_MUESTRA_PERCENTIL = int(os.getenv("MIN_MUESTRA_PERCENTIL", "5"))

# --- VERIFICACIÓN DEL PERFIL CONTRA EL DOCUMENTO (anti-inyección / anti-alucinación) ---
# Las habilidades que devuelve el LLM se contrastan con el texto visible del CV
# por un segundo canal (capa de texto del PDF o, si no existe, OCR opcional).
# Un perfil por debajo del umbral, o con patrones de instrucciones dirigidas al
# modelo, se indexa igualmente pero queda marcado y dispara un correo de
# revisión manual al reclutador. Nunca bloquea la postulación.
VERIFICACION_SKILLS_HABILITADA = os.getenv("VERIFICACION_SKILLS_HABILITADA", "True").lower() in ("true", "1", "t")
# Proporción mínima de habilidades extraídas que deben aparecer escritas en el
# documento para no marcar el perfil como sospechoso.
UMBRAL_SKILLS_VERIFICADAS = float(os.getenv("UMBRAL_SKILLS_VERIFICADAS", "0.5"))

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