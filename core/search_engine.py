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
        """Motor de evaluación léxica interno que reemplaza las limitaciones nativas del 'where' de ChromaDB."""
        if not filtro_nli: 
            return True # Si no hay filtro obligatorio, todos pasan
        
        # Caso 1: Arreglo bilingüe ($or)
        if "$or" in filtro_nli:
            for condicion in filtro_nli["$or"]:
                for campo, operacion in condicion.items():
                    if "$contains" in operacion:
                        valor_buscado = operacion["$contains"].lower()
                        valor_real = str(metadata.get(campo, "")).lower()
                        if valor_buscado in valor_real:
                            return True # Con uno que haga match exacto o parcial, aprueba
            return False # Si ninguno del $or cumplió, se descarta
            
        # Caso 2: Filtro obligatorio simple
        for campo, operacion in filtro_nli.items():
            if "$contains" in operacion:
                valor_buscado = operacion["$contains"].lower()
                valor_real = str(metadata.get(campo, "")).lower()
                if valor_buscado not in valor_real:
                    return False
        return True

    def search_candidates(self, query_text: str, limit: int = 5, where_filter: dict = None) -> list:
        """Interroga la colección vectorial activa aplicando restricciones léxicas vía Python post-extracción."""
        try:
            # 1. Ampliamos la red de captura: Extraemos 50 candidatos usando SOLO IA Vectorial pura
            results = self.collection.query(
                query_texts=[query_text],
                n_results=50, 
                include=["documents", "metadatas", "distances"]
            )
            
            processed_results = []
            UMBRAL_MAXIMO_DISTANCIA = 1.2 
            
            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # 2. Primer filtro (IA): Filtramos por alucinación semántica
                    if distance > UMBRAL_MAXIMO_DISTANCIA:
                        continue
                        
                    # 3. Segund filtro (Python): Evaluamos las reglas duras (Obligatorio/Excluyente)
                    if not self._evaluar_filtro_python(metadata, where_filter):
                        continue
                    
                    # 4. Normalización Matemática y Empaquetado
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
                    
                    # 5. Si ya llenamos el cupo solicitado por el usuario, detenemos el procesamiento
                    if len(processed_results) == limit:
                        break

            return processed_results
        except Exception as e:
            raise RuntimeError(f"Fallo en la arquitectura de recuperación y filtrado RAG: {e}")