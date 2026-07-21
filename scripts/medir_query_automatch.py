"""Mide qué texto de la vacante funciona mejor como consulta del auto-match.

CONTEXTO DEL EXPERIMENTO
------------------------
El auto-match consulta hoy con `texto_original`: el texto plano que el reclutador
pegó al registrar la vacante. Los candidatos, en cambio, se vectorizaron desde un
`document_text` estructurado (Candidato / Nivel Académico / Perfil / Habilidades /
Historial). Son dos registros de escritura distintos comparándose en el mismo
espacio vectorial, y el texto plano arrastra ruido de convocatoria (beneficios,
"empresa líder", instrucciones de postulación) que no existe del lado del candidato.

La hipótesis es que ese ruido degrada el ranking. No se corrige por teoría: se mide.

VARIANTES COMPARADAS
--------------------
  A · texto_original      El texto crudo de la oferta. Era la ruta anterior para
                          las vacantes registradas desde texto libre.
  B · document_text       El texto con el que se vectorizó la propia vacante.
  C · perfil + skills     `perfil_general` + `hard_skills`. Era la ruta anterior
                          para las vacantes registradas desde PDF.
  D · requisitos          **La ruta actual.** Replica la forma del documento del
                          candidato e incorpora los estudios requeridos, la
                          experiencia mínima y las soft skills, que estaban
                          almacenados pero no llegaban a la comparación.

QUÉ MIRAR EN LA SALIDA
----------------------
La métrica que decide no es la distancia media sino la última tabla: **si alguna
variante cruza el umbral del 85 % para candidatos distintos, la elección del texto
de consulta está cambiando a quién se le envía la alerta al reclutador.** Ese es un
efecto observable sobre el comportamiento del sistema, no una diferencia numérica
sin consecuencia.

USO
---
    python scripts/medir_query_automatch.py              # todos los silos
    python scripts/medir_query_automatch.py ingeniero-civil

Requiere Ollama en marcha (para los embeddings) y la ChromaDB del proyecto poblada.
El script solo lee: no escribe, no modifica y no borra nada.
"""

import json
import sys

import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, ".")
from config import settings  # noqa: E402
from core.search_engine import CVSearchEngine  # noqa: E402

ID_VACANTE = "VACANTE_PRINCIPAL"
COLECCION_GLOBAL = "talento-global-empresa"
TEXTO_AUSENTE = "Texto original no disponible"
UMBRAL_ALERTA = 85.0
N_RESULTADOS = 50


def afinidad(distancia: float) -> float:
    """Replica la normalización del motor: distancia coseno 0-2 a porcentaje 0-100."""
    return max(0.0, (1 - (distancia / 2.0)) * 100)


def construir_variantes(meta: dict, documento: str) -> dict:
    """Deriva los tres textos de consulta candidatos a partir del registro de la vacante."""
    variantes = {}

    texto_original = str(meta.get("texto_original", ""))
    if texto_original and texto_original != TEXTO_AUSENTE:
        variantes["A · texto_original"] = texto_original

    if documento:
        variantes["B · document_text"] = documento

    raw = meta.get("raw_json")
    if raw:
        try:
            datos = json.loads(raw)
            perfil = datos.get("perfil_general", "")
            skills = " ".join(datos.get("hard_skills", []))
            estructurado = f"{perfil} {skills}".strip()
            if estructurado:
                variantes["C · perfil + skills"] = estructurado

            # D es la ruta implantada: replica la forma del documento del candidato
            # e incorpora estudios requeridos, experiencia mínima y soft skills, que
            # estaban almacenados pero no llegaban a la comparación.
            requisitos = CVSearchEngine._componer_requisitos(datos, meta)
            if requisitos:
                variantes["D · requisitos"] = requisitos
        except (ValueError, TypeError):
            pass

    return variantes


def consultar(coleccion, texto: str) -> dict:
    """Devuelve {correo: (distancia, nombre)} para los candidatos del silo."""
    try:
        res = coleccion.query(
            query_texts=[texto],
            n_results=N_RESULTADOS,
            where={"tipo_registro": "candidato"},
            include=["metadatas", "distances"]
        )
    except Exception:
        res = coleccion.query(
            query_texts=[texto], n_results=N_RESULTADOS, include=["metadatas", "distances"]
        )

    salida = {}
    if not res.get("ids") or not res["ids"][0]:
        return salida

    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
        if meta.get("tipo_registro") == "perfil_vacante":
            continue
        clave = (meta.get("correo_electronico") or meta.get("nombre_completo") or "?").lower()
        if clave not in salida:
            salida[clave] = (dist, meta.get("nombre_completo", "?"))
    return salida


def analizar_silo(cliente, nombre: str, ef) -> None:
    coleccion = cliente.get_collection(name=nombre, embedding_function=ef)

    registro = coleccion.get(ids=[ID_VACANTE], include=["metadatas", "documents"])
    metadatos = registro.get("metadatas") or []
    if not metadatos or not metadatos[0]:
        return

    meta = metadatos[0]
    documentos = registro.get("documents") or [""]
    variantes = construir_variantes(meta, documentos[0] if documentos else "")

    if len(variantes) < 2:
        print(f"\n[{nombre}] Solo hay una variante disponible; nada que comparar.")
        return

    print("\n" + "=" * 78)
    print(f"SILO: {nombre}   ({meta.get('titulo_cargo', '?')})")
    print("=" * 78)

    for etiqueta, texto in variantes.items():
        print(f"\n  {etiqueta}  ({len(texto)} caracteres)")
        print(f"    {texto[:160].strip()}{'...' if len(texto) > 160 else ''}")

    resultados = {etq: consultar(coleccion, txt) for etq, txt in variantes.items()}
    candidatos = sorted(set().union(*[set(r) for r in resultados.values()]))
    if not candidatos:
        print("\n  Sin candidatos indexados en este silo.")
        return

    etiquetas = list(variantes)

    # --- Afinidad por candidato bajo cada variante ---
    print("\n  AFINIDAD POR CANDIDATO (%)")
    print("  " + "-" * 74)
    print(f"  {'Candidato':<26}" + "".join(f"{e[:16]:>17}" for e in etiquetas))
    print("  " + "-" * 74)
    for clave in candidatos:
        nombre_cand = next((r[clave][1] for r in resultados.values() if clave in r), clave)
        fila = f"  {str(nombre_cand)[:25]:<26}"
        for etq in etiquetas:
            fila += f"{afinidad(resultados[etq][clave][0]):>16.2f} " if clave in resultados[etq] else f"{'—':>17}"
        print(fila)

    # --- Orden inducido por cada variante ---
    print("\n  RANKING (mejor a peor)")
    for etq in etiquetas:
        orden = sorted(resultados[etq].items(), key=lambda kv: kv[1][0])
        print(f"    {etq:<22} " + " > ".join(str(v[1])[:16] for _, v in orden[:5]))

    referencia = sorted(resultados[etiquetas[0]].items(), key=lambda kv: kv[1][0])
    top_ref = {k for k, _ in referencia[:3]}
    for etq in etiquetas[1:]:
        top = {k for k, _ in sorted(resultados[etq].items(), key=lambda kv: kv[1][0])[:3]}
        print(f"    Coincidencia en el top-3 de {etq:<22} {len(top_ref & top)}/{len(top_ref)}")

    # --- La métrica que decide ---
    print(f"\n  ¿QUIÉN DISPARA LA ALERTA? (umbral {UMBRAL_ALERTA} %)")
    discrepancias = 0
    for clave in candidatos:
        decisiones = {}
        for etq in etiquetas:
            decisiones[etq] = clave in resultados[etq] and afinidad(resultados[etq][clave][0]) >= UMBRAL_ALERTA
        if len(set(decisiones.values())) > 1:
            discrepancias += 1
            nombre_cand = next((r[clave][1] for r in resultados.values() if clave in r), clave)
            detalle = ", ".join(f"{e}={'SÍ' if v else 'no'}" for e, v in decisiones.items())
            print(f"    ⚠  {nombre_cand}: {detalle}")

    if discrepancias == 0:
        print("    Ninguna discrepancia: la elección del texto no cambia a quién se alerta.")
    else:
        print(f"    {discrepancias} candidato(s) cambian de decisión según el texto de consulta.")


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

    if not nombres:
        print("No se encontraron silos de vacantes.")
        return

    for nombre in nombres:
        try:
            analizar_silo(cliente, nombre, ef)
        except Exception as e:
            print(f"\n[{nombre}] No se pudo analizar: {e}")

    print("\n" + "=" * 78)
    print("Criterio de decisión: si la última tabla no muestra discrepancias en varios")
    print("silos con datos reales, la ruta actual es defendible y el hallazgo se")
    print("documenta como riesgo acotado. Si las muestra, conviene alinear la consulta")
    print("con la forma estructurada y reflejarlo en §3.5.2.")


if __name__ == "__main__":
    main()