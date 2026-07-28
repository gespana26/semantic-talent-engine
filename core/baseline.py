"""Línea base de similitud: el cero real de cada vacante.

POR QUÉ HACE FALTA
------------------
La similitud coseno entre dos textos profesionales sin relación alguna no es 0,
es de unos 0,68. Cualquier escala que dé por supuesto el cero teórico —como la
antigua `(1 + coseno) / 2`— reparte cien puntos sobre un rango del que solo usa
siete, y su suelo empírico resulta ser el 84 %. Un criterio de jardinería medido
contra un banco de perfiles tecnológicos obtenía un 85,46 %.

La línea base es la similitud que obtiene alguien que con certeza no encaja. Se
mide contra un conjunto de perfiles de referencia manifiestamente ajenos al
dominio y se resta antes de escalar, de modo que el cero de la escala vuelva a
significar "no tiene nada que ver".

**Se calcula por vacante, no como constante global.** La medición dio valores
entre 0,6976 y 0,7654 según el criterio, así que un número fijo en la
configuración habría estado equivocado para casi todas las vacantes. El coste de
calcularla es una sola llamada de embeddings por criterio, cuyo resultado se
cachea mientras dure la búsqueda.

**Definición adoptada: el máximo, no la media.** Es la lectura más estricta —el
perfil ajeno que más se parece marca el listón— y por tanto la más conservadora
a la hora de afirmar que un candidato destaca.
"""

# Perfiles de candidato sintéticos, ajenos a cualquier dominio técnico. Replican
# la forma del documento real del candidato (mismas etiquetas) porque la
# estructura compartida contribuye por sí sola a la similitud: medirla con un
# formato distinto mediría el desemparejamiento de formatos y no el contenido.
#
# Por eso ninguno lleva línea de nombre: el documento del candidato dejó de
# incluirla cuando la identidad se replegó a los metadatos, y estos perfiles
# tienen que seguir ese formato exactamente. Una línea de más aquí falsearía la
# línea base a la baja y con ella todas las similitudes normalizadas.
PERFILES_AJENOS = [
    ("Cocina", "Nivel Académico: Escuela de Hostelería\n"
               "Años de Experiencia Total: 8\nPerfil Profesional: Jefe de cocina en restaurante "
               "de menú diario, elaboración de platos y control de aprovisionamiento.\n"
               "Habilidades Técnicas: Cocina mediterránea, Repostería, Emplatado\n"
               "Competencias Blandas: Trabajo bajo presión"),
    ("Jardinería", "Nivel Académico: Formación profesional agraria\n"
                   "Años de Experiencia Total: 6\nPerfil Profesional: Mantenimiento de zonas verdes, "
                   "poda de arbolado y riego de parques municipales.\n"
                   "Habilidades Técnicas: Poda, Riego automático, Maquinaria agrícola\n"
                   "Competencias Blandas: Autonomía"),
    ("Enfermería", "Nivel Académico: Grado en Enfermería\n"
                   "Años de Experiencia Total: 10\nPerfil Profesional: Atención a pacientes en "
                   "planta de hospitalización, administración de medicación y curas.\n"
                   "Habilidades Técnicas: Canalización de vías, Triaje, Soporte vital\n"
                   "Competencias Blandas: Empatía"),
    ("Derecho", "Nivel Académico: Licenciatura en Derecho\n"
                "Años de Experiencia Total: 12\nPerfil Profesional: Defensa de clientes en "
                "procedimientos penales y redacción de recursos ante la audiencia provincial.\n"
                "Habilidades Técnicas: Derecho penal, Litigación oral, Redacción jurídica\n"
                "Competencias Blandas: Oratoria"),
    ("Pesca", "Nivel Académico: Certificado de marinero pescador\n"
              "Años de Experiencia Total: 15\nPerfil Profesional: Faenas de pesca de altura, "
              "manejo de artes de arrastre y mantenimiento de cubierta.\n"
              "Habilidades Técnicas: Artes de arrastre, Navegación costera, Estiba\n"
              "Competencias Blandas: Resistencia física"),
]

TEXTOS_AJENOS = [texto for _, texto in PERFILES_AJENOS]


def coseno(a, b) -> float:
    """Similitud coseno entre dos vectores.

    **El resultado se convierte a `float` de Python a propósito.** La función de
    embeddings real devuelve arrays de NumPy en `float32`, y ese tipo se propaga
    por toda la aritmética: la línea base, la similitud normalizada y de ahí el
    porcentaje que llega a la interfaz. El problema es que `np.float32` **no** es
    subclase de `float` —`np.float64` sí lo es—, de modo que un
    `isinstance(valor, float)` aguas abajo devuelve `False` y el número deja de
    reconocerse como número.

    Ocurrió: el dashboard rotulaba «Léxico» todos los resultados de búsqueda,
    porque su comprobación de tipo rechazaba el porcentaje que el motor sí había
    calculado. Convertir aquí, en el único punto donde el vector se reduce a un
    escalar, es lo que impide que el tipo del proveedor de embeddings viaje al
    resto del sistema.
    """
    num = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return float(num / (na * nb)) if na and nb else 0.0


def calcular_linea_base(criterio: str, funcion_embeddings) -> float:
    """Similitud que obtiene el mejor de los perfiles ajenos frente a este criterio.

    Devuelve 0.0 si no hay forma de medirla —sin cliente de embeddings o ante un
    fallo del servicio—. Es la degradación segura: sin línea base la similitud
    normalizada equivale a la similitud cruda, que sobrestima, pero la cobertura
    de requisitos sigue siendo el componente principal de la afinidad y el
    veredicto no queda en manos de este valor.
    """
    if not criterio or funcion_embeddings is None:
        return 0.0
    try:
        vectores = funcion_embeddings([criterio] + TEXTOS_AJENOS)
    except Exception:
        return 0.0
    if not vectores or len(vectores) != len(TEXTOS_AJENOS) + 1:
        return 0.0
    v_criterio, v_ajenos = vectores[0], vectores[1:]
    return float(max((coseno(v_criterio, v) for v in v_ajenos), default=0.0))


def normalizar_similitud(similitud: float, linea_base: float) -> float:
    """Reescala el coseno sobre el margen realmente disponible por encima del suelo.

    Un perfil ajeno pasa a valer 0 y el máximo teórico sigue siendo 1. Fuera de
    ese rango se recorta: por debajo de la línea base no hay grados de "peor que
    nada".
    """
    if linea_base >= 1.0:
        return 0.0
    return float(max(0.0, min(1.0, (similitud - linea_base) / (1.0 - linea_base))))


def cachear_embeddings(funcion_embeddings):
    """Envuelve el cliente de embeddings memorizando los textos ya vectorizados.

    Al re-puntuar una lista de candidatos, los requisitos de la vacante y los
    conceptos de contraste son idénticos en todas las comprobaciones y solo
    cambian las habilidades del candidato. Sin memoria, cada candidato pagaría
    de nuevo la vectorización de lo que no cambia. La caché vive lo que dura una
    búsqueda: no hay riesgo de servir un vector obsoleto.
    """
    if funcion_embeddings is None:
        return None

    memoria = {}

    def envoltorio(textos):
        """Devuelve los embeddings de `textos`, calculando solo los no cacheados."""
        pendientes = [t for t in textos if t not in memoria]
        if pendientes:
            # Se conserva el orden y se eliminan duplicados dentro del mismo lote.
            unicos = list(dict.fromkeys(pendientes))
            vectores = funcion_embeddings(unicos)
            if not vectores or len(vectores) != len(unicos):
                # Respuesta inconsistente: se devuelve tal cual y decide quien llama.
                return vectores
            memoria.update(zip(unicos, vectores))
        return [memoria[t] for t in textos]

    return envoltorio


def similitud_desde_distancia(distancia: float) -> float:
    """Convierte la distancia que devuelve ChromaDB en similitud coseno."""
    try:
        return 1.0 - float(distancia)
    except (TypeError, ValueError):
        return 0.0
