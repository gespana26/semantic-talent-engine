"""Capa central de orquestación encargada de ejecutar las reglas de flujo de negocio, pipelines de ingesta y sincronización de estado."""

import os
import shutil
import uuid  # Utiliza la biblioteca nativa estándar de Python
from datetime import datetime, timedelta
import chromadb
from core.extractor import CVImageExtractor
from core.database import CVVectorStoreManager
from config import settings

class VacancyOrchestrator:
    """Administra el flujo secuencial para la ingesta, control de umbrales temporales y conciliación semántica de vacantes."""
    
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider
        self.extractor = CVImageExtractor()
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

    def process_and_register_vacancy(self, raw_text: str = None, pdf_path: str = None) -> dict:
        """Ejecuta la orquestación completa del ciclo de vida para ingerir, resolver colisiones de nombres y persistir ofertas de empleo."""
        image_paths = []
        try:
            if pdf_path:
                image_paths = self.extractor.pdf_to_images(pdf_path)
                vacancy_json = self.ai_provider.parse_vacancy(image_paths=image_paths)
            else:
                vacancy_json = self.ai_provider.parse_vacancy(raw_text=raw_text)

            # --- GENERACIÓN ARITMÉTICA DE MARCAS DE TIEMPO (Query-Time TTL) ---
            fecha_actual = datetime.now()
            
            # 📌 REGLA DE NEGOCIO: 30 DÍAS POR DEFECTO
            # Extraemos los días de forma defensiva. Si es 0 o None, aplicamos 30.
            dias_vigencia = getattr(vacancy_json, 'dias_vigencia', 0)
            if not dias_vigencia or dias_vigencia <= 0:
                dias_vigencia = 30
                
            fecha_expiracion = fecha_actual + timedelta(days=dias_vigencia)
            
            timestamp_creacion = int(fecha_actual.strftime("%Y%m%d"))
            timestamp_expiracion = int(fecha_expiracion.strftime("%Y%m%d"))

            # --- CONCILIACIÓN SEMÁNTICA DE IDENTIDADES (Idempotencia) ---
            colecciones_reales = [col.name for col in self.chroma_client.list_collections()]
            decision = self.ai_provider.reconcile_vacancy_name(vacancy_json.titulo_cargo, colecciones_reales)
            
            es_edicion = decision != "NUEVA" and decision in colecciones_reales
            nombre_tabla = decision if es_edicion else settings.clean_collection_name(vacancy_json.titulo_cargo)

            # --- EVALUACIÓN DE ESTADO DE INFRAESTRUCTURA Y ESCRITURA EN BASE DE DATOS ---
            db_manager = CVVectorStoreManager(nombre_cargo=vacancy_json.titulo_cargo)
            db_manager.collection_name = nombre_tabla
            db_manager.collection = db_manager.client.get_or_create_collection(name=nombre_tabla)
            
            # 📌 PASAMOS EL TEXTO ORIGINAL COMO EQUIPAJE OCULTO
            db_manager.store_vacancy(
                vacancy_json, 
                timestamp_creacion, 
                timestamp_expiracion,
                texto_original=raw_text 
            )
            
            # --- el orquestador devuelve el estado Y los datos extraídos ---
            return {
                "status": "success", 
                "operacion": "edicion" if es_edicion else "creacion", 
                "coleccion": nombre_tabla,
                "datos_extraidos": vacancy_json.model_dump() # Entrega el JSON limpio a la consola
            }
        finally:
            if image_paths:
                self.extractor.clear_temp_images(image_paths)


class CandidateOrchestrator:
    """Administra la ejecución de flujos de postulación, ruteo desacoplado de archivos y sincronización multi-índice."""
    
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider
        self.extractor = CVImageExtractor()

    def extract_candidate(self, pdf_path: str) -> dict:
        """Extrae el perfil sin persistirlo, para que el candidato pueda confirmarlo antes de indexarse.

        Separar la extracción del registro es lo que habilita el paso de
        confirmación del portal web: una clave de identidad (el correo) no
        puede depender de una extracción probabilística sin revisión humana.
        El nombre del archivo se deriva de un identificador único, nunca de un
        dato de contacto, para evitar colisiones al copiar al storage.
        """
        image_paths = []
        try:
            os.makedirs(settings.LOCAL_STORAGE_CV_PATH, exist_ok=True)

            # El identificador de fichero es independiente de los datos extraídos:
            # dos candidatos que suban "CV.pdf" no pueden sobrescribirse entre sí.
            nombre_base = os.path.basename(pdf_path).replace(" ", "_")
            nombre_archivo_final = f"CV_{uuid.uuid4().hex[:12]}_{nombre_base}"
            ruta_persistente_pdf = os.path.join(settings.LOCAL_STORAGE_CV_PATH, nombre_archivo_final)
            shutil.copy(pdf_path, ruta_persistente_pdf)

            image_paths = self.extractor.pdf_to_images(ruta_persistente_pdf)
            candidate_data_pydantic = self.ai_provider.parse_cv_images_to_json(image_paths)

            return {
                "status": "success",
                "candidate_data": candidate_data_pydantic,
                "ruta_pdf_fisico": ruta_persistente_pdf,
                "datos_extraidos": candidate_data_pydantic.model_dump()
            }
        finally:
            if image_paths:
                self.extractor.clear_temp_images(image_paths)

    def register_candidate(self, candidate_data, ruta_persistente_pdf: str, cargo_objetivo: str = "", datos_formulario: dict = None) -> dict:
        """Indexa un perfil ya extraído (y confirmado) mediante la arquitectura de Doble Índice."""
        if datos_formulario is None:
            datos_formulario = {}

        # --- ARQUITECTURA CONCURRENTE DE DOBLE INDEXACIÓN (Dual-Indexing) ---
        id_en_vacante = None

        # Índice Destino A: Pipeline cerrado (Solo si el candidato especificó un cargo)
        cargo_limpio = cargo_objetivo.strip() if cargo_objetivo else ""
        if cargo_limpio and cargo_limpio.lower() != "talento-global-empresa":
            db_vacante = CVVectorStoreManager(nombre_cargo=cargo_limpio)
            id_en_vacante = db_vacante.store_candidate(candidate_data, ruta_persistente_pdf, datos_formulario)

        # Índice Destino B: Repositorio consolidado histórico global corporativo
        db_global = CVVectorStoreManager(nombre_cargo="talento-global-empresa")
        id_en_global = db_global.store_candidate(candidate_data, ruta_persistente_pdf, datos_formulario)

        return {
            "status": "success",
            "id_vacante_silo": id_en_vacante,
            "id_bolsa_global": id_en_global,
            "ruta_pdf_fisico": ruta_persistente_pdf,
            "datos_extraidos": candidate_data.model_dump()
        }

    def process_and_register_candidate(self, pdf_path: str, cargo_objetivo: str = "", datos_formulario: dict = None) -> dict:
        """Ejecuta la ruta de ingesta completa en un solo paso.

        Es la ruta de la CLI, donde el operador ya captura y valida los datos de
        identidad antes de invocar el pipeline, de modo que no necesita un paso
        de confirmación posterior.
        """
        extraccion = self.extract_candidate(pdf_path)
        return self.register_candidate(
            candidate_data=extraccion["candidate_data"],
            ruta_persistente_pdf=extraccion["ruta_pdf_fisico"],
            cargo_objetivo=cargo_objetivo,
            datos_formulario=datos_formulario
        )