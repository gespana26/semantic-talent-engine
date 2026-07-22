"""Evaluación del auto-match y decisión de alerta al reclutador.

Vive en la capa de dominio porque las dos interfaces —portal web y CLI— tenían
una copia literal de esta lógica. Una regla de negocio duplicada en dos vistas
es una regla que tarde o temprano diverge.

LA REGLA DE DECISIÓN Y POR QUÉ ES ASÍ
-------------------------------------
La regla anterior era `afinidad >= 85 %`. La medición sobre datos reales mostró
que no es sostenible:

  · Toda la población, pertinente o no, cae en una franja de siete puntos.
  · La afinidad media crece de forma casi lineal con la longitud del texto de
    consulta, de modo que el número depende tanto de cómo se redactó la vacante
    como de quién es el candidato.
  · Con el criterio de requisitos vigente, los siete candidatos de un silo real
    superaban el umbral: la alerta notificaba en el 100 % de los casos.

La decisión se apoya ahora en dos señales que no comparten ese defecto:

  1. **Cobertura de requisitos.** ¿Cumple las habilidades exigidas? Es una
     pregunta absoluta, verificable requisito a requisito y explicable al
     reclutador. Es la señal principal.
  2. **Percentil dentro del banco de talento.** ¿Destaca frente a los perfiles
     de los que realmente se dispone? Sitúa al candidato contra la distribución
     observada en lugar de contra una escala comprimida, y sigue siendo una
     afirmación absoluta sobre él: no depende de quién más se postuló a esa
     vacante concreta.

Si el banco es demasiado pequeño para que un percentil signifique algo, la
decisión recae solo en la cobertura, que no necesita distribución.
"""

import json

import chromadb
from chromadb.utils import embedding_functions

from config import settings
from config.settings import clean_collection_name
from core.email_service import enviar_alerta_talento
from core.requirements_coverage import evaluar_cobertura
from core.search_engine import CVSearchEngine

COLECCION_GLOBAL = "talento-global-empresa"
MAX_MUESTRA_BANCO = 500


def _funcion_embeddings():
    """Cliente de embeddings para la comprobación semántica de requisitos."""
    try:
        return embedding_functions.OllamaEmbeddingFunction(
            url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
            model_name=settings.EMBEDDING_MODEL
        )
    except Exception:
        return None


def _requisitos_de_la_vacante(buscador: CVSearchEngine) -> tuple:
    """Extrae del silo las habilidades exigidas y el título del cargo."""
    try:
        registro = buscador.collection.get(
            ids=[CVSearchEngine.ID_VACANTE], include=["metadatas"]
        )
        metadatos = registro.get("metadatas") or []
        if not metadatos or not metadatos[0]:
            return [], ""
        meta = metadatos[0]
        vacante = json.loads(meta.get("raw_json") or "{}")
        exigidas = list(vacante.get("hard_skills") or [])
        return exigidas, str(vacante.get("titulo_cargo") or meta.get("titulo_cargo") or "")
    except Exception:
        return [], ""


def _percentil_en_banco(criterio: str, distancia_candidato: float) -> tuple:
    """Posición del candidato dentro del banco de talento, en percentil.

    Devuelve (percentil, tamaño_de_la_muestra). El percentil es la proporción del
    banco que el candidato deja por detrás, de modo que 95 significa que solo un
    5 % del banco se ajusta mejor a esa vacante.
    """
    try:
        cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        banco = cliente.get_collection(
            name=COLECCION_GLOBAL, embedding_function=_funcion_embeddings()
        )
        try:
            total = banco.count()
        except Exception:
            total = MAX_MUESTRA_BANCO

        try:
            res = banco.query(
                query_texts=[criterio], n_results=min(total, MAX_MUESTRA_BANCO),
                where={"tipo_registro": "candidato"}, include=["metadatas", "distances"]
            )
        except Exception:
            res = banco.query(
                query_texts=[criterio], n_results=min(total, MAX_MUESTRA_BANCO),
                include=["metadatas", "distances"]
            )

        if not res.get("ids") or not res["ids"][0]:
            return None, 0

        # La bolsa global acumula un registro por postulación: se conserva el
        # mejor por identidad para no contar dos veces a la misma persona.
        mejor = {}
        for m, d in zip(res["metadatas"][0], res["distances"][0]):
            if not m or m.get("tipo_registro") == "perfil_vacante":
                continue
            clave = str(m.get("correo_electronico") or m.get("nombre_completo") or "?").lower().strip()
            if clave not in mejor or d < mejor[clave]:
                mejor[clave] = d

        distancias = list(mejor.values())
        if not distancias:
            return None, 0

        peores = sum(1 for d in distancias if d > distancia_candidato)
        return 100.0 * peores / len(distancias), len(distancias)
    except Exception:
        return None, 0


def evaluar_postulacion(silo_destino: str, datos_candidato: dict) -> dict:
    """Evalúa una postulación recién indexada y decide si merece alertar al reclutador.

    No envía nada: devuelve el veredicto y sus razones, de modo que la decisión
    sea inspeccionable y testeable con independencia del envío del correo.

    Args:
        silo_destino: Nombre de la vacante a la que se postuló el candidato;
            vacío para la bolsa global, donde no hay criterio contra el que
            evaluar.
        datos_candidato: Perfil extraído del candidato recién indexado.

    Returns:
        Veredicto con la clave ``alertar`` (bool), el ``motivo`` explicable, la
        ``afinidad`` reportada, el ``percentil`` en el banco y el ``desglose``
        del cálculo.
    """
    veredicto = {
        "alertar": False, "motivo": "", "afinidad": None, "percentil": None,
        "muestra_banco": 0, "cobertura": None, "desglose": None,
        "titulo_vacante": silo_destino
    }

    if not silo_destino:
        veredicto["motivo"] = "Postulación a la bolsa global: no hay vacante contra la que evaluar."
        return veredicto

    buscador = CVSearchEngine(collection_name=clean_collection_name(silo_destino))
    criterio = buscador.obtener_perfil_vacante()
    if not criterio:
        veredicto["motivo"] = "El silo no tiene una vacante registrada."
        return veredicto

    exigidas, titulo = _requisitos_de_la_vacante(buscador)
    veredicto["titulo_vacante"] = titulo or silo_destino

    # La vacante estructurada es lo que permite al buscador puntuar por
    # componentes. Sin ella `search_candidates` devuelve solo similitud, y la
    # alerta volvería a decidir sobre una escala distinta de la que ve el
    # reclutador: exactamente el fallo que motivó este módulo.
    vacante = buscador.obtener_vacante_estructurada()

    correo = str(datos_candidato.get("correo_electronico") or "").lower().strip()
    candidatos = buscador.search_candidates(query_text=criterio, limit=50, vacante=vacante)
    propio = next((c for c in candidatos if str(c.get("correo") or "").lower().strip() == correo), None)
    if not propio:
        veredicto["motivo"] = "El candidato no aparece entre los resultados del silo."
        return veredicto

    afinidad = propio.get("porcentaje_afinidad", 0)
    veredicto["afinidad"] = afinidad
    desglose = propio.get("desglose")
    veredicto["desglose"] = desglose

    # El percentil vive en el espacio de distancias del banco, así que hay que
    # deshacer la normalización —no la afinidad—. Invertir la afinidad sería
    # incorrecto: no es una función de la distancia desde que pondera cobertura,
    # experiencia y formación.
    base = float(propio.get("linea_base") or 0.0)
    normalizada = float(propio.get("similitud_normalizada") or 0.0) / 100.0
    distancia = 1.0 - (normalizada * (1.0 - base) + base)

    # --- Señal 1: cobertura de requisitos ---
    # Se reutiliza la del re-puntuado si existe: recalcularla aquí abriría la
    # puerta a que la alerta y el buscador discrepasen sobre el mismo candidato.
    if desglose and desglose.get("cobertura"):
        cobertura = desglose["cobertura"]
    else:
        cobertura = evaluar_cobertura(
            requisitos=exigidas,
            habilidades_candidato=list(datos_candidato.get("hard_skills") or []),
            texto_candidato=str(datos_candidato.get("perfil_profesional") or ""),
            funcion_embeddings=_funcion_embeddings()
        )
    veredicto["cobertura"] = cobertura

    if cobertura["ratio"] < settings.UMBRAL_COBERTURA_REQUISITOS:
        faltan = ", ".join(cobertura["faltantes"]) or "requisitos sin declarar"
        veredicto["motivo"] = (
            f"Cubre {len(cobertura['cubiertos'])} de {cobertura['total']} requisitos. "
            f"No se detectó: {faltan}."
        )
        return veredicto

    # --- Señal 2: posición dentro del banco de talento ---
    percentil, muestra = _percentil_en_banco(criterio, distancia)
    veredicto["percentil"] = percentil
    veredicto["muestra_banco"] = muestra

    if muestra >= settings.MIN_MUESTRA_PERCENTIL and percentil is not None:
        if percentil < settings.PERCENTIL_ALERTA:
            veredicto["motivo"] = (
                f"Cumple los requisitos, pero queda en el percentil {percentil:.0f} "
                f"del banco de talento para esta vacante."
            )
            return veredicto
        veredicto["motivo"] = (
            f"Cubre {len(cobertura['cubiertos'])} de {cobertura['total']} requisitos y "
            f"está en el percentil {percentil:.0f} del banco de talento."
        )
    else:
        # Banco pequeño: el percentil no es informativo y la cobertura decide sola.
        veredicto["motivo"] = (
            f"Cubre {len(cobertura['cubiertos'])} de {cobertura['total']} requisitos. "
            f"El banco de talento es demasiado pequeño para situarlo por percentil."
        )

    veredicto["alertar"] = True
    return veredicto


def evaluar_y_notificar(silo_destino: str, datos_candidato: dict) -> dict:
    """Evalúa la postulación y, si procede, despacha la alerta. Nunca propaga errores.

    Se ejecuta en un hilo secundario bajo un patrón fire-and-forget: un fallo aquí
    no debe afectar a la confirmación que ya recibió el candidato.
    """
    try:
        veredicto = evaluar_postulacion(silo_destino, datos_candidato)
        if veredicto["alertar"]:
            enviar_alerta_talento(
                nombre_candidato=datos_candidato.get("nombre_completo", "Candidato Destacado"),
                silo_destino=veredicto["titulo_vacante"],
                afinidad=veredicto["afinidad"],
                extracto=str(datos_candidato.get("perfil_profesional", "Extracto no disponible"))[:250] + "...",
                cobertura=veredicto["cobertura"],
                percentil=veredicto["percentil"]
            )
        if settings.DEBUG_MODE:
            print(f"[AUTO-MATCH] {silo_destino}: alertar={veredicto['alertar']} · {veredicto['motivo']}")
        return veredicto
    except Exception as e:
        print(f"Error silencioso en el hilo de telemetría: {e}")
        return {"alertar": False, "motivo": f"Error: {e}"}
