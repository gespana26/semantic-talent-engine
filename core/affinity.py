"""Cálculo de la afinidad candidato-vacante por componentes verificables.

POR QUÉ NO SE USA LA SIMILITUD DIRECTA
--------------------------------------
La fórmula anterior era `afinidad = (1 + coseno) / 2`, que supone que dos textos
sin relación dan coseno 0 y por tanto un 50 %. La medición lo desmintió: el
coseno entre textos profesionales sin relación alguna es de unos 0,68, de modo
que una vacante de jardinería obtenía un 85 % de afinidad media contra un banco
de perfiles tecnológicos. El suelo empírico de aquella escala era 84 %, no 0 %.

Peor aún: al restar ese suelo, el mejor candidato pertinente de cada silo apenas
alcanzaba entre el 7 % y el 27 %. La similitud de documento completo casi no
distingue a un candidato válido de uno ajeno; no era un problema de escalado,
sino de falta de señal.

QUÉ MIDE ESTA FÓRMULA
---------------------
    Afinidad = (0,75 · cobertura de habilidades
              + 0,25 · similitud de perfil normalizada)
              × factor de experiencia
              × factor de profesión

- **Cobertura de habilidades**: proporción de las habilidades exigidas que el
  candidato cumple, verificada una a una. Es la señal principal porque es la
  única cuyo cero es un cero real.
- **Similitud normalizada**: el coseno menos la línea base medida para esa
  vacante, de modo que un perfil ajeno da 0 y no 84. Actúa como desempate entre
  candidatos con la misma cobertura, que es todo lo que la medición justifica.
- **Los dos factores son multiplicadores, no sumandos.** Un requisito no se
  compensa cumpliendo otra cosa. La comprobación empírica fue determinante: con
  la experiencia como componente aditiva, un criterio de cocina obtenía un 17,6 %
  contra perfiles de ingeniería solo por tener años suficientes. Como
  multiplicador, obtiene 0 %.
"""

import math

from config import settings
from core.requirements_coverage import evaluar_cobertura


def factor_experiencia(anios_candidato, anios_requeridos) -> float:
    """Penaliza la falta de experiencia con una curva cóncava.

    Se usa la raíz cuadrada y no una proporción lineal por dos razones. La
    primera es de criterio: alguien a un año de un requisito de tres no es dos
    tercios de candidato, y la proporción lineal lo hundía de un 82 % a un 55 %.
    La segunda es de robustez: `anios_experiencia_total` no lo extrae el modelo,
    lo calcula sumando duraciones, y es por tanto el campo más ruidoso del
    esquema. La curva cóncava comprime ese error justo en la zona cercana al
    requisito, que es donde se decide.

    Una vacante que no declara mínimo no puede penalizar por este concepto.
    """
    try:
        requeridos = float(anios_requeridos or 0)
        candidato = float(anios_candidato or 0)
    except (TypeError, ValueError):
        return 1.0

    if requeridos <= 0:
        return 1.0
    if candidato >= requeridos:
        return 1.0
    return math.sqrt(max(0.0, candidato) / requeridos)


def factor_profesion(ajuste_academico: float, hay_requisito: bool) -> float:
    """Penaliza que la formación del candidato no corresponda a la exigida.

    También multiplicativo: una titulación requerida no se compensa con
    habilidades. Se aplica la misma curva cóncava que a la experiencia para que
    las carreras próximas —las ofertas suelen decir "o afines"— no se hundan.

    Conserva un suelo en lugar de anular por completo. La razón es de calidad de
    dato: `nivel_academico_maximo` se extrae con precisión desigual y a veces
    devuelve genéricos como "Profesional", que no permiten juzgar la carrera. Un
    multiplicador que llegara a cero convertiría un fallo de extracción en el
    descarte silencioso de un candidato válido, justo lo que el objetivo de no
    perder talento pretende evitar.
    """
    if not hay_requisito:
        return 1.0
    return max(settings.PISO_FACTOR_PROFESION, math.sqrt(max(0.0, min(1.0, ajuste_academico))))


def _educacion_del_candidato(candidato: dict) -> list:
    """Reúne los textos que describen la formación del candidato."""
    textos = []
    nivel = str(candidato.get("nivel_academico_maximo") or "").strip()
    if nivel:
        textos.append(nivel)
    for titulo in candidato.get("educacion_detalle") or []:
        if str(titulo).strip():
            textos.append(str(titulo).strip())
    return textos


def calcular_afinidad(vacante: dict, candidato: dict, similitud_normalizada: float = 0.0,
                      funcion_embeddings=None) -> dict:
    """Calcula la afinidad y devuelve su desglose completo.

    `similitud_normalizada` se espera en el rango 0-1, ya descontada la línea
    base de la vacante. El desglose se devuelve entero para que la interfaz
    pueda justificar el número en lugar de limitarse a mostrarlo.
    """
    exigidas = [h for h in (vacante.get("hard_skills") or []) if str(h).strip()]
    estudios = [e for e in (vacante.get("estudios_requeridos") or []) if str(e).strip()]

    cobertura = evaluar_cobertura(
        requisitos=exigidas,
        habilidades_candidato=list(candidato.get("hard_skills") or []),
        texto_candidato=str(candidato.get("perfil_profesional") or ""),
        funcion_embeddings=funcion_embeddings
    )

    academico = evaluar_cobertura(
        requisitos=estudios,
        habilidades_candidato=_educacion_del_candidato(candidato),
        texto_candidato=str(candidato.get("perfil_profesional") or ""),
        funcion_embeddings=funcion_embeddings
    )

    sim = max(0.0, min(1.0, float(similitud_normalizada or 0.0)))
    base = settings.PESO_COBERTURA * cobertura["ratio"] + settings.PESO_SIMILITUD * sim

    f_exp = factor_experiencia(
        candidato.get("anios_experiencia_total"), vacante.get("experiencia_minima_anos")
    )
    f_prof = factor_profesion(academico["ratio"], hay_requisito=bool(estudios))

    return {
        "afinidad": round(base * f_exp * f_prof * 100, 2),
        "cobertura": cobertura,
        "academico": academico,
        "similitud_normalizada": round(sim * 100, 2),
        "factor_experiencia": round(f_exp, 3),
        "factor_profesion": round(f_prof, 3),
        "anios_requeridos": vacante.get("experiencia_minima_anos"),
        "anios_candidato": candidato.get("anios_experiencia_total"),
    }


def explicar(desglose: dict) -> str:
    """Redacta el desglose en una línea legible para el reclutador."""
    cob = desglose["cobertura"]
    partes = [f"cubre {len(cob['cubiertos'])} de {cob['total']} habilidades"]

    aca = desglose["academico"]
    if not aca.get("sin_requisitos"):
        partes.append(f"formación {len(aca['cubiertos'])} de {aca['total']}")

    if desglose["factor_experiencia"] < 1:
        partes.append(
            f"experiencia {desglose['anios_candidato']} de {desglose['anios_requeridos']} años"
        )

    partes.append(f"similitud de perfil {desglose['similitud_normalizada']:.0f} %")
    return " · ".join(partes)
