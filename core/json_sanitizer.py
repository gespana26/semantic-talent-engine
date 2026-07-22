"""Saneamiento de las respuestas JSON de los modelos locales.

Un modelo instruido para devolver solo JSON a veces envuelve la respuesta en un
bloque de markdown, la precede de una frase de cortesía o emite tokens de control
propios de su plantilla de conversación. El saneamiento existía ya en
`LocalOllamaProvider`, pero **vivía como método privado de esa clase**, de modo
que la traducción de consultas —que llama a Ollama exactamente igual— no lo
aplicaba y fallaba con una respuesta que el extractor de CV habría recuperado sin
problema.

Extraerlo aquí es lo que hace que la robustez sea uniforme: una sola
implementación, un solo comportamiento, y cualquier ruta que hable con un modelo
local queda cubierta.
"""

import re

# Tokens de control de plantilla (<|im_start|>, <|endoftext|>...) que algunos
# modelos emiten por error dentro del contenido.
TOKENS_DE_CONTROL = re.compile(r"<\|.*?\|>")


def extraer_json(texto_crudo: str) -> str:
    """Devuelve solo el bloque JSON de una respuesta posiblemente contaminada.

    El orden de las estrategias va de la más fiable a la más tolerante: primero
    el bloque de markdown explícito, después cualquier bloque cercado, y por
    último el tramo entre la primera llave de apertura y la última de cierre.
    """
    texto = TOKENS_DE_CONTROL.sub("", str(texto_crudo or ""))

    if "```json" in texto:
        return texto.split("```json")[1].split("```")[0].strip()
    if "```" in texto:
        partes = texto.split("```")
        if len(partes) > 1:
            return partes[1].strip()

    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio != -1 and fin != -1 and fin > inicio:
        return texto[inicio:fin + 1].strip()

    return texto.strip()
