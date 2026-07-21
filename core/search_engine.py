"""Módulo encargado de la recuperación semántica de información, filtrado estructural de metadatos y cálculo de índices de afinidad."""

import json
import chromadb
from chromadb.utils import embedding_functions
from config import settings
from core import baseline
from core.affinity import calcular_afinidad, explicar
from core.data_hygiene import normalizar_texto, primer_dato_valido

class CVSearchEngine:
    """Ejecuta consultas de similitud de alta velocidad en espacios vectoriales aplicando Post-Retrieval Filtering en Python."""
    
    def __init__(self, collection_name: str = "talento-global-empresa"):
        self.client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
        self.embedding_function = embedding_functions.OllamaEmbeddingFunction(
            url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
            model_name=settings.EMBEDDING_MODEL
        )
        self.collection = self.client.get_collection(
            name=collection_name,
            embedding_function=self.embedding_function
        )
        # Línea base por criterio de consulta. Se cachea porque una misma sesión
        # repite la consulta (paginación, cambio de filtro) y su cálculo es una
        # llamada de embeddings.
        self._lineas_base = {}

    # Metadatos de infraestructura: no describen al candidato y no deben poder
    # satisfacer un requisito de búsqueda.
    CAMPOS_NO_DESCRIPTIVOS = {
        "pdf_file_path", "origen", "fecha_actualizacion", "tipo_registro", "raw_json"
    }

    def _evaluar_filtro_python(self, metadata: dict, filtro_nli: dict) -> bool:
        """Motor de evaluación léxica interno. Refactorizado para búsqueda 'Omnidireccional' (Forgiving Filter)."""
        if not filtro_nli: 
            return True 
        
        # 🌟 EL SECRETO: Aplanamos toda la data del candidato en un solo bloque de texto.
        # Si la IA se equivoca de campo (ej. busca en 'perfil' pero la palabra está en 'estudios'), el sistema lo salva.
        # Los metadatos de infraestructura quedan fuera del aplanado: la ruta del PDF,
        # el origen de la postulación o la marca de tiempo no describen al candidato, y
        # sí generan falsos positivos. Un requisito OBLIGATORIO de "web" no debe
        # satisfacerse porque el candidato se postulara desde el portal web.
        contenido = " ".join(
            str(valor) for clave, valor in metadata.items() if clave not in self.CAMPOS_NO_DESCRIPTIVOS
        )
        texto_global_candidato = str(metadata.get("raw_json", "")).lower() + " " + contenido.lower()

        # Se cuentan las condiciones realmente evaluadas. `where_filter` es un
        # diccionario libre que compila un LLM, así que puede llegar con una forma
        # que este evaluador no reconozca. Antes, en ese caso, la función caía al
        # `return True` final: un requisito declarado innegociable por el
        # reclutador quedaba desactivado en silencio y nadie se enteraba.
        evaluadas = 0

        # Caso 1: Arreglo bilingüe ($or)
        if "$or" in filtro_nli:
            for condicion in filtro_nli["$or"]:
                if not isinstance(condicion, dict):
                    continue
                for campo, operacion in condicion.items():
                    if isinstance(operacion, dict) and "$contains" in operacion:
                        evaluadas += 1
                        valor_buscado = str(operacion["$contains"]).lower()
                        # Si el término existe en CUALQUIER parte de su CV, pasa el filtro
                        if valor_buscado in texto_global_candidato:
                            return True
            # Ninguna alternativa reconocible: fail-closed, no fail-open.
            return False

        # Caso 2: Filtro obligatorio simple
        for campo, operacion in filtro_nli.items():
            if isinstance(operacion, dict) and "$contains" in operacion:
                evaluadas += 1
                valor_buscado = str(operacion["$contains"]).lower()
                if valor_buscado not in texto_global_candidato:
                    return False

        # El filtro traía condiciones, pero ninguna era interpretable. Descartar
        # es la opción segura: si el reclutador exigió algo y el sistema no supo
        # comprobarlo, no puede afirmar que el candidato lo cumple.
        if evaluadas == 0:
            return False

        return True
    
    def buscar_candidato_por_identidad(self, termino_busqueda: str) -> list:
        """Bypass del motor vectorial: recupera un candidato por nombre o correo.

        Cuando el término es un correo completo se resuelve con un acceso por
        metadato, que el motor indexa. En los demás casos la búsqueda es parcial
        y sin distinguir mayúsculas ni acentos, algo que ningún filtro nativo de
        ChromaDB expresa: `where` solo admite operadores exactos y
        `where_document` distingue mayúsculas y mira el documento embebido, no
        los metadatos.

        Se evaluó resolverlo escaneando los documentos en lugar de los metadatos,
        que ocupan 3,9 veces menos. Se descartó por dos motivos medidos: buscar en
        el documento completo devuelve **todos** los candidatos ante cualquier
        palabra común —"ingeniero" o "proyectos" acertaban en los 40 de la
        prueba—, y restringirlo a la primera línea acopla la búsqueda al formato
        del texto y **pierde la búsqueda parcial por correo**, porque el correo no
        está en el documento. El recorrido es O(N) y asumido: es la ruta del
        comando `/nombre:`, de uso puntual.

        Lo que sí se corrige es la normalización, que era el fallo real: hoy
        buscar "maria" no encontraba a "María" ni "pena" a "Peña".
        """
        termino = normalizar_texto(termino_busqueda)
        if not termino:
            return []

        # Correo completo: acceso directo por metadato en lugar de recorrer todo.
        if "@" in termino:
            try:
                exacto = self.collection.get(
                    where={"correo_electronico": termino}, include=["metadatas"]
                )
                encontrados = [m for m in (exacto.get("metadatas") or []) if m]
                if encontrados:
                    return encontrados
            except Exception:
                pass  # El motor no admite el filtro: se recurre al recorrido.

        resultados = self.collection.get(include=["metadatas"])
        candidatos_encontrados = []

        for meta in (resultados.get("metadatas") or []):
            if not meta:
                continue
            nombre = normalizar_texto(meta.get("nombre_completo"))
            correo = normalizar_texto(meta.get("correo_electronico"))

            if termino in nombre or termino in correo:
                candidatos_encontrados.append(meta)

        return candidatos_encontrados
    
    def _tamano_recuperacion(self) -> int:
        """Cuántos vecinos pedir, adaptándose al tamaño real de la colección.

        La recuperación vectorial dejó de ser el orden final cuando se introdujo
        el re-puntuado por componentes, y con ello dejó de ser un buen criterio
        para decidir a quién se evalúa: el rango completo de la distancia vale
        4,4 puntos de afinidad, mientras que cubrir un requisito más vale entre
        15 y 37,5. Un candidato que cumple todos los requisitos pero queda lejos
        por vector debe entrar igual.

        Por eso el número fijo de 50 se sustituye por el tamaño de la colección,
        acotado. **En un silo eso significa recuperar a todos los postulantes y
        eliminar el techo de recall por completo**, que es viable precisamente
        porque el silo es pequeño por construcción: contiene los candidatos de
        una sola vacante.
        """
        try:
            total = int(self.collection.count())
        except Exception:
            total = settings.MAX_RECUPERACION
        return max(1, min(total or 1, settings.MAX_RECUPERACION))

    def _consultar_vectorial(self, query_text: str, prefiltrar: bool, n_results: int = None) -> dict:
        """Lanza la consulta vectorial, con o sin pre-filtro nativo por tipo de registro."""
        parametros = {
            "query_texts": [query_text],
            "n_results": n_results or self._tamano_recuperacion(),
            "include": ["documents", "metadatas", "distances"]
        }
        if prefiltrar:
            parametros["where"] = {"tipo_registro": "candidato"}
        return self.collection.query(**parametros)

    COLECCION_GLOBAL = "talento-global-empresa"

    def _aplica_corte_de_pertinencia(self) -> bool:
        """Decide si procede descartar resultados por falta de pertinencia.

        La distinción es de fondo y no de implementación. En un silo la población
        está autoseleccionada: son personas que se postularon a esa vacante, y
        ocultarle al reclutador a quien se molestó en postularse sería
        presuntuoso, por mal que encaje. Además se midió que en dos silos el
        candidato medio queda por debajo de la línea base, de modo que un corte
        allí borraría postulantes reales.

        En la bolsa global es al revés: el sistema propone a personas que nunca
        se postularon a esa vacante, y ahí un suelo de pertinencia es justo lo que
        permite responder "no tengo a nadie" en lugar de rellenar la ventana con
        los menos malos.
        """
        return self.collection.name == self.COLECCION_GLOBAL

    def linea_base(self, criterio: str) -> float:
        """Similitud que obtiene un perfil manifiestamente ajeno frente a este criterio."""
        if criterio not in self._lineas_base:
            self._lineas_base[criterio] = baseline.calcular_linea_base(
                criterio, self.embedding_function
            )
        return self._lineas_base[criterio]

    def search_candidates(self, query_text: str, limit: int = 5, where_filter: dict = None,
                          vacante: dict = None) -> list:
        """Recupera candidatos por similitud y los re-puntúa con la afinidad compuesta.

        ARQUITECTURA: RECUPERAR Y RE-PUNTUAR
        ------------------------------------
        La recuperación sigue siendo vectorial —es la única capaz de manejar la
        colección entera con un coste razonable— pero el orden que devuelve el
        vector no es el orden final. Solo la ventana de los primeros resultados
        se re-puntúa con la fórmula por componentes, que es cara porque verifica
        requisito a requisito. Es el patrón *retrieve-and-rerank*: se paga la
        precisión solo donde puede cambiar la decisión.

        LÍMITE DE DISEÑO QUE CONVIENE DECLARAR
        --------------------------------------
        **La afinidad compuesta solo existe cuando hay una vacante
        estructurada.** En una búsqueda libre del reclutador no hay habilidades
        exigidas que cubrir ni titulación contra la que contrastar, de modo que
        no hay componentes que ponderar. En ese caso el porcentaje es la
        similitud normalizada: el coseno menos la línea base de esa consulta,
        reescalado. Sigue sin ser la escala antigua —cuyo suelo era el 84 %—,
        pero es una señal más débil, y la interfaz lo distingue.
        """
        try:
            # El silo es autocontenido: la vacante comparte colección con sus candidatos.
            # Pre-filtrar por tipo_registro la excluye en el propio motor, de modo que no
            # consume uno de los 50 resultados de la ventana de recuperación.
            n_recuperar = self._tamano_recuperacion()
            results = self._consultar_vectorial(query_text, prefiltrar=True, n_results=n_recuperar)

            # Retrocompatibilidad: las colecciones anteriores a la introducción de
            # tipo_registro devolverían vacío bajo el pre-filtro.
            if not (results and results.get('ids') and len(results['ids'][0]) > 0):
                results = self._consultar_vectorial(query_text, prefiltrar=False, n_results=n_recuperar)

            # Ventana de re-puntuación. Sin vacante estructurada no hay nada que
            # recalcular —la similitud normalizada es monótona respecto a la
            # distancia y no reordena—, así que basta con recuperar lo pedido.
            # Con vacante se re-puntúa toda la ventana: el coste no crece en
            # número de llamadas al modelo de embeddings sino en tamaño de lote,
            # porque la caché comparte los requisitos entre todos los candidatos.
            ventana = max(limit, settings.TOP_N_RERANK) if vacante else limit

            candidatos = []
            correos_vistos = set()

            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # 1. Ignorar el registro de la vacante que comparte la colección.
                    #    Se discrimina por tipo_registro; la ausencia de nombre_completo
                    #    solo se usa como heurística en registros legacy sin ese metadato,
                    #    porque descartaría a un candidato cuyo nombre no se extrajo.
                    tipo_registro = metadata.get("tipo_registro")
                    if tipo_registro == "perfil_vacante":
                        continue
                    if not tipo_registro and not metadata.get("nombre_completo"):
                        continue


                    # 2. El filtro de pertinencia ya no vive aquí. El umbral fijo
                    #    de distancia 1.2 exigía similitud coseno negativa y las
                    #    distancias reales del proyecto van de 0,18 a 0,36: nunca
                    #    llegó a descartar nada. Su función —decidir que un
                    #    resultado no es pertinente— se resuelve ahora en el
                    #    re-puntuado, contra la línea base medida de la consulta.

                    # 3. Segunda Guillotina (Python): Evaluamos las reglas duras (Obligatorio/Excluyente)
                    if not self._evaluar_filtro_python(metadata, where_filter):
                        continue
                        
                    # 4. Deduplicación por identidad. Un correo ausente no es una
                    #    identidad: si se usara como clave, todos los candidatos
                    #    sin correo compartirían la cadena vacía y solo
                    #    sobreviviría el primero. Ante la duda no se descarta,
                    #    porque un duplicado molesta y un falso negativo elimina a
                    #    una persona de todas las búsquedas.
                    correo_actual = primer_dato_valido(metadata.get("correo_electronico")).lower()
                    if correo_actual:
                        if correo_actual in correos_vistos:
                            continue
                        correos_vistos.add(correo_actual)
                    
                    # 5. Empaquetado. La puntuación se asigna después, sobre la
                    #    ventana completa, porque depende de la línea base y de
                    #    la vacante y no solo de esta distancia.
                    raw_json_str = metadata.get("raw_json")
                    candidate_data = json.loads(raw_json_str) if raw_json_str else {}

                    candidatos.append({
                        "id_registro": results['ids'][0][i],
                        "nombre": metadata.get("nombre_completo"),
                        "correo": metadata.get("correo_electronico"),
                        "distancia": distance,
                        "pdf_origen": metadata.get("pdf_file_path"),
                        "perfil_completo_json": candidate_data
                    })

                    if len(candidatos) == ventana:
                        break

            return self._repuntuar(candidatos, query_text, vacante, limit)
        except Exception as e:
            raise RuntimeError(f"Fallo en la arquitectura de recuperación y filtrado RAG: {e}")

    def _repuntuar(self, candidatos: list, criterio: str, vacante: dict, limit: int) -> list:
        """Asigna la puntuación final a la ventana recuperada y la reordena.

        La línea base se descuenta siempre: sin ella el porcentaje arranca en el
        84 % para cualquiera. La afinidad compuesta se calcula solo si hay
        vacante estructurada; en su ausencia el resultado se marca como
        `similitud`, para que la interfaz no presente como equivalentes dos
        números que miden cosas distintas.
        """
        if not candidatos:
            return []

        base = self.linea_base(criterio)
        embeddings = baseline.cachear_embeddings(self.embedding_function) if vacante else None
        aplicar_corte = self._aplica_corte_de_pertinencia()

        puntuados = []
        for candidato in candidatos:
            similitud = baseline.similitud_desde_distancia(candidato.pop("distancia"))

            # Corte de pertinencia. Sustituye al umbral fijo de 1.2, que exigía
            # similitud negativa y jamás se activó. Se exige estar claramente por
            # debajo de un perfil ajeno, y no solo empatar con él, porque se midió
            # que un CV en inglés pierde en torno a 26 puntos de similitud
            # normalizada por el idioma: cortar justo en la línea base lo
            # descartaría por cómo escribe y no por lo que sabe.
            if aplicar_corte and similitud < base - settings.MARGEN_CORTE_PERTINENCIA:
                continue

            normalizada = baseline.normalizar_similitud(similitud, base)
            candidato["similitud_normalizada"] = round(normalizada * 100, 2)
            candidato["linea_base"] = round(base, 4)
            puntuados.append(candidato)

            if not vacante:
                candidato["tipo_puntuacion"] = "similitud"
                candidato["porcentaje_afinidad"] = candidato["similitud_normalizada"]
                candidato["desglose"] = None
                candidato["explicacion"] = "Búsqueda libre: solo similitud de perfil."
                continue

            desglose = calcular_afinidad(
                vacante=vacante,
                candidato=candidato["perfil_completo_json"],
                similitud_normalizada=normalizada,
                funcion_embeddings=embeddings
            )
            candidato["tipo_puntuacion"] = "afinidad"
            candidato["porcentaje_afinidad"] = desglose["afinidad"]
            candidato["desglose"] = desglose
            candidato["explicacion"] = explicar(desglose)

        candidatos = puntuados

        # El orden vectorial deja de decidir: manda la afinidad compuesta.
        candidatos.sort(key=lambda c: c["porcentaje_afinidad"], reverse=True)
        return candidatos[:limit]
        
    ID_VACANTE = "VACANTE_PRINCIPAL"

    @staticmethod
    def _componer_requisitos(vacante: dict, meta: dict) -> str:
        """Compone el texto de requisitos replicando la forma del documento del candidato.

        La comparación semántica solo puede considerar aquello que llega al texto
        que se vectoriza. El documento del candidato incluye su nivel académico,
        sus años de experiencia y sus competencias blandas; si el criterio de la
        vacante no incluye los exigidos, esas tres dimensiones quedan fuera de la
        comparación aunque estén almacenadas. Replicar las mismas etiquetas
        alinea además la estructura de ambos textos dentro del espacio vectorial.
        """
        campos = [
            ("Cargo", str(vacante.get("titulo_cargo") or meta.get("titulo_cargo") or "")),
            ("Nivel Académico", ", ".join(vacante.get("estudios_requeridos") or [])),
            ("Años de Experiencia Total", str(vacante.get("experiencia_minima_anos") or "")),
            ("Perfil Profesional", str(vacante.get("perfil_general") or "")),
            ("Habilidades Técnicas", ", ".join(vacante.get("hard_skills") or [])),
            ("Competencias Blandas", ", ".join(vacante.get("soft_skills") or [])),
        ]
        # Una etiqueta sin contenido solo aporta ruido al embedding.
        lineas = [f"{etiqueta}: {valor}" for etiqueta, valor in campos if valor.strip()]
        return "\n".join(lineas)

    def _texto_criterio(self, meta: dict) -> str:
        """Deriva de los metadatos de la vacante el texto que servirá de criterio de comparación.

        Se prioriza el JSON estructurado sobre el texto original de la oferta. El
        texto original es la convocatoria completa —beneficios, datos de contacto,
        presentación de la empresa— y solo una parte de él son requisitos; su
        propósito es mostrarse en el catálogo, no servir de criterio.
        """
        raw_json = meta.get("raw_json")
        if raw_json:
            try:
                vacante = json.loads(raw_json)
            except (ValueError, TypeError):
                vacante = None
            if vacante:
                requisitos = self._componer_requisitos(vacante, meta)
                if requisitos:
                    return requisitos

        # Retrocompatibilidad: vacantes sin JSON estructurado utilizable.
        texto_original = meta.get("texto_original")
        if texto_original and texto_original != "Texto original no disponible":
            return texto_original
        return ""

    def obtener_vacante_estructurada(self) -> dict:
        """Recupera el JSON de la vacante del silo, que es lo que la afinidad necesita.

        `obtener_perfil_vacante` devuelve el texto que se consulta contra el
        índice; esto devuelve los campos con los que se verifica el
        cumplimiento. Son dos usos distintos del mismo registro: el texto entra
        en el espacio vectorial, los campos se comprueban uno a uno.
        """
        try:
            registro = self.collection.get(ids=[self.ID_VACANTE], include=["metadatas"])
            metadatos = registro.get("metadatas") or []
            if not metadatos or not metadatos[0]:
                return {}
            return json.loads(metadatos[0].get("raw_json") or "{}") or {}
        except Exception:
            return {}

    def obtener_perfil_vacante(self) -> str:
        """Extrae el perfil general de la vacante almacenada en el silo para usarlo como criterio de Auto-Match.

        El silo es autocontenido: la vacante vive en la misma colección que sus
        candidatos bajo el identificador fijo `VACANTE_PRINCIPAL`. Ese identificador
        convierte la recuperación del criterio en un acceso directo por clave, sin
        recorrer la colección ni depender de heurísticas sobre los metadatos.
        """
        try:
            registro = self.collection.get(ids=[self.ID_VACANTE], include=["metadatas", "documents"])
            metadatos = registro.get("metadatas") or []
            if metadatos and metadatos[0]:
                return self._texto_criterio(metadatos[0])

            # Retrocompatibilidad: colecciones anteriores al identificador fijo.
            return self._buscar_vacante_legacy()
        except Exception:
            return ""

    def _buscar_vacante_legacy(self) -> str:
        """Localiza la vacante en colecciones antiguas, donde el identificador no era fijo."""
        try:
            resultados = self.collection.get(include=["metadatas", "documents"])
            for meta in (resultados.get('metadatas') or []):
                if not meta:
                    continue
                if meta.get("tipo_registro") == "perfil_vacante" or not meta.get("nombre_completo"):
                    return self._texto_criterio(meta)
            return ""
        except Exception:
            return ""