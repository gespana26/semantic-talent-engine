"""Compara la carpeta de trabajo con la de ejecucion y avisa de regresiones.

POR QUE EXISTE
--------------
El proyecto vive en dos carpetas: los cambios se escriben en la copia de trabajo
y la aplicacion se ejecuta desde otra. El 21/07/2026 una actualizacion del
repositorio sobrescribio nueve ficheros de la copia y revirtio en silencio dos
correcciones ya cerradas:

  * `core/auto_match.py` dejo de pasar la vacante a `search_candidates`, de modo
    que la alerta volvio a puntuar en una escala distinta de la del buscador.
  * `models/ai_provider.py` dejo de heredar `BaseLLMProvider` y perdio
    `complete_json`, con lo que el traductor de consultas quedaba roto.

Nada fallo al arrancar y la suite de tests no lo detecto, porque los tests que
lo habrian cazado se saltan cuando los SDK no estan instalados. Este script hace
visible esa clase de perdida ANTES de ejecutar nada.

USO
---
    python scripts/verificar_sincronizacion.py
    python scripts/verificar_sincronizacion.py --otra "C:/ruta/a/la/otra/carpeta"

Solo lee. No copia, no borra y no modifica ningun fichero de ninguna de las dos
carpetas: decidir que se sincroniza es una decision humana.

Codigo de salida 1 si encuentra invariantes rotos, para poder encadenarlo.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
OTRA_POR_DEFECTO = RAIZ.parent / "semantic-talent-engine"

DIRECTORIOS_IGNORADOS = {
    "__pycache__", ".pytest_cache", ".git", ".TFM", "venv", ".venv",
    "storage", "node_modules",
}

# Invariantes: propiedades del codigo que costo trabajo establecer y que una
# sobrescritura puede deshacer sin que nada falle al importar. Cada entrada es
# (fichero, fragmento que DEBE aparecer, que se pierde si no aparece).
INVARIANTES = [
    (
        "core/auto_match.py",
        "vacante=vacante",
        "La alerta no pasa la vacante al buscador: vuelve a puntuar en otra escala.",
    ),
    (
        "core/auto_match.py",
        '"desglose"',
        "El veredicto no lleva el desglose: la decision deja de ser auditable.",
    ),
    (
        "models/ai_provider.py",
        "class OpenAIProvider(BaseLLMProvider)",
        "OpenAIProvider no hereda el contrato: vuelve el duck typing.",
    ),
    (
        "models/ai_provider.py",
        "class LocalOllamaProvider(BaseLLMProvider)",
        "LocalOllamaProvider no hereda el contrato: vuelve el duck typing.",
    ),
    (
        "models/ai_provider.py",
        "def complete_json",
        "Sin complete_json el QueryTranslator falla en tiempo de ejecucion.",
    ),
    (
        "core/database.py",
        "Nivel Académico:",  # se comprueba por separado la ausencia del nombre
        "El documento vectorizado perdio su estructura de etiquetas.",
    ),
    (
        "core/search_engine.py",
        "self.collection_name == self.COLECCION_GLOBAL",
        "El corte de pertinencia vuelve a leer el nombre del objeto de ChromaDB.",
    ),
    (
        "core/data_hygiene.py",
        "def normalizar_texto",
        "La busqueda por nombre pierde la normalizacion de acentos y mayusculas.",
    ),
]

# Fragmentos que NO deben reaparecer: correcciones que consistieron en quitar algo.
PROHIBIDOS = [
    (
        "core/database.py",
        "Candidato: {nombre_final}",
        "El nombre vuelve al documento vectorizado: §2.4.2 pasa a ser falsa.",
    ),
    (
        "core/baseline.py",
        "Candidato: Perfil de referencia",
        "Los perfiles de referencia no siguen el formato del documento real.",
    ),
    (
        # Solo la comparacion viva. Los comentarios que explican por que se
        # elimino el umbral mencionan el 1.2 a proposito y deben conservarse.
        "core/search_engine.py",
        "> 1.2",
        "Reaparece el umbral de distancia 1.2, que exigia coseno negativo.",
    ),
    (
        "core/auto_match.py",
        "2 * (1 - afinidad / 100.0)",
        "Se reconstruye la distancia invirtiendo la formula antigua.",
    ),
]


def _ficheros_py(raiz: Path) -> dict:
    """Ruta relativa -> hash del contenido, ignorando lo que no es fuente.

    Se poda durante el recorrido y no despues: un entorno virtual tiene decenas
    de miles de ficheros y recorrerlo entero para descartarlo tarda minutos.
    """
    encontrados = {}
    for carpeta, subcarpetas, ficheros in os.walk(raiz):
        subcarpetas[:] = [d for d in subcarpetas if d not in DIRECTORIOS_IGNORADOS]
        for nombre in ficheros:
            if not nombre.endswith(".py"):
                continue
            ruta = Path(carpeta) / nombre
            try:
                datos = ruta.read_bytes()
            except OSError:
                continue
            # Los finales de linea se normalizan: CRLF frente a LF no es un cambio.
            datos = datos.replace(b"\r\n", b"\n")
            clave = ruta.relative_to(raiz).as_posix()
            encontrados[clave] = hashlib.sha1(datos).hexdigest()
    return encontrados


def _revisar_invariantes(raiz: Path) -> list:
    problemas = []
    for fichero, fragmento, consecuencia in INVARIANTES:
        ruta = raiz / fichero
        if not ruta.exists():
            problemas.append(f"FALTA EL FICHERO  {fichero} — {consecuencia}")
            continue
        if fragmento not in ruta.read_text(encoding="utf-8", errors="ignore"):
            problemas.append(f"INVARIANTE ROTO   {fichero}: no aparece "
                             f"'{fragmento}'\n                  → {consecuencia}")
    for fichero, fragmento, consecuencia in PROHIBIDOS:
        ruta = raiz / fichero
        if not ruta.exists():
            continue
        if fragmento in ruta.read_text(encoding="utf-8", errors="ignore"):
            problemas.append(f"REGRESION         {fichero}: reaparece "
                             f"'{fragmento}'\n                  → {consecuencia}")
    return problemas


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--otra", default=str(OTRA_POR_DEFECTO),
                        help="Carpeta con la que comparar (la de ejecucion).")
    args = parser.parse_args()

    otra = Path(args.otra)
    print(f"Trabajo   : {RAIZ}")
    print(f"Ejecucion : {otra}")
    print()

    print("=" * 78)
    print("1. INVARIANTES DE LA CARPETA DE TRABAJO")
    print("=" * 78)
    problemas = _revisar_invariantes(RAIZ)
    if problemas:
        for p in problemas:
            print(f"  ✗ {p}")
    else:
        print("  ✓ Los invariantes se mantienen.")
    print()

    if not otra.exists():
        print(f"(No se encuentra {otra}: se omite la comparacion entre carpetas.)")
        return 1 if problemas else 0

    aqui = _ficheros_py(RAIZ)
    alla = _ficheros_py(otra)

    solo_trabajo = sorted(set(aqui) - set(alla))
    solo_ejecucion = sorted(set(alla) - set(aqui))
    distintos = sorted(f for f in set(aqui) & set(alla) if aqui[f] != alla[f])

    print("=" * 78)
    print("2. COMPARACION")
    print("=" * 78)
    print(f"\n  SOLO EN TRABAJO ({len(solo_trabajo)}) — pendiente de subir al repositorio:")
    for f in solo_trabajo:
        print(f"    + {f}")
    print(f"\n  SOLO EN EJECUCION ({len(solo_ejecucion)}) — se perderia con un espejo:")
    for f in solo_ejecucion:
        print(f"    - {f}")
    print(f"\n  DISTINTOS ({len(distintos)}):")
    for f in distintos:
        print(f"    ≠ {f}")

    print()
    print("=" * 78)
    print("3. INVARIANTES DE LA CARPETA DE EJECUCION")
    print("=" * 78)
    problemas_otra = _revisar_invariantes(otra)
    if problemas_otra:
        for p in problemas_otra:
            print(f"  ✗ {p}")
    else:
        print("  ✓ Los invariantes se mantienen.")

    print()
    print("Recordatorio: sincronizar sin espejo (robocopy sin /MIR) para no borrar")
    print("lo que solo existe en destino, y limpiar la base vectorial despues.")

    return 1 if (problemas or problemas_otra) else 0


if __name__ == "__main__":
    sys.exit(main())
