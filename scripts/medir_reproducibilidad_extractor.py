"""Caracteriza la variabilidad del extractor multimodal entre ejecuciones.

QUE MIDE Y POR QUE
------------------
El extractor convierte un PDF en una estructura de datos mediante un modelo
generativo. Un modelo generativo con temperatura distinta de cero no es una
funcion: el mismo documento puede producir estructuras distintas en ejecuciones
sucesivas. Mientras esa variabilidad no se acote, ninguna comparacion entre dos
ejecuciones del sistema es interpretable, porque una diferencia observada puede
proceder del cambio que se queria evaluar o del propio muestreo del modelo.

Este script procesa N veces el mismo documento y compara las estructuras
obtenidas campo a campo. Reporta que campos divergen, cuantos valores distintos
produjo cada uno y cual es el impacto de esa divergencia sobre la afinidad
final, que es lo que decide si un candidato aparece o no ante el reclutador.

COMO LEER EL RESULTADO
----------------------
Hay tres veredictos posibles, porque no todos los campos pesan igual:

  DETERMINISTA
      Las N ejecuciones son identicas en los diez campos del esquema.

  DETERMINISTA EN LOS CAMPOS QUE DECIDEN
      Los campos que entran en el calculo de la afinidad y los que fijan la
      identidad del candidato coinciden; la variacion se limita a campos
      descriptivos, cuyo unico efecto llega por la componente de similitud.
      El sistema sigue siendo comparable entre ejecuciones.

  NO DETERMINISTA
      Varia algun campo que decide la puntuacion o la identidad. Mientras eso
      ocurra, dos mediciones del sistema no son comparables.

Fijar temperature=0 y una semilla constante es necesario, pero no siempre
suficiente: los proveedores en la nube documentan la semilla como
reproducibilidad de mejor esfuerzo, y la inferencia sobre GPU no es
reproducible bit a bit. De ahi que la reproducibilidad haya que verificarla y
no darla por supuesta a partir de la configuracion.

El impacto se calcula sobre `hard_skills` porque es el campo que alimenta la
cobertura de requisitos, que es la componente principal de la afinidad. Con el
peso por defecto, capturar una habilidad de mas o de menos sobre dos exigidas
desplaza el resultado 37,5 puntos porcentuales para el mismo documento.

Ademas de la variabilidad, el informe reporta la latencia media de extraccion
medida en la maquina, y vuelca los diez campos de una ejecucion para que puedan
cotejarse a mano contra el CV y obtener la tasa de campos correctamente
extraidos. Son las dos metricas de la seccion 5.1 que pueden medirse sin un
conjunto anotado; precision y recall del ranking si lo requieren.

USO
---
    python scripts/medir_reproducibilidad_extractor.py CV/mi_hoja_de_vida.pdf
    python scripts/medir_reproducibilidad_extractor.py CV/ejemplo.pdf --veces 6
    python scripts/medir_reproducibilidad_extractor.py CV/ejemplo.pdf --proveedor ollama

El parametro `--proveedor` permite repetir la misma medicion sobre el modelo
local y sobre el de la nube para compararlos, sin duplicar el experimento.

Requiere el proveedor de IA configurado en `.env` y operativo. Solo lee: no
escribe en la base vectorial ni indexa nada. Copia el PDF al almacenamiento
temporal de imagenes y lo limpia al terminar.
"""

from __future__ import annotations

import argparse
import re
import statistics
import sys
import time
from collections import Counter

sys.path.insert(0, ".")

from config import settings  # noqa: E402
from config.providers import get_ai_provider  # noqa: E402
from core.data_hygiene import normalizar_texto  # noqa: E402
from core.extractor import CVImageExtractor  # noqa: E402

# Campos comparados. Se separan por tipo porque no se comparan igual: una lista
# desordenada no debe contar como divergencia solo por el orden.
CAMPOS_TEXTO = [
    "nombre_completo", "correo_electronico", "telefono_movil",
    "ubicacion", "nivel_academico_maximo", "perfil_profesional",
]
CAMPOS_LISTA = ["educacion_detalle", "hard_skills", "soft_skills"]
CAMPOS_NUMERO = ["anios_experiencia_total"]

# Los campos no pesan lo mismo, y un veredicto que los trate por igual engaña en
# las dos direcciones. Se agrupan por la consecuencia que tiene su variacion:
#
#   PUNTUACION  entran en `calcular_afinidad`, sea en la cobertura de requisitos
#               (hard_skills y perfil_profesional), en el factor de profesion
#               (nivel academico y educacion) o en el de experiencia. Si estos
#               varian, dos ejecuciones del sistema no son comparables.
#   IDENTIDAD   determinan la clave de deduplicacion y el canal de la alerta. Su
#               variacion no altera la puntuacion, pero puede duplicar un
#               registro o desviar un correo.
#   DESCRIPTIVO solo llegan al texto que se vectoriza, de modo que su efecto se
#               limita a la componente de similitud, que pesa `PESO_SIMILITUD`.
GRUPOS = {
    "PUNTUACION": ["hard_skills", "perfil_profesional", "nivel_academico_maximo",
                   "educacion_detalle", "anios_experiencia_total"],
    "IDENTIDAD": ["nombre_completo", "correo_electronico", "telefono_movil"],
    "DESCRIPTIVO": ["soft_skills", "ubicacion"],
}


def _grupo(campo: str) -> str:
    for nombre, campos in GRUPOS.items():
        if campo in campos:
            return nombre
    return "DESCRIPTIVO"


# Signos que el modelo usa indistintamente para separar dos datos dentro de una
# misma cadena. "Administracion de Empresas, Universidad EAN" y la misma cadena
# con un guion son el mismo contenido escrito de dos maneras.
SEPARADORES = re.compile(r"[.,;:/|·\u2014\u2013-]+")


def _normalizar(valor, tipo: str):
    """Forma comparable conservando el formato: detecta cualquier diferencia."""
    if tipo == "lista":
        return tuple(sorted(str(x).strip().lower() for x in (valor or []) if str(x).strip()))
    if tipo == "numero":
        try:
            return round(float(valor or 0), 2)
        except (TypeError, ValueError):
            return 0.0
    return str(valor or "").strip().lower()


def _canonico(valor, tipo: str):
    """Forma comparable ignorando el formato: detecta solo diferencias de contenido.

    Compararlo todo en crudo sobreestima la variabilidad, porque cuenta como
    divergencia que el modelo escriba una lista con comas en una ejecucion y con
    guiones en otra. Comparar solo el contenido canonico la subestimaria si el
    formato importara. Se calculan las dos y se informa por separado: una
    divergencia que desaparece al canonizar es de redaccion, no de extraccion.
    """
    if tipo == "numero":
        return _normalizar(valor, tipo)

    def limpiar(x) -> str:
        t = normalizar_texto(x)
        return re.sub(r"\s+", " ", SEPARADORES.sub(" ", t)).strip()

    if tipo == "lista":
        return tuple(sorted(limpiar(x) for x in (valor or []) if str(x).strip()))
    return limpiar(valor)


def _punto_de_divergencia(valores) -> str:
    """Describe DONDE empiezan a diferir dos redacciones largas.

    Contar cuantos valores distintos hay no basta para juzgar la gravedad: no es
    lo mismo que el modelo cambie una coletilla final que que anada o suprima una
    competencia mencionada en el texto. Se localiza el prefijo comun y se muestra
    lo que viene despues en cada version.
    """
    textos = [v if isinstance(v, str) else " | ".join(v) for v in set(valores)]
    if len(textos) < 2:
        return ""
    corte = 0
    while corte < min(len(t) for t in textos) and len({t[corte] for t in textos}) == 1:
        corte += 1
    # Se retrocede hasta el ultimo espacio para no cortar una palabra por la mitad.
    prefijo = textos[0][:corte]
    if " " in prefijo:
        corte = prefijo.rindex(" ") + 1
    lineas = [f"     coinciden en los primeros {corte} caracteres; a partir de ahi:"]
    for t in sorted(textos):
        cola = t[corte:].strip() or "(fin del texto)"
        lineas.append(f"       …{cola[:120]}")
    return "\n".join(lineas)


def _extraer(proveedor, extractor, pdf_path: str) -> tuple:
    """Una ejecucion completa del extractor. Devuelve (estructura, segundos).

    El cronometro cubre solo la llamada al modelo, no la rasterizacion del PDF:
    lo que interesa medir es la latencia de inferencia, que es la que domina y la
    que cambia entre proveedor local y en la nube.
    """
    rutas = []
    try:
        rutas = extractor.pdf_to_images(pdf_path)
        inicio = time.perf_counter()
        estructura = proveedor.parse_cv_images_to_json(rutas)
        segundos = time.perf_counter() - inicio
        datos = estructura.model_dump() if hasattr(estructura, "model_dump") else dict(estructura)
        return datos, segundos
    finally:
        if rutas:
            extractor.clear_temp_images(rutas)


def _impacto_en_afinidad(conteo_habilidades: list) -> str:
    """Traduce la divergencia en habilidades a puntos de afinidad.

    La cobertura es la proporcion de requisitos cumplidos y pesa
    `PESO_COBERTURA`. Una habilidad de diferencia sobre una vacante que exige
    `n` mueve la cobertura en 1/n, y la afinidad en `PESO_COBERTURA / n`.
    """
    if not conteo_habilidades:
        return ""
    rango = max(conteo_habilidades) - min(conteo_habilidades)
    if rango == 0:
        return "   Sin divergencia en habilidades: la cobertura de requisitos no se ve afectada."
    lineas = ["   Impacto de esa divergencia sobre la afinidad final:"]
    for exigidas in (2, 3, 5):
        puntos = 100.0 * settings.PESO_COBERTURA * rango / exigidas
        lineas.append(f"     · vacante con {exigidas} requisitos exigidos → hasta {puntos:.1f} puntos")
    return "\n".join(lineas)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", help="Ruta al PDF que se procesara repetidamente.")
    parser.add_argument("--veces", type=int, default=4, help="Numero de ejecuciones (por defecto 4).")
    parser.add_argument("--proveedor", default=None, choices=["openai", "ollama"],
                        help="Fuerza el proveedor. Por defecto, el configurado en el entorno.")
    args = parser.parse_args()
    proveedor_usado = args.proveedor or settings.AI_PROVIDER_TYPE

    print("=" * 78)
    print("REPRODUCIBILIDAD DEL EXTRACTOR MULTIMODAL")
    print("=" * 78)
    print(f"   Documento : {args.pdf}")
    print(f"   Ejecuciones: {args.veces}")
    print(f"   Proveedor : {proveedor_usado}")
    print(f"   Semilla   : {settings.RANDOM_SEED}\n")

    proveedor = get_ai_provider(args.proveedor)
    extractor = CVImageExtractor()

    resultados = []
    latencias = []
    for i in range(args.veces):
        print(f"   Ejecucion {i + 1}/{args.veces}…", flush=True)
        try:
            datos, segundos = _extraer(proveedor, extractor, args.pdf)
            resultados.append(datos)
            latencias.append(segundos)
            print(f"      {segundos:.1f} s", flush=True)
        except Exception as e:
            print(f"\n   La ejecucion {i + 1} fallo: {e}")
            return 2

    print()
    print("-" * 78)
    print("COMPARACION CAMPO A CAMPO")
    print("-" * 78)
    print(f"   {'campo':<26}{'grupo':>12}{'crudo':>7}{'canonico':>10}{'estado':>18}")
    print("   " + "-" * 73)

    divergentes = []
    solo_formato = []
    conteo_habilidades = []
    for campo, tipo in ([(c, "texto") for c in CAMPOS_TEXTO]
                        + [(c, "lista") for c in CAMPOS_LISTA]
                        + [(c, "numero") for c in CAMPOS_NUMERO]):
        valores = [_normalizar(r.get(campo), tipo) for r in resultados]
        canonicos = [_canonico(r.get(campo), tipo) for r in resultados]
        n_crudo, n_canon = len(set(valores)), len(set(canonicos))

        if n_canon > 1:
            estado = "DIVERGE contenido"
            divergentes.append((campo, canonicos, _grupo(campo)))
        elif n_crudo > 1:
            estado = "solo formato"
            solo_formato.append((campo, valores))
        else:
            estado = "estable"

        if campo == "hard_skills":
            conteo_habilidades = [len(v) for v in canonicos]
        print(f"   {campo:<26}{_grupo(campo):>12}{n_crudo:>7}{n_canon:>10}{estado:>18}")

    # --- Latencia de extraccion (medida en esta maquina) ---
    if latencias:
        print()
        print("-" * 78)
        print("LATENCIA DE EXTRACCION (esta maquina, este proveedor)")
        print("-" * 78)
        media = statistics.mean(latencias)
        print(f"   por ejecucion: {[f'{x:.1f}' for x in latencias]} s")
        print(f"   media {media:.1f} s · minimo {min(latencias):.1f} s · maximo {max(latencias):.1f} s")

    # --- Volcado de una extraccion para cotejar la tasa de campos correctos ---
    print()
    print("-" * 78)
    print("EXTRACCION DE REFERENCIA (ejecucion 1) — para cotejar contra el CV")
    print("-" * 78)
    print("   Marca cada campo como correcto o no comparandolo con el documento;")
    print("   la tasa de campos correctamente extraidos es (correctos / 10).")
    ref = resultados[0]
    for campo in CAMPOS_TEXTO + CAMPOS_LISTA + CAMPOS_NUMERO:
        valor = ref.get(campo)
        if isinstance(valor, list):
            valor = ", ".join(str(x) for x in valor) if valor else "(vacio)"
        texto = str(valor) if str(valor).strip() else "(vacio)"
        print(f"   [ ] {campo:<26} {texto[:110]}")

    print()
    if conteo_habilidades:
        print(f"   Habilidades tecnicas reconocidas por ejecucion: {conteo_habilidades}")
        if len(set(conteo_habilidades)) > 1:
            print(f"   media {statistics.mean(conteo_habilidades):.2f} · "
                  f"minimo {min(conteo_habilidades)} · maximo {max(conteo_habilidades)}")
        print(_impacto_en_afinidad(conteo_habilidades))
        print()

    criticos = [d for d in divergentes if d[2] in ("PUNTUACION", "IDENTIDAD")]

    print("=" * 78)
    if not divergentes:
        print("VEREDICTO: DETERMINISTA")
        print("=" * 78)
        print(f"   Las {args.veces} ejecuciones produjeron estructuras identicas en todos los")
        print("   campos comparados. El pipeline de extraccion es reproducible: una diferencia")
        print("   entre dos ejecuciones del sistema puede atribuirse al cambio evaluado y no")
        print("   al muestreo del modelo.")
        return 0

    if not criticos:
        print("VEREDICTO: DETERMINISTA EN LOS CAMPOS QUE DECIDEN")
        print("=" * 78)
        print("   Los campos que entran en el calculo de la afinidad y los que determinan la")
        print(f"   identidad del candidato son identicos en las {args.veces} ejecuciones. La")
        print("   variabilidad residual se limita a campos descriptivos, cuyo unico efecto es")
        print(f"   sobre la componente de similitud, con peso {settings.PESO_SIMILITUD}.")
        print("   El sistema es comparable entre ejecuciones: la puntuacion no se mueve.")
    else:
        print("VEREDICTO: NO DETERMINISTA")
        print("=" * 78)
        print(f"   {len(criticos)} campo(s) que afectan a la puntuacion o a la identidad divergen")
        print("   entre ejecuciones del mismo documento. Mientras esto ocurra, dos mediciones")
        print("   del sistema no son comparables.")
        print("   Revisar que todas las llamadas de extraccion fijen temperature=0 y seed.")

    if solo_formato:
        print()
        print("   Divergencias de redaccion (mismo contenido, distinta escritura).")
        print("   No afectan al calculo: los comparadores del sistema normalizan el texto.")
        for campo, valores in solo_formato:
            print(f"     {campo}: {len(set(valores))} redacciones distintas")

    print()
    for campo, valores, grupo in divergentes:
        print(f"   {campo}  [{grupo}]")
        for valor, veces in Counter(valores).most_common():
            texto = ", ".join(valor) if isinstance(valor, tuple) else str(valor)
            print(f"     {veces}x  {texto[:90]}")
        detalle = _punto_de_divergencia(valores)
        if detalle:
            print(detalle)
        print()
    return 1 if criticos else 0


if __name__ == "__main__":
    sys.exit(main())
