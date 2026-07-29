"""Capa de datos encargada de la persistencia transaccional y el mapeo relacional de metadatos dentro del motor de vectores."""

from datetime import datetime

from config import settings
from config.settings import clean_collection_name
from core import store_client
from core.data_hygiene import primer_dato_valido
from models.schemas import CandidateStructure, VacancyStructure


class CVVectorStoreManager:
    """Administra operaciones atómicas e idempotentes de escritura, actualización e indexación dentro de ChromaDB."""
    
    def __init__(self, nombre_cargo: str = "talento-global-empresa"):
        # NOTA: Ajusté el valor por defecto para que coincida con la colección global de tu orquestador
        self.client = store_client.crear_cliente()
        self.embedding_function = store_client.crear_funcion_embeddings()
        self.collection_name = clean_collection_name(nombre_cargo)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={"hnsw:space": "cosine", "cargo_original": nombre_cargo}
        )

    def store_vacancy(self, vacancy_data: VacancyStructure, creado_en: int, expira_en: int, texto_original: str = None) -> str:
        """Inserta o actualiza de forma idempotente el nodo raíz descriptor de la oferta laboral."""
        try:
            skills_str = ", ".join(vacancy_data.hard_skills)
            # Este es el texto vectorizado optimizado para el buscador RAG
            document_text = f"Cargo: {vacancy_data.titulo_cargo}\nPerfil: {vacancy_data.perfil_general}\nHabilidades: {skills_str}"
            
            metadata = {
                "tipo_registro": "perfil_vacante",
                "titulo_cargo": str(vacancy_data.titulo_cargo),
                "rango_salarial": str(vacancy_data.rango_salarial),
                "experiencia_anos": int(vacancy_data.experiencia_minima_anos),
                "hard_skills": skills_str,
                "soft_skills": ", ".join(vacancy_data.soft_skills),
                "timestamp_creacion": creado_en,      
                "timestamp_expiracion": expira_en,    
                "texto_original": texto_original if texto_original else "Texto original no disponible",
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

    @staticmethod
    def identificador_candidato(correo: str, nombre: str = "") -> str:
        """Deriva un identificador estable de la identidad del candidato.

        Cada postulación generaba antes un `uuid4()` nuevo, de modo que el
        `upsert` siempre insertaba y nunca actualizaba. Eso producía varios
        registros de la misma persona **dentro de una misma colección**, con tres
        consecuencias medidas: la ventana de recuperación se gastaba en copias
        (un 31 % de la bolsa global), la deduplicación de lectura decidía cuál
        sobrevivía, y como las extracciones de esas copias diferían entre sí, esa
        elección determinaba la afinidad del candidato.

        Con un identificador derivado del correo, volver a postularse actualiza
        el registro en lugar de duplicarlo. La separación por vacante no se
        pierde: cada silo es una colección distinta, así que la misma persona
        conserva un registro por cada vacante a la que se postula, más el suyo en
        la bolsa global.

        Si no hay correo utilizable se recurre al nombre, y en última instancia a
        un identificador aleatorio: es preferible un duplicado a perder una
        postulación bajo una clave compartida.
        """
        import hashlib
        import uuid

        semilla = primer_dato_valido(correo).lower()
        if not semilla:
            semilla = primer_dato_valido(nombre).lower()
        if not semilla:
            return f"CANDIDATO_{uuid.uuid4()}"

        digest = hashlib.sha1(semilla.encode("utf-8")).hexdigest()[:16]
        return f"CANDIDATO_{digest}"

    def store_candidate(self, candidate_data: CandidateStructure, pdf_path: str, formulario: dict,
                        candidate_id: str = None, verificacion: dict = None) -> str:
        """Almacena e indexa el perfil vectorial del candidato con sus metadatos.

        La precedencia es formulario > extracción, pero se resuelve con
        `primer_dato_valido` y no con `or`: un centinela como "0000" es
        *truthy* y con `or` descartaría el dato real extraído del documento.

        Args:
            candidate_data: Perfil estructurado extraído del CV.
            pdf_path: Ruta al PDF almacenado, guardada como metadato.
            formulario: Datos confirmados por el candidato, que tienen
                precedencia sobre los extraídos.
            candidate_id: Identificador a reutilizar; si es ``None`` se deriva
                del correo para que volver a postularse actualice el registro.

        Returns:
            El identificador con el que quedó indexado el candidato.
        """
        try:
            nombre_final_previo = primer_dato_valido(
                formulario.get("nombre"), candidate_data.nombre_completo
            )
            candidate_id = candidate_id or self.identificador_candidato(
                primer_dato_valido(formulario.get("correo"), candidate_data.correo_electronico),
                nombre_final_previo
            )

            nombre_final = primer_dato_valido(
                formulario.get("nombre"), candidate_data.nombre_completo, default="Nombre no disponible"
            )
            correo_final = primer_dato_valido(
                formulario.get("correo"), candidate_data.correo_electronico
            )
            telefono_final = primer_dato_valido(
                formulario.get("telefono"), candidate_data.telefono_movil
            )
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

            # El documento vectorizado contiene solo señal profesional. El nombre
            # queda fuera a propósito: es un canal conocido de señal demográfica
            # —origen y género— y no aporta capacidad de emparejamiento, porque
            # el criterio de la vacante no tiene con qué emparejarlo. Los datos de
            # identidad viven en los metadatos, que es donde la búsqueda por
            # nombre y por correo los lee (`buscar_candidato_por_identidad`).
            document_text = (
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
                "nombre_completo": nombre_final,
                "correo_electronico": correo_final,
                "telefono_movil": telefono_final,
                # Estas tres llaves son CRÍTICAS para que funcione nuestro Prompt Engineering
                "nivel_academico_maximo": str(getattr(candidate_data, 'nivel_academico_maximo', '')),
                "perfil_profesional": str(candidate_data.perfil_profesional),
                "anios_experiencia_total": float(getattr(candidate_data, 'anios_experiencia_total', 0.0)),
                "hard_skills": ", ".join(candidate_data.hard_skills),
                "soft_skills": ", ".join(candidate_data.soft_skills),
                "pdf_file_path": str(pdf_path),
                "origen": str(formulario.get("origen", "No especificado")),
                "fecha_actualizacion": datetime.now().isoformat(timespec="seconds"),
                "raw_json": candidate_data.model_dump_json()
            }

            # Veredicto de la verificación contra el documento. Se aplana a
            # escalares porque ChromaDB no admite metadatos anidados. La marca
            # `sospechoso` permite al dashboard filtrar o señalar el perfil.
            if verificacion:
                metadata["verificacion_canal"] = str(verificacion.get("canal", ""))
                metadata["verificacion_sospechoso"] = bool(verificacion.get("sospechoso", False))
                if verificacion.get("ratio") is not None:
                    metadata["verificacion_ratio"] = float(verificacion["ratio"])
                no_verificadas = verificacion.get("no_verificadas") or []
                if no_verificadas:
                    metadata["verificacion_no_verificadas"] = ", ".join(no_verificadas)


            self.collection.upsert(
                documents=[document_text],
                metadatas=[metadata],
                ids=[candidate_id]
            )
            return candidate_id
        except Exception as e:
            raise RuntimeError(f"Fallo en operación transaccional UPSERT de candidato en base vectorial: {e}")