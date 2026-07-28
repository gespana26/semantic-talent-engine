"""Capa central de orquestación encargada de ejecutar las reglas de flujo de negocio, pipelines de ingesta y sincronización de estado."""

import os
import shutil
import tempfile
import threading
import uuid  # Utiliza la biblioteca nativa estándar de Python
from datetime import datetime, timedelta

from config import settings
from core import skill_verification, store_client
from core.database import CVVectorStoreManager
from core.email_service import enviar_alerta_revision_cv
from core.extractor import CVImageExtractor

# Prefijo del directorio donde vive la copia de trabajo de una postulación que
# todavía no se ha confirmado. Es lo que permite distinguir un PDF pendiente de
# uno ya persistido sin llevar estado en ningún sitio: la ruta lo dice.
PREFIJO_PENDIENTE = "cv_pendiente_"


def _es_pendiente(ruta_pdf: str) -> bool:
    """Indica si la ruta apunta al área temporal de postulaciones sin confirmar."""
    if not ruta_pdf:
        return False
    return os.path.basename(os.path.dirname(ruta_pdf)).startswith(PREFIJO_PENDIENTE)


def persistir_pdf(ruta_pdf: str) -> str:
    """Traslada al almacén definitivo el PDF de una postulación confirmada.

    Devuelve la ruta final, que es la que se indexa como `pdf_file_path`. **Es
    idempotente**: si la ruta ya apunta al almacén —caso de una llamada repetida,
    o del flujo de la CLI si algún día persistiera antes— se devuelve sin tocar
    nada. La decisión de si hay que mover se lee de la propia ruta, sin estado
    auxiliar que pueda desincronizarse.
    """
    if not ruta_pdf or not _es_pendiente(ruta_pdf) or not os.path.exists(ruta_pdf):
        return ruta_pdf

    os.makedirs(settings.LOCAL_STORAGE_CV_PATH, exist_ok=True)
    destino = os.path.join(settings.LOCAL_STORAGE_CV_PATH, os.path.basename(ruta_pdf))
    carpeta_origen = os.path.dirname(ruta_pdf)

    shutil.move(ruta_pdf, destino)
    shutil.rmtree(carpeta_origen, ignore_errors=True)
    return destino


def descartar_extraccion(ruta_pdf: str) -> None:
    """Elimina la copia de trabajo de una postulación que no llegó a confirmarse.

    La llama el portal al reiniciar el borrador. No propaga errores: descartar un
    temporal nunca puede impedirle a alguien empezar una postulación nueva.
    """
    if _es_pendiente(ruta_pdf):
        shutil.rmtree(os.path.dirname(ruta_pdf), ignore_errors=True)


class VacancyOrchestrator:
    """Administra el flujo secuencial para la ingesta, control de umbrales temporales y conciliación semántica de vacantes."""
    
    def __init__(self, ai_provider):
        self.ai_provider = ai_provider
        self.extractor = CVImageExtractor()
        self.chroma_client = store_client.crear_cliente()

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

            # --- ESCRITURA EN BASE DE DATOS ---
            # El manager se construye DESPUÉS de resolver el destino y es el único
            # que crea u obtiene la colección: siempre con la función de embeddings
            # del proyecto (nomic-embed-text) y distancia coseno. La versión
            # anterior reasignaba `db_manager.collection` con un
            # get_or_create_collection sin embedding_function, y ese objeto queda
            # ligado a la EF por defecto de ChromaDB (MiniLM, 384 dims): la vacante
            # podía vectorizarse en un espacio distinto al de sus candidatos. Con
            # chromadb 1.x el daño no se materializó (la colección existente
            # conserva su EF), pero con el pin histórico 0.6.x la vacante fijaba la
            # colección a 384 dims y cada postulación al silo fallaba después por
            # conflicto de dimensión. La regresión se cubre en
            # tests/unit/test_vacancy_embedding_coherence.py.
            db_manager = CVVectorStoreManager(
                nombre_cargo=decision if es_edicion else vacancy_json.titulo_cargo
            )
            nombre_tabla = db_manager.collection_name


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
            # El identificador de fichero es independiente de los datos extraídos:
            # dos candidatos que suban "CV.pdf" no pueden sobrescribirse entre sí.
            nombre_base = os.path.basename(pdf_path).replace(" ", "_")
            nombre_archivo_final = f"CV_{uuid.uuid4().hex[:12]}_{nombre_base}"

            # La copia de trabajo vive en un directorio temporal propio, NO en
            # `storage/cv_files/`. Antes se escribía directamente en el almacén
            # definitivo, antes de que el candidato confirmase: si abandonaba la
            # fase 2 del portal —cerraba la pestaña, cambiaba de idea, se le caía
            # la conexión— el PDF quedaba en disco sin ningún registro que lo
            # referenciase, y nada lo recogía nunca. El directorio crecía sin
            # techo y, lo que más pesa, retenía currículums con datos personales
            # de gente que decidió **no** postularse.
            #
            # El fichero solo llega al almacén en `persistir_pdf`, ya con el
            # consentimiento dado. Y si la postulación se abandona sin pasar por
            # ningún sitio, lo que queda es un temporal del sistema operativo, no
            # un residuo permanente de la aplicación.
            carpeta_pendiente = tempfile.mkdtemp(prefix=PREFIJO_PENDIENTE)
            ruta_persistente_pdf = os.path.join(carpeta_pendiente, nombre_archivo_final)
            shutil.copy(pdf_path, ruta_persistente_pdf)

            image_paths = self.extractor.pdf_to_images(ruta_persistente_pdf)

            # --- SEGUNDO CANAL DE TEXTO, EN PARALELO CON LA LLAMADA AL LLM ---
            # La cascada texto-PDF → OCR consume las mismas imágenes que ya se
            # generaron y siempre termina antes que el modelo multimodal, de
            # modo que la verificación no añade latencia percibida.
            canal_texto = {"texto": "", "canal": skill_verification.CANAL_NO_DISPONIBLE}
            hilo_texto = None
            if settings.VERIFICACION_SKILLS_HABILITADA:
                def _extraer_texto():
                    try:
                        texto, canal = skill_verification.extraer_texto_documento(
                            ruta_persistente_pdf, image_paths
                        )
                        canal_texto.update({"texto": texto, "canal": canal})
                    except Exception:
                        pass  # La verificación degrada; nunca tumba la postulación.
                hilo_texto = threading.Thread(target=_extraer_texto, daemon=True)
                hilo_texto.start()

            candidate_data_pydantic = self.ai_provider.parse_cv_images_to_json(image_paths)

            # El veredicto se calcula tras el join: comparar habilidades contra
            # texto ya extraído cuesta microsegundos.
            verificacion = None
            if hilo_texto is not None:
                hilo_texto.join(timeout=120)
                verificacion = skill_verification.evaluar_verificacion(
                    list(candidate_data_pydantic.hard_skills or []),
                    canal_texto["texto"],
                    canal_texto["canal"],
                )

            return {
                "status": "success",
                "candidate_data": candidate_data_pydantic,
                "ruta_pdf_fisico": ruta_persistente_pdf,
                "datos_extraidos": candidate_data_pydantic.model_dump(),
                "verificacion": verificacion
            }
        finally:
            if image_paths:
                self.extractor.clear_temp_images(image_paths)

    def register_candidate(self, candidate_data, ruta_persistente_pdf: str, cargo_objetivo: str = "",
                           datos_formulario: dict = None, verificacion: dict = None) -> dict:
        """Indexa un perfil ya extraído (y confirmado) mediante la arquitectura de Doble Índice.

        El veredicto de verificación se persiste junto al perfil y, si marca
        sospecha, se despacha en segundo plano un correo de revisión manual al
        reclutador. La postulación nunca se bloquea por sospecha: la decisión
        de descartar es humana, el sistema solo la hace visible.
        """
        if datos_formulario is None:
            datos_formulario = {}

        # El PDF pasa al almacén definitivo aquí y no antes: este es el punto en
        # que la postulación existe de verdad. Se hace antes de indexar para que
        # la ruta que viaja a los metadatos sea ya la final; si se hiciera
        # después, el índice apuntaría un instante a un temporal.
        ruta_persistente_pdf = persistir_pdf(ruta_persistente_pdf)

        # --- ARQUITECTURA CONCURRENTE DE DOBLE INDEXACIÓN (Dual-Indexing) ---
        id_en_vacante = None

        # Índice Destino A: Pipeline cerrado (Solo si el candidato especificó un cargo)
        cargo_limpio = cargo_objetivo.strip() if cargo_objetivo else ""
        if cargo_limpio and cargo_limpio.lower() != "talento-global-empresa":
            db_vacante = CVVectorStoreManager(nombre_cargo=cargo_limpio)
            id_en_vacante = db_vacante.store_candidate(
                candidate_data, ruta_persistente_pdf, datos_formulario, verificacion=verificacion
            )

        # Índice Destino B: Repositorio consolidado histórico global corporativo
        db_global = CVVectorStoreManager(nombre_cargo="talento-global-empresa")
        id_en_global = db_global.store_candidate(
            candidate_data, ruta_persistente_pdf, datos_formulario, verificacion=verificacion
        )

        # --- ALERTA DE REVISIÓN MANUAL (fire-and-forget) ---
        # Mismo patrón que el auto-match: un fallo del correo no debe afectar a
        # la confirmación que ya recibió el candidato.
        if verificacion and verificacion.get("sospechoso"):
            from core.data_hygiene import primer_dato_valido
            threading.Thread(
                target=enviar_alerta_revision_cv,
                kwargs={
                    "nombre_candidato": primer_dato_valido(
                        datos_formulario.get("nombre"), candidate_data.nombre_completo,
                        default="Candidato sin nombre"
                    ),
                    "correo_candidato": primer_dato_valido(
                        datos_formulario.get("correo"), candidate_data.correo_electronico
                    ),
                    "vacante_destino": cargo_limpio or "Bolsa Global",
                    "veredicto": verificacion,
                    "pdf_path": ruta_persistente_pdf,
                },
                daemon=True
            ).start()

        return {
            "status": "success",
            "id_vacante_silo": id_en_vacante,
            "id_bolsa_global": id_en_global,
            "ruta_pdf_fisico": ruta_persistente_pdf,
            "datos_extraidos": candidate_data.model_dump(),
            "verificacion": verificacion
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
            datos_formulario=datos_formulario,
            verificacion=extraccion.get("verificacion")
        )