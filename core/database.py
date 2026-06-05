import json
import chromadb
from chromadb.utils import embedding_functions
from config import settings
from config.settings import clean_collection_name
from models.schemas import VacancyStructure

class CVVectorStoreManager:
    def __init__(self, nombre_cargo: str):
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
            model_name=settings.EMBEDDING_MODEL
        )
        self.collection_name = clean_collection_name(nombre_cargo)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine", "cargo_original": nombre_cargo}
        )

    def store_vacancy(self, vacancy_data: VacancyStructure, creado_en: int, expira_en: int) -> str:
        """Persiste la descripción estructurada de la vacante en su nodo ancla."""
        try:
            document_text = f"Cargo: {vacancy_data.titulo_cargo}\nPerfil: {vacancy_data.perfil_general}"
            metadata = {
                "tipo_registro": "perfil_vacante",
                "titulo_cargo": vacancy_data.titulo_cargo,
                "rango_salarial": vacancy_data.rango_salarial,
                "experiencia_anos": vacancy_data.experiencia_minima_anos,
                "hard_skills": ", ".join(vacancy_data.hard_skills),
                "soft_skills": ", ".join(vacancy_data.soft_skills),
                "fecha_creacion_int": creado_en,
                "fecha_expiracion_int": expira_en,
                "raw_json": vacancy_data.model_dump_json()
            }
            self.collection.upsert(
                documents=[document_text],
                metadatas=[metadata],
                ids=["VACANTE_PRINCIPAL"]
            )
            return self.collection_name
        except Exception as e:
            raise RuntimeError(f"Error al guardar vacante en ChromaDB: {e}")

    def store_candidate(self, candidate_json: dict, pdf_path: str, formulario: dict) -> str:
        """Almacena un candidato indexando metadatos declarativos y la ruta al PDF físico."""
        import uuid
        try:
            candidate_id = f"CANDIDATO_{uuid.uuid4()}"
            
            # Consolidación del documento semántico
            document_text = f"Nombre: {formulario.get('nombre')}\nPerfil: {formulario.get('perfil')}"
            
            metadata = {
                "tipo_registro": "candidato",
                "nombre_completo": formulario.get("nombre"),
                "correo_electronico": formulario.get("correo"),
                "telefono_movil": formulario.get("telefono"),
                "hard_skills": candidate_json.get("hard_skills_str", ""),
                "soft_skills": candidate_json.get("soft_skills_str", ""),
                "pdf_file_path": pdf_path,  # Estrategia de almacenamiento desacoplado
                "raw_json": json.dumps(candidate_json, ensure_ascii=False)
            }
            
            self.collection.upsert(
                documents=[document_text],
                metadatas=[metadata],
                ids=[candidate_id]
            )
            return candidate_id
        except Exception as e:
            raise RuntimeError(f"Error al persistir candidato en ChromaDB: {e}")