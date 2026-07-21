"""Diagnostica la duplicación de identidades en la base vectorial.

QUÉ SE ESTÁ COMPROBANDO
-----------------------
`store_candidate` genera un `uuid4()` nuevo en cada postulación, de modo que el
`upsert` siempre inserta y nunca actualiza. En los silos ese comportamiento se
quiere: un registro por postulación a esa vacante. En la bolsa global no, porque
ahí la unidad es la persona.

De ahí se derivan tres consecuencias que este script cuantifica:

1. **Consumo de recall.** La recuperación pide 50 vecinos. Cada registro
   duplicado ocupa uno de esos puestos, así que una persona con diez
   postulaciones se lleva diez. Los duplicados se descartan *después*, de modo
   que el coste ya se pagó: la duplicación no ensucia los resultados, se come la
   ventana.

2. **Lotería sobre la nota.** La deduplicación ocurre antes del re-puntuado y
   conserva el registro más próximo por vector. Como la afinidad se calcula
   sobre el `raw_json` de ese registro, si las extracciones de una misma persona
   difieren entre postulaciones, **el dedup no decide qué fila se muestra sino
   cuánto puntúa el candidato**. Este script comprueba si difieren de hecho.

3. **Identidades vacías.** Un registro sin correo comparte la clave "" con todos
   los demás sin correo, de modo que solo sobrevive el primero.

CUÁNDO EJECUTARLO
-----------------
Antes de limpiar la base. Si se vacía y se vuelven a correr los casos de uso con
el código actual, se reproduce el mismo patrón: la corrección debe entrar antes.

USO
---
    python scripts/diagnostico_duplicados.py

Solo lee: no escribe, no modifica y no borra nada.
"""

import json
import sys
from collections import defaultdict

import chromadb

sys.path.insert(0, ".")
from config import settings  # noqa: E402

COLECCION_GLOBAL = "talento-global-empresa"
VENTANA_RECUPERACION = 50


def identidad(meta: dict) -> str:
    """Clave con la que el motor deduplica hoy: el correo, en minúsculas."""
    return str(meta.get("correo_electronico") or "").lower().strip()


def firma_extraccion(meta: dict) -> tuple:
    """Resume la riqueza de una extracción para poder comparar duplicados entre sí."""
    try:
        datos = json.loads(meta.get("raw_json") or "{}")
    except (ValueError, TypeError):
        datos = {}
    return (
        len(datos.get("hard_skills") or []),
        len(datos.get("soft_skills") or []),
        len(datos.get("historial_laboral") or []),
        len(datos.get("educacion_detalle") or []),
        str(datos.get("nivel_academico_maximo") or ""),
        int(datos.get("anios_experiencia_total") or 0),
    )


def analizar(coleccion, es_global: bool) -> dict:
    contenido = coleccion.get(include=["metadatas"])
    metadatos = contenido.get("metadatas") or []
    ids = contenido.get("ids") or []

    registros = 0
    sin_correo = 0
    por_identidad = defaultdict(list)

    for id_registro, meta in zip(ids, metadatos):
        if not meta or meta.get("tipo_registro") == "perfil_vacante":
            continue
        registros += 1
        clave = identidad(meta)
        if not clave:
            sin_correo += 1
            clave = f"(sin correo) {id_registro}"
        por_identidad[clave].append((id_registro, meta))

    duplicados = {k: v for k, v in por_identidad.items() if len(v) > 1}

    # ¿Las extracciones de una misma persona son distintas entre sí?
    discrepantes = {}
    for clave, entradas in duplicados.items():
        firmas = {firma_extraccion(m) for _, m in entradas}
        if len(firmas) > 1:
            discrepantes[clave] = firmas

    return {
        "nombre": coleccion.name, "es_global": es_global, "registros": registros,
        "identidades": len(por_identidad), "sin_correo": sin_correo,
        "duplicados": duplicados, "discrepantes": discrepantes,
    }


def main() -> None:
    cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)

    informes = []
    for col in cliente.list_collections():
        try:
            informes.append(analizar(col, col.name == COLECCION_GLOBAL))
        except Exception as e:
            print(f"[{col.name}] No se pudo analizar: {e}")

    if not informes:
        print("No hay colecciones.")
        return

    print("=" * 82)
    print("1. REGISTROS FRENTE A IDENTIDADES")
    print("=" * 82)
    print(f"  {'colección':<28}{'registros':>11}{'identidades':>13}{'duplicación':>13}{'sin correo':>12}")
    print("  " + "-" * 78)

    for inf in sorted(informes, key=lambda i: (not i["es_global"], i["nombre"])):
        factor = inf["registros"] / inf["identidades"] if inf["identidades"] else 0
        marca = "  <- bolsa global" if inf["es_global"] else ""
        print(f"  {inf['nombre'][:27]:<28}{inf['registros']:>11}{inf['identidades']:>13}"
              f"{factor:>12.2f}x{inf['sin_correo']:>12}{marca}")

    glob = next((i for i in informes if i["es_global"]), None)

    # =====================================================================
    print("\n" + "=" * 82)
    print("2. CONSUMO DE LA VENTANA DE RECUPERACIÓN (bolsa global)")
    print("=" * 82)

    if not glob:
        print("  No se encontró la bolsa global.")
    elif not glob["duplicados"]:
        print("  ✅ No hay duplicados: cada persona ocupa un solo puesto.")
        print("     El punto ciego 11 es teórico con los datos actuales y no urge.")
    else:
        extra = glob["registros"] - glob["identidades"]
        pct = 100.0 * extra / glob["registros"] if glob["registros"] else 0
        print(f"  Registros redundantes: {extra} de {glob['registros']} ({pct:.0f} %)")
        print(f"  De cada {VENTANA_RECUPERACION} vecinos recuperados, unos "
              f"{VENTANA_RECUPERACION * pct / 100:.0f} se gastan en duplicados.\n")
        print(f"  {'identidad':<38}{'registros':>11}")
        print("  " + "-" * 50)
        for clave, entradas in sorted(glob["duplicados"].items(),
                                      key=lambda kv: -len(kv[1]))[:15]:
            print(f"  {clave[:37]:<38}{len(entradas):>11}")

    # =====================================================================
    print("\n" + "=" * 82)
    print("3. ¿DECIDE EL DEDUP LA NOTA DEL CANDIDATO?")
    print("=" * 82)
    print("  Si las extracciones de una misma persona difieren, el registro que")
    print("  sobrevive al dedup determina su afinidad.\n")

    hay_discrepancia = False
    for inf in informes:
        if not inf["discrepantes"]:
            continue
        hay_discrepancia = True
        print(f"  [{inf['nombre']}]")
        for clave, firmas in list(inf["discrepantes"].items())[:10]:
            print(f"    {clave[:40]}")
            for f in sorted(firmas):
                print(f"       hard={f[0]:<3} soft={f[1]:<3} historial={f[2]:<3} "
                      f"educación={f[3]:<3} años={f[5]:<3} nivel='{f[4][:28]}'")
        print()

    if not hay_discrepancia:
        print("  ✅ Todas las copias de una misma persona tienen la misma extracción.")
        print("     El dedup elige entre registros equivalentes: no altera la nota.")
    else:
        print("  ⚠️  Hay personas cuyas copias difieren en contenido extraído. El registro")
        print("      conservado cambia la cobertura de requisitos y, por tanto, la afinidad.")

    # =====================================================================
    print("\n" + "=" * 82)
    print("VEREDICTO")
    print("=" * 82)

    sin_correo_total = sum(i["sin_correo"] for i in informes)
    if glob and glob["duplicados"]:
        print("  · Punto ciego 11 ACTIVO. Conviene el identificador determinista por correo")
        print("    en la bolsa global antes de la prueba final de casos de uso.")
    else:
        print("  · Punto ciego 11 sin efecto observable en los datos actuales.")

    if sin_correo_total:
        print(f"  · Punto ciego 7: {sin_correo_total} registro(s) sin correo. Colapsarían")
        print("    bajo una misma clave vacía. Son datos anteriores al paso de confirmación.")
    else:
        print("  · Punto ciego 7 sin registros afectados: todos tienen correo.")

    print("\n  Recordatorio de orden: corregir el código ANTES de limpiar la base. Vaciarla")
    print("  y repetir los casos de uso con el código actual reproduce el mismo patrón.")


if __name__ == "__main__":
    main()
