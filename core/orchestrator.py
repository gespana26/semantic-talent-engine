import os
import shutil
from datetime import datetime, timedelta
import chromadb
from core.extractor import CVImageExtractor
from core.database import CVVectorStoreManager
from config import settings

class VacancyOrchestrator:
    """Orquestador a cargo del ciclo de vida y vigencia de las vacantes."""
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider
        self.extractor = CVImageExtractor()
        self.chroma_client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

    def process_and_register_vacancy(self, raw_text: str = None, pdf_path: str = None) -> dict:
        image_paths = []
        try:
            if pdf_path:
                image_paths = self.extractor.pdf_to_images(pdf_path)
                vacancy_json = self.ai_provider.parse_vacancy(image_paths=image_paths)
            else:
                vacancy_json = self.ai_provider.parse_vacancy(raw_text=raw_text)

            # --- CÁLCULO DETERMINISTA DE FECHAS (Query-Time TTL) ---
            fecha_actual = datetime.now()
            fecha_expiracion = fecha_actual + timedelta(days=vacancy_json.dias_vigencia)
            
            timestamp_creacion = int(fecha_actual.strftime("%Y%m%d"))
            timestamp_expiracion = int(fecha_expiracion.strftime("%Y%m%d"))

            # --- CONCILIACIÓN SEMÁNTICA DE ENTIDADES ---
            colecciones_reales = [col.name for col in self.chroma_client.list_collections()]
            decision = self.ai_provider.reconcile_vacancy_name(vacancy_json.titulo_cargo, colecciones_reales)
            
            es_edicion = decision != "NUEVA" and decision in colecciones_reales
            nombre_tabla = decision if es_edicion else settings.clean_collection_name(vacancy_json.titulo_cargo)

            # --- PERSISTENCIA ---
            db_manager = CVVectorStoreManager(nombre_cargo=vacancy_json.titulo_cargo)
            db_manager.collection_name = nombre_tabla
            db_manager.collection = db_manager.client.get_or_create_collection(name=nombre_tabla)
            
            db_manager.store_vacancy(vacancy_json, timestamp_creacion, timestamp_expiracion)
            
            return {"status": "success", "operacion": "edicion" if es_edicion else "creacion", "coleccion": nombre_tabla}
        finally:
            if image_paths:
                self.extractor.clear_temp_images(image_paths)


class CandidateOrchestrator:
    """Orquestador a cargo de la ingesta del candidato y Doble Indexación."""
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider
        self.extractor = CVImageExtractor()

    def process_and_register_candidate(self, pdf_path: str, cargo_objetivo: str, datos_formulario: dict) -> dict:
        image_paths = []
        try:
            # 1. Copiar el archivo original al almacenamiento desacoplado de larga duración
            os.makedirs(settings.LOCAL_STORAGE_CV_PATH, exist_ok=True)
            nombre_archivo_final = f"CV_{datos_formulario.get('telefono')}_{os.path.basename(pdf_path)}"
            ruta_persistente_pdf = os.path.join(settings.LOCAL_STORAGE_CV_PATH, nombre_archivo_final)
            shutil.copy(pdf_path, ruta_persistente_pdf)

            # 2. Pipeline cognitivo de extracción
            image_paths = self.extractor.pdf_to_images(ruta_persistente_pdf)
            candidate_json = self.ai_provider.parse_cv_images_to_json(image_paths)

            # --- ESTRATEGIA DE DOBLE INDEXACIÓN (Dual-Indexing) ---
            # A. Guardar en el silo cerrado de la vacante específica actual
            db_vacante = CVVectorStoreManager(nombre_cargo=cargo_objetivo)
            id_en_vacante = db_vacante.store_candidate(candidate_json, ruta_persistente_pdf, datos_formulario)

            # B. Guardar en la bolsa de empleo histórica global de la empresa
            db_global = CVVectorStoreManager(nombre_cargo="talento-global-empresa")
            id_en_global = db_global.store_candidate(candidate_json, ruta_persistente_pdf, datos_formulario)

            return {
                "status": "success",
                "id_vacante_silo": id_en_vacante,
                "id_bolsa_global": id_en_global,
                "ruta_pdf_fisico": ruta_persistente_pdf
            }
        finally:
            if image_paths:
                self.extractor.clear_temp_images(image_paths)