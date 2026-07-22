"""Mide la línea base de la similitud para poder escalar la afinidad con sentido.

EL PROBLEMA
-----------
La afinidad se calcula como (1 + coseno) / 2, fórmula que supone que un texto sin
relación alguna da coseno 0 y por tanto un 50 %. Es falso para los modelos de
embeddings de texto natural: en la medición con criterios ajenos, una vacante de
jardinería obtuvo un 85,46 % de afinidad media contra un banco de perfiles
tecnológicos. Despejando, el coseno entre textos sin relación es de unos 0,68.

Todo lo útil vive entre 0,68 y 0,82 de coseno, y la fórmula reparte ese margen
sobre una escala de 100 puntos de la que solo usa siete.

QUÉ MIDE ESTE SCRIPT
--------------------
1. **El efecto de las etiquetas compartidas.** El criterio de la vacante replica
   las etiquetas del documento del candidato ("Nivel Académico:", "Perfil
   Profesional:"...). Esa estructura común es texto que ambos lados comparten
   siempre, de modo que puede estar elevando el suelo por sí sola. Se compara el
   mismo contenido con y sin etiquetas.

2. **La línea base por vacante.** Se mide la similitud de cada criterio contra un
   conjunto de perfiles sintéticos manifiestamente ajenos al dominio. Ese valor
   es el cero real de esa vacante: la similitud que obtendría alguien que no
   tiene nada que ver.

3. **El efecto de normalizar.** Se recalcula la afinidad de los candidatos reales
   restando esa línea base, para comprobar que un perfil ajeno cae a cero y que
   los pertinentes conservan un rango utilizable.

USO
---
    python scripts/medir_linea_base.py

Requiere Ollama. Solo lee: no escribe ni modifica nada.
"""

import json
import sys

import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, ".")
from config import settings  # noqa: E402
from core.baseline import PERFILES_AJENOS, coseno, normalizar_similitud  # noqa: E402
from core.search_engine import CVSearchEngine  # noqa: E402

COLECCION_GLOBAL = "talento-global-empresa"
ID_VACANTE = "VACANTE_PRINCIPAL"

# Los perfiles de referencia y el cálculo de la línea base viven ya en
# `core/baseline.py`: son producción, no instrumental de medición. Este script
# mide contra exactamente el mismo conjunto que usa el buscador.


def afinidad_actual(cos: float) -> float:
    """Fórmula vigente: (1 + coseno) / 2."""
    return max(0.0, (1 + cos) / 2 * 100)


def afinidad_normalizada(cos: float, base: float) -> float:
    """Escala el coseno sobre el margen realmente disponible por encima de la línea base."""
    return 100.0 * normalizar_similitud(cos, base)


def sin_etiquetas(criterio: str) -> str:
    """Elimina las etiquetas estructurales dejando solo el contenido."""
    partes = []
    for linea in criterio.splitlines():
        partes.append(linea.split(":", 1)[1].strip() if ":" in linea else linea.strip())
    return ". ".join(p for p in partes if p)


def main() -> None:
    cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    ef = embedding_functions.OllamaEmbeddingFunction(
        url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL
    )

    # --- Documentos reales de los candidatos ---
    banco = cliente.get_collection(name=COLECCION_GLOBAL, embedding_function=ef)
    contenido = banco.get(include=["metadatas", "documents"])
    candidatos = {}
    for meta, doc in zip(contenido.get("metadatas") or [], contenido.get("documents") or []):
        if not meta or meta.get("tipo_registro") == "perfil_vacante" or not doc:
            continue
        clave = str(meta.get("correo_electronico") or meta.get("nombre_completo") or "?").lower()
        candidatos.setdefault(clave, doc)

    if not candidatos:
        print("El banco de talento está vacío.")
        return

    # --- Criterios reales ---
    criterios = []
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
        try:
            vacante = json.loads(meta.get("raw_json") or "{}")
        except (ValueError, TypeError):
            continue
        criterio = CVSearchEngine._componer_requisitos(vacante, meta)
        if criterio:
            criterios.append((col.name, criterio))

    if not criterios:
        print("No hay vacantes registradas.")
        return

    # --- Un solo lote de embeddings ---
    docs_cand = list(candidatos.values())
    crit_con = [c for _, c in criterios]
    crit_sin = [sin_etiquetas(c) for c in crit_con]
    perf_ajenos = [t for _, t in PERFILES_AJENOS]
    perf_ajenos_sin = [sin_etiquetas(t) for t in perf_ajenos]

    # Los documentos del candidato también se comparan en sus dos formatos: si solo
    # se quitaran las etiquetas de un lado, la caída de similitud mediría el
    # desemparejamiento de formatos y no el efecto real de la estructura compartida.
    docs_cand_sin = [sin_etiquetas(d) for d in docs_cand]

    todos = docs_cand + docs_cand_sin + crit_con + crit_sin + perf_ajenos + perf_ajenos_sin
    vectores = ef(todos)

    i = 0
    v_cand = vectores[i:i + len(docs_cand)]
    i += len(docs_cand)
    v_cand_sin = vectores[i:i + len(docs_cand_sin)]
    i += len(docs_cand_sin)
    v_con = vectores[i:i + len(crit_con)]
    i += len(crit_con)
    v_sin = vectores[i:i + len(crit_sin)]
    i += len(crit_sin)
    v_aj = vectores[i:i + len(perf_ajenos)]
    i += len(perf_ajenos)
    v_aj_sin = vectores[i:i + len(perf_ajenos_sin)]

    # =====================================================================
    print("=" * 86)
    print("1. EFECTO DE LAS ETIQUETAS COMPARTIDAS")
    print("=" * 86)
    print("   Se compara, para cada vacante, la similitud media con los candidatos reales")
    print("   frente a la similitud media con perfiles ajenos. Interesa la SEPARACIÓN.\n")
    print(f"   {'vacante':<24}{'formato':<16}{'cos real':>10}{'cos ajeno':>11}{'separación':>12}")
    print("   " + "-" * 71)

    sep_con_total, sep_sin_total = [], []
    for (nombre, _), vc, vs in zip(criterios, v_con, v_sin):
        formatos = (
            ("con etiquetas", vc, v_cand, v_aj),
            ("sin etiquetas", vs, v_cand_sin, v_aj_sin),
        )
        for etiqueta, vec_crit, vec_reales, vec_ajenos in formatos:
            cos_real = sum(coseno(vec_crit, v) for v in vec_reales) / len(vec_reales)
            cos_ajeno = sum(coseno(vec_crit, v) for v in vec_ajenos) / len(vec_ajenos)
            sep = cos_real - cos_ajeno
            (sep_con_total if etiqueta == "con etiquetas" else sep_sin_total).append(sep)
            print(f"   {nombre[:23]:<24}{etiqueta:<16}{cos_real:>10.4f}{cos_ajeno:>11.4f}{sep:>12.4f}")
        print()

    media_con = sum(sep_con_total) / len(sep_con_total)
    media_sin = sum(sep_sin_total) / len(sep_sin_total)
    print(f"   Separación media CON etiquetas: {media_con:.4f}")
    print(f"   Separación media SIN etiquetas: {media_sin:.4f}")
    if media_sin > media_con:
        mejora = (media_sin - media_con) / media_con * 100 if media_con else 0
        print(f"   -> Quitar las etiquetas MEJORA la separación un {mejora:.1f} %.")
    else:
        print("   -> Las etiquetas no perjudican: el suelo no viene de la estructura compartida.")

    # =====================================================================
    print("\n" + "=" * 86)
    print("2. LÍNEA BASE POR VACANTE Y EFECTO DE NORMALIZAR")
    print("=" * 86)
    print("   Línea base = mayor similitud con un perfil manifiestamente ajeno.")
    print("   Es el cero real de esa vacante.\n")
    print(f"   {'vacante':<24}{'base':>8}{'afinidad actual':>18}{'afinidad normaliz.':>21}")
    print(f"   {'':<24}{'':>8}{'ajeno / real':>18}{'ajeno / real':>21}")
    print("   " + "-" * 71)

    for (nombre, _), vc in zip(criterios, v_con):
        base = max(coseno(vc, v) for v in v_aj)
        cos_reales = [coseno(vc, v) for v in v_cand]
        cos_ajeno_medio = sum(coseno(vc, v) for v in v_aj) / len(v_aj)
        real_medio = sum(cos_reales) / len(cos_reales)

        act_aj, act_real = afinidad_actual(cos_ajeno_medio), afinidad_actual(real_medio)
        nor_aj = afinidad_normalizada(cos_ajeno_medio, base)
        nor_real = afinidad_normalizada(real_medio, base)
        nor_max = afinidad_normalizada(max(cos_reales), base)

        print(f"   {nombre[:23]:<24}{base:>8.4f}"
              f"{act_aj:>8.1f} /{act_real:>8.1f}"
              f"{nor_aj:>11.1f} /{nor_real:>8.1f}   (máx {nor_max:.1f})")

    # =====================================================================
    print("\n" + "=" * 86)
    print("3. CONSTANTES SUGERIDAS")
    print("=" * 86)
    bases = [max(coseno(vc, v) for v in v_aj) for vc in v_con]
    print(f"   Línea base observada: mínimo {min(bases):.4f} · media {sum(bases) / len(bases):.4f} "
          f"· máximo {max(bases):.4f}")
    print("   La línea base se calcula por vacante en tiempo de ejecución, así que no hace")
    print("   falta fijarla como constante: basta con incrustar los perfiles de referencia")
    print("   junto al criterio, que es una sola llamada más al modelo de embeddings.")


if __name__ == "__main__":
    main()
