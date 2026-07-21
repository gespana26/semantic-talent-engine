"""Deriva el umbral de la alerta de auto-match a partir de las distribuciones reales.

EL PROBLEMA QUE RESUELVE
------------------------
El umbral del 85 % se fijó por criterio, no por medición. Con el criterio de
requisitos vigente, los siete candidatos de un silo medido lo superan: la alerta
notifica en el 100 % de los casos y deja de discriminar.

Fijar otro número por intuición sería repetir el error. Lo que falta para
calibrarlo es una población de contraste: perfiles que **no** se postularon a esa
vacante. La bolsa global la contiene.

EL EXPERIMENTO
--------------
Para cada vacante se compone su criterio de requisitos y se consulta contra la
bolsa global. Los resultados se separan en dos poblaciones:

  · POSTULANTES     candidatos que sí se postularon a esa vacante.
  · NO POSTULANTES  el resto de la bolsa. Población de contraste.

El umbral útil es el que mejor separa ambas distribuciones.

LIMITACIÓN QUE HAY QUE DECLARAR
-------------------------------
La etiqueta es ruidosa por construcción: un candidato de la bolsa global puede
encajar perfectamente en una vacante a la que no se postuló. Los "no postulantes"
no son negativos verdaderos sino una muestra de la población general. En
consecuencia, la tasa de falsos positivos que se reporta aquí es una **cota
superior pesimista**, y el solapamiento entre poblaciones no debe leerse como
error del sistema. Sirve para situar el umbral, no para medir precisión.

USO
---
    python scripts/calibrar_umbral_alerta.py
    python scripts/calibrar_umbral_alerta.py project-manager

Requiere Ollama en marcha. El script solo lee: no escribe ni modifica nada.
"""

import json
import sys

import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, ".")
from config import settings  # noqa: E402
from core.search_engine import CVSearchEngine  # noqa: E402

COLECCION_GLOBAL = "talento-global-empresa"
ID_VACANTE = "VACANTE_PRINCIPAL"
UMBRAL_ACTUAL = 85.0
MAX_RESULTADOS = 500


def afinidad(distancia: float) -> float:
    """Replica la normalización del motor: distancia coseno 0-2 a porcentaje 0-100."""
    return max(0.0, (1 - (distancia / 2.0)) * 100)


def resumen(valores: list) -> dict:
    """Estadísticos de posición sin dependencias externas."""
    v = sorted(valores)
    n = len(v)
    pct = lambda p: v[min(n - 1, max(0, int(round(p * (n - 1)))))]  # noqa: E731
    return {
        "n": n, "min": v[0], "p10": pct(0.10), "p25": pct(0.25), "mediana": pct(0.50),
        "p75": pct(0.75), "p90": pct(0.90), "p95": pct(0.95), "max": v[-1],
        "media": sum(v) / n
    }


def imprimir_resumen(etiqueta: str, r: dict) -> None:
    print(f"    {etiqueta:<18} n={r['n']:<4} min={r['min']:.2f}  p25={r['p25']:.2f}  "
          f"mediana={r['mediana']:.2f}  p75={r['p75']:.2f}  p95={r['p95']:.2f}  max={r['max']:.2f}")


def histograma(positivos: list, negativos: list, ancho: int = 46) -> None:
    """Dibuja ambas distribuciones sobre el mismo eje para que el solapamiento se vea."""
    todos = positivos + negativos
    if not todos:
        return
    lo, hi = min(todos), max(todos)
    if hi - lo < 1e-9:
        return

    n_bins = 14
    def binear(vals):
        cubos = [0] * n_bins
        for v in vals:
            i = min(n_bins - 1, int((v - lo) / (hi - lo) * n_bins))
            cubos[i] += 1
        return cubos

    cp, cn = binear(positivos), binear(negativos)
    escala = max(max(cp or [0]), max(cn or [0])) or 1

    print(f"\n    Distribución de afinidad ({lo:.1f} % a {hi:.1f} %)")
    print(f"    {'rango':<16}{'postulantes':<{ancho // 2}}no postulantes")
    for i in range(n_bins - 1, -1, -1):
        centro_lo = lo + (hi - lo) * i / n_bins
        barra_p = "#" * int(cp[i] / escala * (ancho // 2 - 6))
        barra_n = "." * int(cn[i] / escala * (ancho // 2 - 6))
        print(f"    {centro_lo:>6.2f} %      {barra_p:<{ancho // 2}}{barra_n}")


def evaluar_umbrales(positivos: list, negativos: list) -> dict:
    """Recorre los umbrales observados y calcula sensibilidad y tasa de falsos positivos."""
    # Sin redondear: un umbral redondeado puede dejar fuera al valor que lo generó
    # y reportar una tasa de falsos positivos optimista por un error de coma flotante.
    candidatos = sorted(set(positivos + negativos))
    filas = []
    for t in candidatos:
        tpr = sum(1 for v in positivos if v >= t) / len(positivos) if positivos else 0.0
        fpr = sum(1 for v in negativos if v >= t) / len(negativos) if negativos else 0.0
        filas.append({"umbral": t, "tpr": tpr, "fpr": fpr, "j": tpr - fpr})
    return filas


def recomendar(filas: list) -> dict:
    """Propone dos umbrales con criterios explícitos y complementarios."""
    if not filas:
        return {}

    # 1. Índice J de Youden: el punto que maximiza sensibilidad menos falsos positivos.
    #    Es el equilibrio estándar cuando ambos errores pesan parecido.
    youden = max(filas, key=lambda f: (f["j"], f["umbral"]))

    # 2. Presupuesto de falsos positivos: el umbral más bajo que mantiene la tasa
    #    de falsos positivos por debajo del 10 %. Maximiza la sensibilidad dentro
    #    de un presupuesto de ruido aceptable para el reclutador.
    presupuestados = [f for f in filas if f["fpr"] <= 0.10]
    presupuesto = min(presupuestados, key=lambda f: f["umbral"]) if presupuestados else youden

    return {"youden": youden, "presupuesto": presupuesto}


def poblaciones_del_silo(cliente, ef, nombre: str):
    """Devuelve (criterio, postulantes, no_postulantes) en porcentaje de afinidad."""
    silo = cliente.get_collection(name=nombre, embedding_function=ef)
    registro = silo.get(ids=[ID_VACANTE], include=["metadatas"])
    metadatos = registro.get("metadatas") or []
    if not metadatos or not metadatos[0]:
        return None, [], []

    meta = metadatos[0]
    try:
        vacante = json.loads(meta.get("raw_json") or "{}")
    except (ValueError, TypeError):
        vacante = {}
    criterio = CVSearchEngine._componer_requisitos(vacante, meta)
    if not criterio:
        return None, [], []

    # Correos de quienes se postularon a esta vacante.
    contenido = silo.get(include=["metadatas"])
    postulantes = set()
    for m in contenido.get("metadatas") or []:
        if not m or m.get("tipo_registro") == "perfil_vacante":
            continue
        correo = str(m.get("correo_electronico") or "").lower().strip()
        if correo:
            postulantes.add(correo)

    glob = cliente.get_collection(name=COLECCION_GLOBAL, embedding_function=ef)
    try:
        total = glob.count()
    except Exception:
        total = MAX_RESULTADOS

    try:
        res = glob.query(
            query_texts=[criterio], n_results=min(total, MAX_RESULTADOS),
            where={"tipo_registro": "candidato"}, include=["metadatas", "distances"]
        )
    except Exception:
        res = glob.query(
            query_texts=[criterio], n_results=min(total, MAX_RESULTADOS),
            include=["metadatas", "distances"]
        )

    if not res.get("ids") or not res["ids"][0]:
        return criterio, [], []

    # La bolsa global acumula un registro por postulación: nos quedamos con el
    # mejor por identidad para no contar dos veces a la misma persona.
    mejor_por_correo = {}
    for m, d in zip(res["metadatas"][0], res["distances"][0]):
        if not m or m.get("tipo_registro") == "perfil_vacante":
            continue
        correo = str(m.get("correo_electronico") or m.get("nombre_completo") or "?").lower().strip()
        if correo not in mejor_por_correo or d < mejor_por_correo[correo]:
            mejor_por_correo[correo] = d

    pos, neg = [], []
    for correo, d in mejor_por_correo.items():
        (pos if correo in postulantes else neg).append(afinidad(d))

    return criterio, pos, neg


def informe_silo(nombre: str, criterio: str, pos: list, neg: list) -> None:
    print("\n" + "=" * 78)
    print(f"SILO: {nombre}")
    print("=" * 78)
    print(f"  Criterio ({len(criterio)} caracteres):")
    for linea in criterio.splitlines():
        print(f"    | {linea}")

    if not pos or not neg:
        print(f"\n  Sin poblaciones suficientes (postulantes={len(pos)}, no postulantes={len(neg)}).")
        return

    print("\n  DISTRIBUCIONES (afinidad %)")
    imprimir_resumen("Postulantes", resumen(pos))
    imprimir_resumen("No postulantes", resumen(neg))
    histograma(pos, neg)

    filas = evaluar_umbrales(pos, neg)
    rec = recomendar(filas)
    actual = next((f for f in filas if f["umbral"] >= UMBRAL_ACTUAL), None)

    print("\n  UMBRALES")
    if actual:
        print(f"    Actual ({UMBRAL_ACTUAL:.0f} %)        alerta al {actual['tpr'] * 100:.0f} % de los "
              f"postulantes y al {actual['fpr'] * 100:.0f} % del resto")
    print(f"    Youden (equilibrio)  {rec['youden']['umbral']:.2f} %   sensibilidad "
          f"{rec['youden']['tpr'] * 100:.0f} %, falsos positivos {rec['youden']['fpr'] * 100:.0f} %")
    print(f"    Presupuesto FP≤10 %  {rec['presupuesto']['umbral']:.2f} %   sensibilidad "
          f"{rec['presupuesto']['tpr'] * 100:.0f} %, falsos positivos {rec['presupuesto']['fpr'] * 100:.0f} %")


def main() -> None:
    cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    ef = embedding_functions.OllamaEmbeddingFunction(
        url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL
    )

    solicitados = sys.argv[1:]
    nombres = [c.name for c in cliente.list_collections() if c.name != COLECCION_GLOBAL]
    if solicitados:
        nombres = [n for n in nombres if n in solicitados]

    acum_pos, acum_neg = [], []
    for nombre in nombres:
        try:
            criterio, pos, neg = poblaciones_del_silo(cliente, ef, nombre)
            if criterio is None:
                continue
            informe_silo(nombre, criterio, pos, neg)
            acum_pos += pos
            acum_neg += neg
        except Exception as e:
            print(f"\n[{nombre}] No se pudo analizar: {e}")

    if not acum_pos or not acum_neg:
        print("\nNo hay datos suficientes para proponer un umbral global.")
        return

    print("\n" + "=" * 78)
    print("AGREGADO DE TODOS LOS SILOS")
    print("=" * 78)
    imprimir_resumen("Postulantes", resumen(acum_pos))
    imprimir_resumen("No postulantes", resumen(acum_neg))
    histograma(acum_pos, acum_neg)

    filas = evaluar_umbrales(acum_pos, acum_neg)
    rec = recomendar(filas)
    actual = next((f for f in filas if f["umbral"] >= UMBRAL_ACTUAL), None)

    print("\n  PROPUESTA DE UMBRAL")
    if actual:
        print(f"    Umbral actual  {UMBRAL_ACTUAL:.0f} %  ->  alerta al {actual['tpr'] * 100:.0f} % de los "
              f"postulantes y al {actual['fpr'] * 100:.0f} % del resto de la bolsa")
    print(f"    Youden         {rec['youden']['umbral']:.2f} %  ->  sensibilidad "
          f"{rec['youden']['tpr'] * 100:.0f} %, falsos positivos {rec['youden']['fpr'] * 100:.0f} %")
    print(f"    Presupuesto FP≤10% {rec['presupuesto']['umbral']:.2f} %  ->  sensibilidad "
          f"{rec['presupuesto']['tpr'] * 100:.0f} %, falsos positivos {rec['presupuesto']['fpr'] * 100:.0f} %")

    print("\n  CÓMO LEERLO")
    print("    · Si las dos distribuciones apenas se solapan, el umbral propuesto es sólido")
    print("      y puede sustituir al 85 % con respaldo empírico.")
    print("    · Si se solapan mucho, el problema no es el número: la afinidad por sí sola")
    print("      no separa perfiles pertinentes de los que no lo son, y conviene documentarlo")
    print("      como limitación medida en lugar de simular una calibración.")
    print("    · Recuerda que los 'no postulantes' no son negativos verdaderos, de modo que")
    print("      la tasa de falsos positivos es una cota superior pesimista.")


if __name__ == "__main__":
    main()
