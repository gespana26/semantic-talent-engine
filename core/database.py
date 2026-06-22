"""Capa de datos encargada de la persistencia transaccional y el mapeo relacional de metadatos dentro del motor de vectores."""

import chromadb
from chromadb.utils import embedding_functions
from config import settings
from config.settings import clean_collection_name
from models.schemas import VacancyStructure, CandidateStructure

class CVVectorStoreManager:
    """Administra operaciones atómicas e idempotentes de escritura, actualización e indexación dentro de ChromaDB."""
    
    def __init__(self, nombre_cargo: str = "talento-global-empresa"):
        # NOTA: Ajusté el valor por defecto para que coincida con la colección global de tu orquestador
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
        """Inserta o actualiza de forma idempotente el nodo raíz descriptor de la oferta laboral."""
        try:
            skills_str = ", ".join(vacancy_data.hard_skills)
            document_text = f"Cargo: {vacancy_data.titulo_cargo}\nPerfil: {vacancy_data.perfil_general}\nHabilidades: {skills_str}"
            
            metadata = {
                "tipo_registro": "perfil_vacante",
                "titulo_cargo": str(vacancy_data.titulo_cargo),
                "rango_salarial": str(vacancy_data.rango_salarial),
                "experiencia_anos": int(vacancy_data.experiencia_minima_anos),
                "hard_skills": skills_str,
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
            raise RuntimeError(f"Fallo en operación transaccional UPSERT de vacante en base vectorial: {e}")

    def store_candidate(self, candidate_data: CandidateStructure, pdf_path: str, formulario: dict) -> str:
        """Almacena e indexa el perfil vectorial del candidato asociando metadatos estructurados y su ruta lógica de archivo."""
        import uuid
        try:
            candidate_id = f"CANDIDATO_{uuid.uuid4()}"
            # Convertimos el historial laboral en texto plano para que el modelo lo "lea"
            # 1. ENRIQUECIMIENTO DEL VECTOR (Aprovechando la memoria de Nomic de forma segura)
            historial_str = ""
            if hasattr(candidate_data, 'historial_laboral') and candidate_data.historial_laboral:
                for exp in candidate_data.historial_laboral:
                    cargo = getattr(exp, 'cargo', 'Cargo no especificado')
                    empresa = getattr(exp, 'empresa', 'Empresa no especificada')
                    responsabilidades = getattr(exp, 'responsabilidades', '')
                    
                    # --- CAMBIO CRÍTICO: Usamos el nombre real de tu esquema ---
                    duracion = getattr(exp, 'duracion_anios', '')
                    duracion_txt = f" ({duracion} años)" if duracion else ""
                    
                    historial_str += f"- {cargo} en {empresa}{duracion_txt}: {responsabilidades}\n"

            document_text = (
                f"Candidato: {formulario.get('nombre') or candidate_data.nombre_completo}\n"
                f"Nivel Académico: {getattr(candidate_data, 'nivel_academico_maximo', 'N/A')}\n"
                f"Años de Experiencia Total: {getattr(candidate_data, 'anios_experiencia_total', 0)}\n"
                f"Perfil Profesional: {candidate_data.perfil_profesional}\n"
                f"Habilidades Técnicas: {', '.join(candidate_data.hard_skills)}\n"
                f"Competencias Blandas: {', '.join(candidate_data.soft_skills)}\n"
                f"Historial Laboral:\n{historial_str}"
            )
            
            # 2. ENRIQUECIMIENTO DE METADATOS (Asegurando que ChromaDB pueda filtrar)
            metadata = {
                "tipo_registro": "candidato",
                "nombre_completo": str(formulario.get("nombre") or candidate_data.nombre_completo),
                "correo_electronico": str(formulario.get("correo") or candidate_data.correo_electronico),
                "telefono_movil": str(formulario.get("telefono") or candidate_data.telefono_movil),
                # Estas tres llaves son CRÍTICAS para que funcione nuestro Prompt Engineering
                "nivel_academico_maximo": str(getattr(candidate_data, 'nivel_academico_maximo', '')),
                "perfil_profesional": str(candidate_data.perfil_profesional),
                "anios_experiencia_total": float(getattr(candidate_data, 'anios_experiencia_total', 0.0)),
                "hard_skills": ", ".join(candidate_data.hard_skills),
                "soft_skills": ", ".join(candidate_data.soft_skills),
                "pdf_file_path": str(pdf_path),
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