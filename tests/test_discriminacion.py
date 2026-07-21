"""Test decisivo: ¿la afinidad discrimina, o está saturada?

LA PREGUNTA
-----------
La calibración mostró que postulantes y no postulantes se solapan casi por
completo. Ese resultado admite dos lecturas opuestas:

  H1 · MÉTRICA SATURADA      La afinidad da valores altos a casi cualquier
                             perfil y no distingue lo pertinente de lo que no
                             lo es. Sería un fallo del enfoque.

  H2 · POBLACIÓN HOMOGÉNEA   La métrica funciona, pero todos los candidatos
                             del banco son perfiles tecnológicos y todas las
                             vacantes son tecnológicas, así que se parecen de
                             verdad. El solapamiento sería correcto.

Con los datos existentes no se pueden distinguir, porque faltan negativos
verdaderos: nadie del banco es manifiestamente ajeno a las vacantes.

EL EXPERIMENTO
--------------
Se componen criterios de vacantes **deliberadamente ajenas** al dominio del
banco de talento (cocina, enfermería, derecho penal, aviación, veterinaria) con
exactamente la misma estructura que los criterios reales, y se miden contra los
mismos candidatos.

  · Si los criterios ajenos puntúan como los reales  ->  H1, métrica saturada.
  · Si caen de forma marcada                          ->  H2, métrica válida.

CONTROL DE LA LONGITUD
----------------------
Se estableció que la afinidad media crece con la longitud del texto de consulta.
Por eso los criterios ajenos se construyen en tres tamaños y el informe reporta
la correlación entre longitud y afinidad media: si el efecto de la longitud
fuera mayor que el del contenido, el experimento lo haría visible en lugar de
ocultarlo.

USO
---
    python scripts/test_discriminacion.py

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
MAX_RESULTADOS = 500


# Vacantes inventadas, ajenas al dominio del banco de talento. Se declaran con la
# misma estructura que las reales para que la comparación sea de contenido y no
# de forma. Los tres tamaños permiten separar el efecto de la longitud.
VACANTES_AJENAS = [
    {
        "titulo_cargo": "Chef de Cocina",
        "estudios_requeridos": ["Escuela de Alta Cocina", "Certificación en Manipulación de Alimentos"],
        "experiencia_minima_anos": 5,
        "perfil_general": ("Responsable de la elaboración de los menús diarios, la gestión del "
                           "servicio de cocina y el control de escandallos y mermas en un "
                           "restaurante de alta rotación."),
        "hard_skills": ["Cocina mediterránea", "Emplatado", "Control de escandallos", "Repostería"],
        "soft_skills": ["Trabajo bajo presión", "Liderazgo de brigada"],
    },
    {
        "titulo_cargo": "Enfermero de Urgencias",
        "estudios_requeridos": ["Grado en Enfermería", "Especialidad en Urgencias y Emergencias"],
        "experiencia_minima_anos": 3,
        "perfil_general": ("Atención directa al paciente en el servicio de urgencias hospitalarias, "
                           "triaje, administración de medicación y asistencia en procedimientos "
                           "invasivos."),
        "hard_skills": ["Triaje Manchester", "Canalización de vías", "Soporte vital avanzado"],
        "soft_skills": ["Empatía con el paciente", "Serenidad en situaciones críticas"],
    },
    {
        "titulo_cargo": "Abogado Penalista",
        "estudios_requeridos": ["Licenciatura en Derecho", "Colegiatura vigente"],
        "experiencia_minima_anos": 6,
        "perfil_general": ("Defensa de clientes en procesos penales, redacción de escritos de "
                           "acusación y defensa, y representación en vistas orales ante juzgados "
                           "de lo penal."),
        "hard_skills": ["Derecho procesal penal", "Litigación oral", "Redacción de recursos"],
        "soft_skills": ["Oratoria", "Negociación"],
    },
    {
        "titulo_cargo": "Piloto Comercial",
        "experiencia_minima_anos": 4,
        "perfil_general": "Operación de aeronaves comerciales en rutas de corto y medio radio.",
        "hard_skills": ["Airbus A320", "Navegación IFR"],
    },
    {
        "titulo_cargo": "Jardinero",
        "perfil_general": "Mantenimiento de zonas verdes y poda.",
        "hard_skills": ["Poda"],
    },
]


def afinidad(distancia: float) -> float:
    """Replica la normalización del motor: distancia coseno 0-2 a porcentaje 0-100."""
    return max(0.0, (1 - (distancia / 2.0)) * 100)


def correlacion(xs: list, ys: list) -> float:
    """Coeficiente de Pearson, sin dependencias externas."""
    n = len(xs)
    if n < 3:
        return float("nan")
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    return num / (dx * dy) if dx and dy else float("nan")


def medir(coleccion, criterio: str, total: int) -> list:
    """Devuelve las afinidades de los candidatos del banco frente a un criterio."""
    try:
        res = coleccion.query(
            query_texts=[criterio], n_results=min(total, MAX_RESULTADOS),
            where={"tipo_registro": "candidato"}, include=["metadatas", "distances"]
        )
    except Exception:
        res = coleccion.query(
            query_texts=[criterio], n_results=min(total, MAX_RESULTADOS),
            include=["metadatas", "distances"]
        )

    if not res.get("ids") or not res["ids"][0]:
        return []

    # Un registro por postulación en la bolsa global: nos quedamos con el mejor
    # por identidad para no contar dos veces a la misma persona.
    mejor = {}
    for m, d in zip(res["metadatas"][0], res["distances"][0]):
        if not m or m.get("tipo_registro") == "perfil_vacante":
            continue
        clave = str(m.get("correo_electronico") or m.get("nombre_completo") or "?").lower().strip()
        if clave not in mejor or d < mejor[clave]:
            mejor[clave] = d
    return [afinidad(d) for d in mejor.values()]


def criterios_reales(cliente, ef) -> list:
    """Compone el criterio de cada vacante realmente registrada."""
    salida = []
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
            salida.append((col.name, criterio))
    return salida


def main() -> None:
    cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    ef = embedding_functions.OllamaEmbeddingFunction(
        url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL
    )
    banco = cliente.get_collection(name=COLECCION_GLOBAL, embedding_function=ef)
    try:
        total = banco.count()
    except Exception:
        total = MAX_RESULTADOS

    filas = []

    for nombre, criterio in criterios_reales(cliente, ef):
        vals = medir(banco, criterio, total)
        if vals:
            filas.append(("REAL ", nombre, len(criterio), vals))

    for vacante in VACANTES_AJENAS:
        criterio = CVSearchEngine._componer_requisitos(vacante, {})
        vals = medir(banco, criterio, total)
        if vals:
            filas.append(("AJENO", vacante["titulo_cargo"], len(criterio), vals))

    if not filas:
        print("No hay datos suficientes en el banco de talento.")
        return

    print("=" * 84)
    print("AFINIDAD DEL BANCO DE TALENTO FRENTE A CADA CRITERIO")
    print("=" * 84)
    print(f"  {'tipo':<7}{'criterio':<26}{'car.':>6}{'n':>5}{'media':>9}{'máx':>9}{'mín':>9}")
    print("  " + "-" * 78)
    for tipo, nombre, largo, vals in sorted(filas, key=lambda f: (f[0], -sum(f[3]) / len(f[3]))):
        media = sum(vals) / len(vals)
        print(f"  {tipo:<7}{nombre[:25]:<26}{largo:>6}{len(vals):>5}"
              f"{media:>9.2f}{max(vals):>9.2f}{min(vals):>9.2f}")

    reales = [f for f in filas if f[0].strip() == "REAL"]
    ajenos = [f for f in filas if f[0].strip() == "AJENO"]

    print("\n" + "=" * 84)
    print("VEREDICTO")
    print("=" * 84)

    if not reales or not ajenos:
        print("  Faltan criterios de uno de los dos tipos.")
        return

    media_real = sum(sum(f[3]) / len(f[3]) for f in reales) / len(reales)
    media_ajena = sum(sum(f[3]) / len(f[3]) for f in ajenos) / len(ajenos)
    peor_real = min(sum(f[3]) / len(f[3]) for f in reales)
    mejor_ajeno = max(sum(f[3]) / len(f[3]) for f in ajenos)
    brecha = peor_real - mejor_ajeno

    print(f"  Afinidad media con criterios REALES   {media_real:6.2f} %")
    print(f"  Afinidad media con criterios AJENOS   {media_ajena:6.2f} %")
    print(f"  Separación entre medias               {media_real - media_ajena:6.2f} puntos")
    print(f"\n  Peor criterio real  {peor_real:6.2f} %")
    print(f"  Mejor criterio ajeno {mejor_ajeno:6.2f} %")
    print(f"  Brecha (positiva = separan)          {brecha:6.2f} puntos")

    largos = [f[2] for f in filas]
    medias = [sum(f[3]) / len(f[3]) for f in filas]
    r = correlacion(largos, medias)
    print(f"\n  Correlación longitud del criterio / afinidad media   r = {r:.3f}")
    if r == r and abs(r) > 0.7:
        print("    Fuerte: la longitud del texto influye tanto o más que el contenido.")
        print("    Cualquier umbral absoluto sobre la afinidad es inestable por construcción.")

    print("\n  LECTURA")
    if brecha > 3:
        print("    H2 · La métrica DISCRIMINA. Los criterios ajenos caen de forma clara.")
        print("    El solapamiento entre postulantes y no postulantes refleja que el banco de")
        print("    talento es homogéneo, no un fallo del emparejamiento. La afinidad es válida")
        print("    para ordenar; lo que no es defendible es el umbral fijo sobre su escala.")
    elif brecha > 0:
        print("    Discriminación DÉBIL. Los criterios ajenos puntúan algo por debajo, pero el")
        print("    margen es demasiado estrecho para sostener una decisión automática.")
    else:
        print("    H1 · La métrica está SATURADA. Un criterio ajeno al dominio puntúa igual o")
        print("    mejor que las vacantes reales. La afinidad, tal como se calcula hoy, no")
        print("    distingue perfiles pertinentes: el hallazgo es del enfoque, no del umbral.")


if __name__ == "__main__":
    main()
