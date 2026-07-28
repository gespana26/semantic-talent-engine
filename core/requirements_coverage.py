"""Verificación de cobertura de requisitos entre una vacante y un candidato.

POR QUÉ EXISTE ESTE MÓDULO
--------------------------
La afinidad es una única similitud coseno sobre textos mezclados, y por eso no
puede expresar la noción de requisito. Un candidato con doce años de
infraestructura tecnológica obtiene una afinidad alta frente a una vacante de
Project Manager aunque no cumpla ninguna de las dos habilidades exigidas: la
señal de los requisitos concretos se diluye entre el cargo, el perfil y los años
de experiencia. Ningún umbral sobre esa magnitud distingue "puntúa alto porque
encaja" de "puntúa alto porque tiene mucho texto parecido".

La cobertura responde una pregunta distinta y verificable, requisito a requisito:
¿aparece esta habilidad en el candidato, sí o no?

ESTRATEGIA HÍBRIDA
------------------
1. **Léxica.** Exacta y barata. Cubre el caso mayoritario y no admite discusión:
   si el candidato escribió "Metodologías ágiles", el requisito está cubierto.
2. **Semántica, solo para lo que falla.** Es lo que resuelve los sinónimos, que
   es precisamente donde un filtro literal fracasa: "Scrum" y "Kanban" deben
   cubrir "Metodologías ágiles"; "elocuencia" debe cubrir "comunicación asertiva".

El orden importa: la vía semántica se reserva para las candidatas a fallo, de
modo que su coste se paga solo cuando aporta algo.

El resultado es además explicable: no solo dice cuánto cubre, sino **qué falta**.
"""

import re

from config import settings
from core.data_hygiene import normalizar_texto

# Palabras sin capacidad discriminante al comparar habilidades.
VACIAS = {
    "de", "del", "la", "el", "los", "las", "en", "y", "o", "con", "para", "por",
    "un", "una", "al", "a", "e", "su", "sus", "of", "the", "and", "in", "for"
}
LONGITUD_MINIMA_TOKEN = 3


def normalizar(texto: str) -> str:
    """Alias de `data_hygiene.normalizar_texto`: una sola implementacion compartida."""
    return normalizar_texto(texto)


def tokens_significativos(texto: str) -> set:
    """Extrae las palabras con contenido de un requisito."""
    palabras = re.findall(r"[a-z0-9+#.]+", normalizar(texto))
    return {p for p in palabras if len(p) >= LONGITUD_MINIMA_TOKEN and p not in VACIAS}


def cubre_lexicamente(requisito: str, texto_candidato: str) -> bool:
    """Comprueba la presencia del requisito por frase completa o por todos sus tokens.

    La comprobación por tokens evita que un orden distinto de las palabras
    ("gestión ágil de proyectos" frente a "gestión de proyectos ágiles") cuente
    como incumplimiento.
    """
    req, texto = normalizar(requisito), normalizar(texto_candidato)
    if not req:
        return False
    if req in texto:
        return True

    tokens = tokens_significativos(req)
    if not tokens:
        return False
    presentes = tokens_significativos(texto)
    return tokens.issubset(presentes)


def _coseno(a, b) -> float:
    """Similitud coseno entre dos vectores.

    Se convierte a `float` de Python por el mismo motivo que en
    `core.baseline.coseno`: la función de embeddings real devuelve `float32` de
    NumPy, que no es subclase de `float`, y ese tipo contamina todo lo que se
    calcule a partir de él hasta llegar a la interfaz.
    """
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return float(num / (na * nb)) if na and nb else 0.0


# Línea base: habilidades reales, de dominios distintos entre sí y ajenas a las
# que el sistema evalúa. Miden cuánta similitud obtiene un requisito frente a algo
# que con certeza no lo cubre.
#
# Están expresadas a nivel de HABILIDAD y no de profesión, y esa distinción es
# deliberada. Con referencias de profesión ("cocina", "enfermería") el listón
# quedaba demasiado bajo: cualquier habilidad del mismo sector que el requisito lo
# superaba sin ser equivalente, de modo que "Servidores" podía darse por
# equivalente a "Modelos Predictivos" solo por ser ambas informáticas. La línea
# base debe representar "otra habilidad cualquiera", no "otro oficio".
REFERENCIAS_AJENAS = [
    "atención telefónica al cliente",
    "archivo y gestión documental en papel",
    "conducción de vehículos de reparto",
    "cocina mediterránea y repostería",
    "poda de árboles y jardinería",
    "contabilidad de costes y facturación",
]


def cubre_semanticamente(pendientes: list, habilidades_candidato: list, funcion_embeddings) -> dict:
    """Resuelve por contraste los requisitos que la vía léxica no encontró.

    No basta con exigir una similitud absoluta alta. Los embeddings de este
    proyecto ocupan un cono estrecho —lo confirmó la medición de afinidad, donde
    toda la población cabía en siete puntos—, de modo que dos textos sin relación
    alguna obtienen igualmente una similitud elevada. Un umbral fijo sobre esa
    magnitud marcaría cualquier habilidad como equivalente a cualquier requisito.

    La comprobación es por tanto **relativa**: un requisito se considera cubierto
    si la habilidad más próxima del candidato lo supera por un margen frente a la
    mejor de un conjunto de conceptos ajenos. Se pregunta "¿se parece más a esta
    habilidad que a la cocina o la jardinería?", que es una pregunta estable, en
    lugar de "¿supera 0,6?", que depende de la geometría del modelo.

    Devuelve {requisito: (habilidad_más_cercana, contraste)} para los cubiertos.
    """
    if not pendientes or not habilidades_candidato or funcion_embeddings is None:
        return {}

    try:
        vectores = funcion_embeddings(pendientes + habilidades_candidato + REFERENCIAS_AJENAS)
    except Exception:
        return {}

    esperados = len(pendientes) + len(habilidades_candidato) + len(REFERENCIAS_AJENAS)
    if not vectores or len(vectores) != esperados:
        return {}

    corte_hab = len(pendientes)
    corte_ref = corte_hab + len(habilidades_candidato)
    vec_req = vectores[:corte_hab]
    vec_hab = vectores[corte_hab:corte_ref]
    vec_ref = vectores[corte_ref:]

    resueltos = {}
    for requisito, v_req in zip(pendientes, vec_req):
        mejor_similitud, mejor_habilidad = -1.0, None
        for habilidad, v_hab in zip(habilidades_candidato, vec_hab):
            s = _coseno(v_req, v_hab)
            if s > mejor_similitud:
                mejor_similitud, mejor_habilidad = s, habilidad

        linea_base = max((_coseno(v_req, v) for v in vec_ref), default=0.0)
        contraste = mejor_similitud - linea_base

        if contraste >= settings.MARGEN_CONTRASTE_REQUISITO:
            resueltos[requisito] = (mejor_habilidad, round(contraste, 3))
    return resueltos


def evaluar_cobertura(requisitos: list, habilidades_candidato: list,
                      texto_candidato: str = "", funcion_embeddings=None) -> dict:
    """Determina qué requisitos de la vacante cubre el candidato y cuáles no.

    Args:
        requisitos: Habilidades o estudios exigidos por la vacante.
        habilidades_candidato: Habilidades declaradas en el perfil del candidato.
        texto_candidato: Perfil completo opcional; la vía léxica lo aprovecha
            para dar por cubierta una habilidad descrita en la experiencia
            aunque no aparezca declarada como tal.
        funcion_embeddings: Cliente de embeddings para la verificación por
            contraste semántico; si es ``None``, solo se aplica la vía léxica.

    Returns:
        Diccionario con la proporción cubierta (``ratio``), las listas de
        requisitos cubiertos y faltantes, y las equivalencias detectadas por
        contraste.
    """
    requisitos = [r for r in (requisitos or []) if str(r).strip()]
    habilidades = [h for h in (habilidades_candidato or []) if str(h).strip()]

    if not requisitos:
        # Una vacante sin requisitos declarados no puede incumplirse.
        return {"cubiertos": [], "faltantes": [], "por_similitud": {},
                "ratio": 1.0, "total": 0, "sin_requisitos": True}

    corpus = " ".join(habilidades) + " " + str(texto_candidato or "")

    cubiertos, pendientes = [], []
    for requisito in requisitos:
        (cubiertos if cubre_lexicamente(requisito, corpus) else pendientes).append(requisito)

    por_similitud = cubre_semanticamente(pendientes, habilidades, funcion_embeddings)
    cubiertos += list(por_similitud)
    faltantes = [r for r in pendientes if r not in por_similitud]

    return {
        "cubiertos": cubiertos,
        "faltantes": faltantes,
        "por_similitud": por_similitud,
        "ratio": len(cubiertos) / len(requisitos),
        "total": len(requisitos),
        "sin_requisitos": False
    }
