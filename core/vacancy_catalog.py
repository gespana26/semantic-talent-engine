"""Consultas de catálogo sobre el conjunto de silos de vacantes.

Vive en la capa de dominio y no en la de presentación porque ambas interfaces
—el portal web y la CLI— necesitan la misma respuesta a la misma pregunta:
qué vacantes admiten hoy una postulación. Que la proyección destinada al
candidato se calcule aquí, y no en cada vista, es lo que garantiza que las dos
apliquen idénticas reglas de visibilidad.
"""

from datetime import datetime

import chromadb

from config import settings

COLECCION_GLOBAL = "talento-global-empresa"
ID_VACANTE = "VACANTE_PRINCIPAL"
TEXTO_AUSENTE = "Texto original no disponible"


def obtener_vacantes_publicas() -> list:
    """Devuelve las vacantes a las que un candidato puede postularse hoy.

    Reglas de visibilidad del portal, distintas de las del dashboard:

    - Se exige que la colección contenga el registro `VACANTE_PRINCIPAL`. Una
      colección sin oferta no es una vacante sino un silo residual, y por tanto
      no es postulable.
    - Se descartan las vacantes expiradas: si no se puede postular, no se muestra.
    - Se devuelve únicamente el texto que el reclutador redactó como oferta. No se
      aplica el fallback al primer documento de la colección que usa el visor del
      reclutador, porque en esa misma colección viven los candidatos y ese
      fallback expondría el perfil de un tercero.
    """
    vacantes = []
    try:
        cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        hoy = datetime.now()

        for col in cliente.list_collections():
            if col.name == COLECCION_GLOBAL:
                continue
            try:
                registro = col.get(ids=[ID_VACANTE], include=["metadatas"])
            except Exception:
                continue

            metadatos = registro.get("metadatas") or []
            if not metadatos or not metadatos[0]:
                continue

            meta = metadatos[0]
            dias_restantes = None
            fecha_exp = str(meta.get("timestamp_expiracion", ""))
            if len(fecha_exp) == 8:
                try:
                    dias_restantes = (datetime.strptime(fecha_exp, "%Y%m%d") - hoy).days
                    if dias_restantes < 0:
                        continue
                except ValueError:
                    dias_restantes = None

            detalle = str(meta.get("texto_original", ""))
            if detalle == TEXTO_AUSENTE:
                detalle = ""

            vacantes.append({
                "coleccion": col.name,
                "titulo": str(meta.get("titulo_cargo") or col.name.replace("-", " ").title()),
                "detalle": detalle,
                "dias": dias_restantes
            })
    except Exception:
        pass

    return sorted(vacantes, key=lambda v: v["titulo"].lower())
