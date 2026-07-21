"""Mide si el modelo de embeddings alinea español e inglés, y qué le cuesta a un CV en inglés.

LAS TRES PREGUNTAS
------------------
1. **¿Alinea idiomas?** La memoria reclama capacidad cross-lingual y habla de
   "embeddings multilingües". `nomic-embed-text` en Ollama es la v1.5, entrenada
   principalmente en inglés, de modo que su alineación entre idiomas no está
   garantizada. Si no alinea, esa afirmación de §8.2 es incorrecta y la capacidad
   bilingüe real del sistema procede de otro sitio: del `$or` con variantes en
   ambos idiomas que genera el `QueryTranslator`, que es una estrategia de prompt
   y no de embedding.

2. **¿Penaliza el corte por línea base a quien escribe en inglés?** El corte
   propuesto descarta a quien no esté más cerca que un perfil de referencia
   ajeno, y esos perfiles están todos en español. Si un CV pertinente en inglés
   queda más lejos que un jardinero en español, el sistema lo descartaría **por
   su idioma**, no por su perfil. Sería un sesgo directo.

3. **¿Se corrige incluyendo referencias en inglés?** Se recalcula el corte con
   una línea base bilingüe para ver si el problema desaparece.

CÓMO ESTÁ CONSTRUIDO
--------------------
Los pares bilingües son textos controlados y equivalentes entre sí, escritos con
la misma estructura que los documentos del sistema. Se miden contra los criterios
REALES de las vacantes registradas, de modo que el resultado no depende de un
corpus inventado.

USO
---
    python scripts/medir_cross_lingual.py

Requiere Ollama. Solo lee: no escribe, no modifica y no toca la base de datos.
"""

import json
import sys

import chromadb
from chromadb.utils import embedding_functions

sys.path.insert(0, ".")
from config import settings  # noqa: E402
from core import baseline  # noqa: E402
from core.search_engine import CVSearchEngine  # noqa: E402

COLECCION_GLOBAL = "talento-global-empresa"
ID_VACANTE = "VACANTE_PRINCIPAL"


def _perfil(nivel, anios, resumen, tecnicas, blandas):
    """Compone un documento con la misma forma que usa el sistema.

    Sin línea de nombre, como el documento real: la identidad vive en los
    metadatos y no entra en el embedding. Aquí importa además por otra razón —
    un nombre traducido ("Perfil de prueba" / "Test profile") habría metido
    señal de idioma en el propio texto, que es justo la variable que se mide.
    """
    return (f"Nivel Académico: {nivel}\n"
            f"Años de Experiencia Total: {anios}\nPerfil Profesional: {resumen}\n"
            f"Habilidades Técnicas: {tecnicas}\nCompetencias Blandas: {blandas}")


# Pares equivalentes: mismo contenido, distinto idioma. La única variable es el
# idioma, de modo que la distancia dentro de un par mide exclusivamente eso.
PARES = [
    ("Analista de datos", "PERTINENTE",
     _perfil("Ingeniería de Sistemas", 6,
             "Análisis de grandes volúmenes de datos para identificar y mitigar riesgos "
             "financieros y operativos en el sector financiero.",
             "Bases de datos, Ciencia de datos, Modelos predictivos, SQL",
             "Habilidades analíticas, Comunicación"),
     _perfil("Systems Engineering", 6,
             "Analysis of large data volumes to identify and mitigate financial and "
             "operational risks in the financial sector.",
             "Databases, Data science, Predictive models, SQL",
             "Analytical skills, Communication")),

    ("Jefe de proyecto", "PERTINENTE",
     _perfil("Ingeniería Industrial", 8,
             "Liderar y gestionar proyectos tecnológicos, levantando requerimientos "
             "funcionales del cliente interno bajo metodologías ágiles.",
             "Metodologías ágiles, Scrum, Gestión de proyectos, Jira",
             "Liderazgo, Negociación"),
     _perfil("Industrial Engineering", 8,
             "Lead and manage technology projects, gathering functional requirements "
             "from internal stakeholders under agile methodologies.",
             "Agile methodologies, Scrum, Project management, Jira",
             "Leadership, Negotiation")),

    ("Desarrollador", "PERTINENTE",
     _perfil("Ingeniería de Software", 5,
             "Desarrollo de servicios backend y automatización de procesos.",
             "Python, Django, PostgreSQL, Docker",
             "Trabajo en equipo, Autonomía"),
     _perfil("Software Engineering", 5,
             "Backend service development and process automation.",
             "Python, Django, PostgreSQL, Docker",
             "Teamwork, Autonomy")),

    ("Cocina", "AJENO",
     _perfil("Escuela de Hostelería", 8,
             "Jefe de cocina en restaurante de menú diario, elaboración de platos y "
             "control de aprovisionamiento.",
             "Cocina mediterránea, Repostería, Emplatado",
             "Trabajo bajo presión"),
     _perfil("Culinary School", 8,
             "Head chef at a daily-menu restaurant, dish preparation and supply control.",
             "Mediterranean cuisine, Pastry, Plating",
             "Working under pressure")),

    ("Enfermería", "AJENO",
     _perfil("Grado en Enfermería", 10,
             "Atención a pacientes en planta de hospitalización, administración de "
             "medicación y curas.",
             "Canalización de vías, Triaje, Soporte vital",
             "Empatía"),
     _perfil("Nursing Degree", 10,
             "Patient care on the hospital ward, medication administration and wound care.",
             "IV cannulation, Triage, Life support",
             "Empathy")),
]


def coseno(a, b) -> float:
    return baseline.coseno(a, b)


def criterios_reales(cliente) -> list:
    """Recupera el criterio de requisitos de cada vacante registrada."""
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

    criterios = criterios_reales(cliente)
    if not criterios:
        print("No hay vacantes registradas: el bloque 2 no podrá ejecutarse.")

    es = [p[2] for p in PARES]
    en = [p[3] for p in PARES]
    crit = [c for _, c in criterios]

    vectores = ef(es + en + crit)
    v_es = vectores[:len(es)]
    v_en = vectores[len(es):len(es) + len(en)]
    v_crit = vectores[len(es) + len(en):]

    # =====================================================================
    print("=" * 84)
    print("1. ¿ALINEA EL MODELO ESPAÑOL E INGLÉS?")
    print("=" * 84)
    print(f"   Modelo: {settings.EMBEDDING_MODEL}\n")
    print("   Distancia dentro de cada par equivalente (mismo contenido, distinto idioma).")
    print("   Si el modelo alinea idiomas debe ser pequeña.\n")
    print(f"   {'tema':<22}{'tipo':<14}{'distancia ES-EN':>18}")
    print("   " + "-" * 54)

    intra = []
    for (tema, tipo, _, _), a, b in zip(PARES, v_es, v_en):
        d = 1 - coseno(a, b)
        intra.append(d)
        print(f"   {tema:<22}{tipo:<14}{d:>18.4f}")

    # Control: mismo idioma, temas distintos. Es la referencia contra la que
    # juzgar si la distancia entre idiomas es grande o pequeña.
    cruzadas = []
    for i in range(len(PARES)):
        for j in range(len(PARES)):
            if i != j:
                cruzadas.append(1 - coseno(v_es[i], v_en[j]))

    media_intra = sum(intra) / len(intra)
    media_cruz = sum(cruzadas) / len(cruzadas)
    print("   " + "-" * 54)
    print(f"   {'MEDIA equivalentes (ES↔EN)':<36}{media_intra:>18.4f}")
    print(f"   {'MEDIA temas distintos (control)':<36}{media_cruz:>18.4f}")
    print(f"   {'Separación':<36}{media_cruz - media_intra:>18.4f}")

    print("\n   LECTURA")
    if media_intra < 0.20 and (media_cruz - media_intra) > 0.10:
        print("     ✅ ALINEA. Un mismo contenido en dos idiomas queda muy próximo y")
        print("        claramente más cerca que un contenido distinto. La afirmación de")
        print("        §8.2 sobre embeddings multilingües se sostiene.")
    elif (media_cruz - media_intra) > 0.03:
        print("     🟡 ALINEA DÉBILMENTE. Hay señal cross-lingual, pero el margen es")
        print("        estrecho: el idioma pesa tanto como el contenido. Conviene matizar")
        print("        la afirmación de §8.2 en lugar de sostenerla tal cual.")
    else:
        print("     ❌ NO ALINEA. El idioma domina sobre el contenido: dos textos")
        print("        equivalentes en idiomas distintos no quedan más cerca que dos")
        print("        textos de temas diferentes. 'Embeddings multilingües' sería")
        print("        incorrecto; la capacidad bilingüe real está en el $or que genera")
        print("        el QueryTranslator, que es estrategia de prompt.")

    if not criterios:
        return

    # =====================================================================
    print("\n" + "=" * 84)
    print("2. ¿PENALIZA EL CORTE POR LÍNEA BASE A QUIEN ESCRIBE EN INGLÉS?")
    print("=" * 84)
    print("   Para cada vacante real se compara el mejor CV PERTINENTE en cada idioma")
    print("   contra la línea base actual, que se calcula solo con referencias en español.\n")
    print(f"   {'vacante':<22}{'base ES':>9}{'pert. ES':>10}{'pert. EN':>10}"
          f"{'norm ES':>9}{'norm EN':>9}{'¿descarta EN?':>15}")
    print("   " + "-" * 84)

    idx_pertinentes = [i for i, p in enumerate(PARES) if p[1] == "PERTINENTE"]
    descartes = 0

    for (nombre, criterio), vc in zip(criterios, v_crit):
        base_es = baseline.calcular_linea_base(criterio, ef)

        sim_es = max(coseno(vc, v_es[i]) for i in idx_pertinentes)
        sim_en = max(coseno(vc, v_en[i]) for i in idx_pertinentes)
        norm_es = baseline.normalizar_similitud(sim_es, base_es) * 100
        norm_en = baseline.normalizar_similitud(sim_en, base_es) * 100

        descarta = norm_en <= 0 < norm_es
        if descarta:
            descartes += 1
        marca = "⚠️  SÍ" if descarta else "no"
        print(f"   {nombre[:21]:<22}{base_es:>9.4f}{sim_es:>10.4f}{sim_en:>10.4f}"
              f"{norm_es:>8.1f}%{norm_en:>8.1f}%{marca:>15}")

    print("   " + "-" * 84)
    if descartes:
        print(f"   ⚠️  En {descartes} de {len(criterios)} vacantes, un CV pertinente en inglés")
        print("       quedaría descartado mientras su equivalente en español pasa.")
        print("       Es un sesgo por idioma y hay que corregirlo antes de activar el corte.")
    else:
        print("   ✅ Ninguna vacante descarta el CV en inglés que sí admite en español.")

    # =====================================================================
    print("\n" + "=" * 84)
    print("3. ¿SE CORRIGE CON UNA LÍNEA BASE BILINGÜE?")
    print("=" * 84)
    print("   Se recalcula el corte usando también referencias ajenas en inglés, para")
    print("   que la línea base deje de premiar la coincidencia de idioma.\n")

    idx_ajenos = [i for i, p in enumerate(PARES) if p[1] == "AJENO"]
    print(f"   {'vacante':<22}{'base ES':>10}{'base bilingüe':>15}{'norm EN antes':>15}{'después':>10}")
    print("   " + "-" * 72)

    for (nombre, criterio), vc in zip(criterios, v_crit):
        base_es = baseline.calcular_linea_base(criterio, ef)
        # Línea base bilingüe: el ajeno más próximo, mire en el idioma que mire.
        base_bi = max(
            [coseno(vc, v_es[i]) for i in idx_ajenos] + [coseno(vc, v_en[i]) for i in idx_ajenos]
        )
        base_bi = max(base_bi, base_es)

        sim_en = max(coseno(vc, v_en[i]) for i in idx_pertinentes)
        antes = baseline.normalizar_similitud(sim_en, base_es) * 100
        despues = baseline.normalizar_similitud(sim_en, base_bi) * 100
        print(f"   {nombre[:21]:<22}{base_es:>10.4f}{base_bi:>15.4f}"
              f"{antes:>14.1f}%{despues:>9.1f}%")

    print("\n   Si la columna 'después' sube por encima de cero donde antes estaba en cero,")
    print("   basta con añadir los perfiles de referencia en inglés a core/baseline.py.")
    print("   Si sigue en cero, el problema no es la línea base sino el propio modelo, y")
    print("   la solución pasa por uno multilingüe (nomic-embed-text-v2-moe, bge-m3).")


if __name__ == "__main__":
    main()
