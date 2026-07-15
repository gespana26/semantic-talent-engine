"""
Background auto-match: evaluate candidate against a specific vacancy and notify.

Used by both CLI console (core/cli_console.py) and Streamlit portal views
(views/portal.py) to avoid code duplication.

Usage:

    from core.auto_match import evaluar_y_notificar_background

    # Launch in a daemon thread after candidate registration:
    thread = threading.Thread(
        target=evaluar_y_notificar_background,
        args=(silo_destino, datos_extraidos),
        daemon=True,
    )
    thread.start()
"""
import logging
from config.settings import clean_collection_name
from core.search_engine import CVSearchEngine
from core.email_service import enviar_alerta_talento

logger = logging.getLogger(__name__)


def evaluar_y_notificar_background(silo_destino, datos_extraidos):
    """Ejecuta un auto-match silencioso. Si el candidato es Top y >= 85%, alerta al reclutador."""
    try:
        if not silo_destino:
            return

        coleccion_target = clean_collection_name(silo_destino)
        buscador = CVSearchEngine(collection_name=coleccion_target)
        texto_vacante = buscador.obtener_perfil_vacante()

        if not texto_vacante:
            return

        candidatos_top = buscador.search_candidates(query_text=texto_vacante, limit=10)

        correo_nuevo = str(datos_extraidos.get('correo_electronico', '')).lower().strip()
        nombre_nuevo = datos_extraidos.get('nombre_completo', 'Candidato Destacado')
        extracto = datos_extraidos.get('perfil_profesional', 'Extracto no disponible')[:250] + "..."

        for cand in candidatos_top:
            if cand.get('correo', '').lower().strip() == correo_nuevo:
                afinidad = cand.get('porcentaje_afinidad', 0)
                if afinidad >= 85.0:
                    enviar_alerta_talento(nombre_nuevo, silo_destino, afinidad, extracto)
                break

    except Exception as e:
        logger.error("Error silencioso en background auto-match: %s", e)