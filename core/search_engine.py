import json
import chromadb
from chromadb.utils import embedding_functions
from config import settings

class CVSearchEngine:
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

    def search_candidates(self, query_text: str, limit: int = 5, where_filter: dict = None) -> list:
        """Ejecuta búsquedas semánticas híbridas con filtrado exacto por metadatos."""
        try:
            results = self.collection.query(
                query_texts=[query_text],
                n_results=limit,
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
            
            processed_results = []
            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Transformación formal de distancia de coseno a porcentaje de afinidad
                    affinity_percentage = max(0, (1 - distance) * 100)
                    
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
            return processed_results
        except Exception as e:
            raise RuntimeError(f"Error en consulta semántica: {e}")