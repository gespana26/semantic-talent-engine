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
SIN_LIMITE = "∞"


def _silos(cliente):
    """Colecciones que son silos de vacante, excluida la bolsa global."""
    for col in cliente.list_collections():
        if col.name != COLECCION_GLOBAL:
            yield col


def _leer_vacante(col):
    """Metadatos del registro de vacante del silo, o `None` si no lo tiene.

    **Acceso directo por clave.** El silo es autocontenido: la vacante convive
    con sus candidatos bajo el identificador fijo `VACANTE_PRINCIPAL`. Leerla con
    `get(ids=[...])` cuesta lo mismo con cuarenta candidatos que con cuatro mil;
    recorrer la colección entera para encontrarla —que es lo que hacía el
    sidebar— arrastra ademas el `raw_json` completo de cada perfil, y lo hacía en
    cada repintado de Streamlit.
    """
    try:
        registro = col.get(ids=[ID_VACANTE], include=["metadatas"])
    except Exception:
        return None
    metadatos = registro.get("metadatas") or []
    return metadatos[0] if metadatos and metadatos[0] else None


def _dias_restantes(meta: dict, hoy: datetime):
    """Días hasta la expiración, o `None` si la vacante no declara una válida.

    **Se comparan fechas, no instantes.** La resta se hacía entre el `datetime`
    de la fecha de expiración —que `strptime` sitúa a las 00:00— y el momento
    actual, de modo que el mismo día de la expiración daba −1 y la vacante
    constaba como cerrada desde las 00:00:01. El último día se perdía en
    silencio: `orchestrator.py` concede treinta días de vigencia por defecto y el
    candidato disponía de veintinueve.

    La expiración es una fecha de calendario, no una hora, y comparar solo la
    parte de fecha es lo que hace que `dias == 0` signifique lo que aparenta:
    hoy es el último día y todavía se admite postulación.
    """
    fecha_exp = str((meta or {}).get("timestamp_expiracion", ""))
    if len(fecha_exp) != 8:
        return None
    try:
        return (datetime.strptime(fecha_exp, "%Y%m%d").date() - hoy.date()).days
    except ValueError:
        return None


def obtener_silos_del_reclutador() -> list:
    """Silos que el reclutador puede consultar, con su vigencia.

    Reglas de visibilidad **deliberadamente distintas** de las del portal, y la
    diferencia no es un descuido:

    - **No se descartan las vacantes expiradas, se marcan.** Sus candidatos
      siguen ahí, y ocultarle al reclutador a quien se postuló a una vacante que
      acaba de cerrar seria esconderle sus propios datos. El portal sí las
      descarta, porque allí la pregunta es otra: a qué se puede uno postular hoy.
    - **Se incluyen los silos sin registro de vacante.** Para el candidato no son
      postulables; para el reclutador son colecciones reales que puede necesitar
      inspeccionar.

    Que ambas proyecciones vivan en este módulo es lo que permite compararlas.
    Mientras el sidebar calculaba la suya por su cuenta, la divergencia entre las
    dos no la había decidido nadie.
    """
    silos = []
    try:
        cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        hoy = datetime.now()

        for col in _silos(cliente):
            dias = _dias_restantes(_leer_vacante(col), hoy)
            silos.append({
                "nombre": col.name,
                "dias": SIN_LIMITE if dias is None else max(0, dias),
                "expirada": dias is not None and dias < 0,
            })
    except Exception:
        pass

    return silos


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

        for col in _silos(cliente):
            meta = _leer_vacante(col)
            if meta is None:
                continue

            dias_restantes = _dias_restantes(meta, hoy)
            if dias_restantes is not None and dias_restantes < 0:
                continue

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
