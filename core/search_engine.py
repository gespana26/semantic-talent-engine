"""Módulo encargado de la recuperación semántica de información, filtrado estructural de metadatos y cálculo de índices de afinidad."""

import json
import chromadb
from chromadb.utils import embedding_functions
from config import settings

class CVSearchEngine:
    """Ejecuta consultas de similitud de alta velocidad en espacios vectoriales aplicando Post-Retrieval Filtering en Python."""
    
    def __init__(self, collection_name: str = "talento-global-empresa"):
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
            model_name=settings.EMBEDDING_MODEL
        )
        self.collection = self.client.get_collection(
            name=collection_name, 
            embedding_function=self.embedding_function
        )

    def _evaluar_filtro_python(self, metadata: dict, filtro_nli: dict) -> bool:
        """Motor de evaluación léxica interno. Refactorizado para búsqueda 'Omnidireccional' (Forgiving Filter)."""
        if not filtro_nli: 
            return True 
        
        # 🌟 EL SECRETO: Aplanamos toda la data del candidato en un solo bloque de texto.
        # Si la IA se equivoca de campo (ej. busca en 'perfil' pero la palabra está en 'estudios'), el sistema lo salva.
        texto_global_candidato = str(metadata.get("raw_json", "")).lower() + str(metadata).lower()

        # Caso 1: Arreglo bilingüe ($or)
        if "$or" in filtro_nli:
            for condicion in filtro_nli["$or"]:
                for campo, operacion in condicion.items():
                    if isinstance(operacion, dict) and "$contains" in operacion:
                        valor_buscado = operacion["$contains"].lower()
                        # Si el término existe en CUALQUIER parte de su CV, pasa el filtro
                        if valor_buscado in texto_global_candidato:
                            return True
            return False 
            
        # Caso 2: Filtro obligatorio simple
        for campo, operacion in filtro_nli.items():
            if isinstance(operacion, dict) and "$contains" in operacion:
                valor_buscado = operacion["$contains"].lower()
                if valor_buscado not in texto_global_candidato:
                    return False
                    
        return True
    
    def buscar_candidato_por_identidad(self, termino_busqueda: str) -> list:
        """Bypass del motor vectorial: Recupera un candidato directamente por nombre o correo."""
        resultados = self.collection.get(include=["metadatas"])
        candidatos_encontrados = []
        termino = termino_busqueda.lower()
        
        if resultados and resultados['metadatas']:
            for meta in resultados['metadatas']:
                nombre = str(meta.get("nombre_completo", "")).lower()
                correo = str(meta.get("correo_electronico", "")).lower()
                
                if termino in nombre or termino in correo:
                    candidatos_encontrados.append(meta)
                    
        return candidatos_encontrados
    
    def search_candidates(self, query_text: str, limit: int = 5, where_filter: dict = None) -> list:
        """Interroga la colección vectorial activa aplicando restricciones léxicas y deduplicación."""
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=50, 
                include=["documents", "metadatas", "distances"]
            )
            
            processed_results = []
            correos_vistos = set()
            UMBRAL_MAXIMO_DISTANCIA = 1.2 
            
            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # 1. Ignorar la Vacante (Registros Fantasma)
                    if not metadata.get("nombre_completo"):
                        continue
                        
                    # 2. Primera Guillotina (IA): Filtramos por alucinación semántica
                    if distance > UMBRAL_MAXIMO_DISTANCIA:
                        continue
                        
                    # 3. Segunda Guillotina (Python): Evaluamos las reglas duras (Obligatorio/Excluyente)
                    if not self._evaluar_filtro_python(metadata, where_filter):
                        continue
                        
                    # 4. Blindaje: Deduplicación por Identidad
                    correo_actual = metadata.get("correo_electronico", "").lower().strip()
                    if correo_actual in correos_vistos:
                        continue 
                    correos_vistos.add(correo_actual)
                    
                    # 5. Normalización Matemática y Empaquetado
                    affinity_percentage = max(0, (1 - (distance / 2.0)) * 100)
                    raw_json_str = metadata.get("raw_json")
                    candidate_data = json.loads(raw_json_str) if raw_json_str else {}
                    
                    processed_results.append({
                        "id_registro": results['ids'][0][i],
                        "nombre": metadata.get("nombre_completo"),
                        "correo": metadata.get("correo_electronico"),
                        "porcentaje_afinidad": round(affinity_percentage, 2),
                        "pdf_origen": metadata.get("pdf_file_path"),
                        "perfil_completo_json": candidate_data
                    })
                    
                    if len(processed_results) == limit:
                        break

            return processed_results
        except Exception as e:
            raise RuntimeError(f"Fallo en la arquitectura de recuperación y filtrado RAG: {e}")
        
    def obtener_perfil_vacante(self) -> str:
        """Extrae el perfil general de la vacante almacenada en el silo para usarlo como criterio de Auto-Match."""
        try:
            resultados = self.collection.get(include=["metadatas", "documents"])
            if resultados and resultados.get('metadatas'):
                for i, meta in enumerate(resultados['metadatas']):
                    if not meta.get("nombre_completo"):
                        # Intentamos sacar el texto original primero
                        texto_original = meta.get("texto_original")
                        if texto_original and texto_original != "Texto original no disponible":
                            return texto_original
                            
                        # Retrocompatibilidad
                        raw_json = meta.get("raw_json")
                        if raw_json:
                            datos_vacante = json.loads(raw_json)
                            perfil = datos_vacante.get("perfil_general", "")
                            habilidades = " ".join(datos_vacante.get("hard_skills", []))
                            return f"{perfil} {habilidades}".strip()
            return ""
        except Exception:
            return ""