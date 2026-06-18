"""Capa de datos encargada de la persistencia transaccional y el mapeo relacional de metadatos dentro del motor de vectores."""

import chromadb
from chromadb.utils import embedding_functions
from config import settings
from config.settings import clean_collection_name
from models.schemas import VacancyStructure, CandidateStructure

class CVVectorStoreManager:
    """Administra operaciones atómicas e idempotentes de escritura, actualización e indexación dentro de ChromaDB."""
    
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
        """Inserta o actualiza de forma idempotente el nodo raíz descriptor de la oferta laboral.

        Args:
            vacancy_data (VacancyStructure): Entidad estructurada con atributos de la vacante.
            creado_en (int): Marca de tiempo numérica de creación (Formato YYYYMMDD).
            expira_en (int): Marca de tiempo numérica de expiración (Formato YYYYMMDD).
        """
        try:
            # Forzamos la interpolación limpia convirtiendo listas a strings de forma explícita
            skills_str = ", ".join(vacancy_data.hard_skills)
            document_text = f"Cargo: {vacancy_data.titulo_cargo}\nPerfil: {vacancy_data.perfil_general}\nHabilidades: {skills_str}"
            
            # Nos aseguramos de que el payload de metadatos no sufra codificación ASCII oculta
            metadata = {
                "tipo_registro": "perfil_vacante",
                "titulo_cargo": str(vacancy_data.titulo_cargo),
                "rango_salarial": str(vacancy_data.rango_salarial),
                "experiencia_anos": int(vacancy_data.experiencia_minima_anos),
                "hard_skills": skills_str,
                "soft_skills": ", ".join(vacancy_data.soft_skills),
                "fecha_creacion_int": creado_en,
                "fecha_expiracion_int": expira_en,
                "raw_json": vacancy_data.model_dump_json() # Pydantic v2 ya genera UTF-8 nativo aquí
            }
            self.collection.upsert(
                documents=[document_text],
                metadatas=[metadata],
                ids=["VACANTE_PRINCIPAL"]
            )
            return self.collection_name
        except Exception as e:
            raise RuntimeError(f"Fallo en operación transaccional UPSERT de vacante en base vectorial: {e}")

    def store_candidate(self, candidate_data: CandidateStructure, pdf_path: str, formulario: dict) -> str:
        """Almacena e indexa el perfil vectorial del candidato asociando metadatos estructurados y su ruta lógica de archivo."""
        import uuid
        try:
            candidate_id = f"CANDIDATO_{uuid.uuid4()}"
            document_text = (
                f"Candidato: {formulario.get('nombre') or candidate_data.nombre_completo}\n"
                f"Perfil Profesional: {candidate_data.perfil_profesional}\n"
                f"Habilidades Técnicas: {', '.join(candidate_data.hard_skills)}\n"
                f"Competencias Blandas: {', '.join(candidate_data.soft_skills)}"
            )
            metadata = {
                "tipo_registro": "candidato",
                "nombre_completo": formulario.get("nombre") or candidate_data.nombre_completo,
                "correo_electronico": formulario.get("correo") or candidate_data.correo_electronico,
                "telefono_movil": formulario.get("telefono") or candidate_data.telefono_movil,
                "hard_skills": ", ".join(candidate_data.hard_skills),
                "soft_skills": ", ".join(candidate_data.soft_skills),
                "pdf_file_path": pdf_path,
                "raw_json": candidate_data.model_dump_json()
            }
            self.collection.upsert(
                documents=[document_text],
                metadatas=[metadata],
                ids=[candidate_id]
            )
            return candidate_id
        except Exception as e:
            raise RuntimeError(f"Fallo en operación transaccional UPSERT de candidato en base vectorial: {e}")