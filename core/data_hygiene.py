"""Utilidades de higiene de datos de contacto.

Cubre dos responsabilidades emparentadas:

1. **Centinelas.** Un centinela es un marcador de relleno que ocupa el lugar de
   un dato ausente ("0000", "N/A", "No especificado"). Como todos ellos son
   *truthy* en Python, un `a or b` los da por buenos y descarta el valor real de
   `b`. Centralizar la deteccion hace explicita y verificable la precedencia del
   dato humano sobre el extraido por el LLM.
2. **Validacion de identidad.** El correo y el telefono son la clave de
   identidad del candidato y el canal de la alerta de auto-match. Las reglas
   viven aqui, no en la vista, para que la CLI y el portal web apliquen el mismo
   contrato y para poder testearlas sin levantar Streamlit.
"""

import re

PLACEHOLDERS = {
    "",
    "-",
    "0000",
    "n/a",
    "na",
    "no aplica",
    "no disponible",
    "no especificado",
    "no especificada",
    "none",
    "null",
    "sin especificar",
}


def es_ausente(valor) -> bool:
    """Determina si un valor es un dato ausente o un centinela de relleno."""
    if valor is None:
        return True
    return str(valor).strip().lower() in PLACEHOLDERS


def primer_dato_valido(*valores, default: str = "") -> str:
    """Devuelve el primer valor que no sea un centinela, respetando el orden de precedencia."""
    for valor in valores:
        if not es_ausente(valor):
            return str(valor).strip()
    return default


# ---------------------------------------------------------------------------
# Validacion de datos de contacto
# ---------------------------------------------------------------------------

PATRON_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

# Solo se admiten digitos y los separadores de uso real en numeracion telefonica.
# La posicion del prefijo "+" no se restringe (hay notaciones como "(+34) 612...");
# la comprobacion sustantiva es el recuento de digitos.
CARACTERES_TELEFONO_VALIDOS = re.compile(r"^[0-9+\s\-().]+$")

# Rango de la recomendacion E.164: entre 7 y 15 digitos significativos.
MIN_DIGITOS_TELEFONO = 7
MAX_DIGITOS_TELEFONO = 15


def email_valido(valor) -> bool:
    """Comprueba que el correo tenga una forma sintacticamente utilizable como canal de contacto."""
    if es_ausente(valor):
        return False
    return bool(PATRON_EMAIL.match(str(valor).strip()))


def telefono_valido(valor) -> bool:
    """Comprueba que el telefono sea un numero de contacto plausible.

    La validacion es deliberadamente permisiva en formato (admite prefijo
    internacional, espacios, guiones y parentesis) y estricta en sustancia: se
    exige un recuento de digitos dentro del rango de la recomendacion E.164. Ese
    limite inferior descarta por si solo los centinelas de relleno del tipo
    "0000", que no alcanzan los siete digitos.
    """
    if es_ausente(valor):
        return False

    texto = str(valor).strip()
    if not CARACTERES_TELEFONO_VALIDOS.match(texto):
        return False

    digitos = [c for c in texto if c.isdigit()]
    return MIN_DIGITOS_TELEFONO <= len(digitos) <= MAX_DIGITOS_TELEFONO
