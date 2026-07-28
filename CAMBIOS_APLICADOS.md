# Cambios aplicados — guía de revisión

Documento de revisión. Recoge **cada cambio, el fichero y la línea exacta** donde
está, para poder contrastarlo contra el código sin buscarlo.

Los números de línea se extrajeron del código, no de memoria, y corresponden al
estado del árbol tras aplicar todos los grupos. Rama de trabajo:
`fix/defectos-criticos`. **Nada se ha enviado a GitHub.**

Estado de la suite: **327 passed, 5 skipped** en un entorno sin `chromadb`,
`fitz`, `ollama`, `openai` ni `streamlit` instalados. En un entorno completo, los
5 saltados también se ejecutan.

---

## 1. Resumen: los 13 defectos del documento de traspaso

| Ref | Defecto | Estado | Dónde revisarlo |
|---|---|---|---|
| 2.1 | La afinidad compuesta nunca se calcula en el dashboard | ✅ corregido | `views/dashboard.py:231, 257, 292, 301` |
| 2.2 | Las vistas rompen el composition root | ✅ corregido | `views/portal.py:8, 99, 209` · `views/dashboard.py:7, 126, 165` |
| 2.3 | `load_dotenv()` sin `override=True` | ✅ corregido | `config/settings.py:16` |
| 2.4 | Clave de OpenAI por defecto que enmascara el error | ✅ corregido | `config/settings.py:35` · `config/providers.py:41-102` |
| 2.5 | Saneo de JSON duplicado | ✅ corregido | `models/ai_provider.py:232, 266` |
| 2.6 | PDFs huérfanos | ✅ corregido | `core/orchestrator.py:19-53, 173, 237` · `views/portal.py:31` |
| 2.7 | Catálogo de vacantes duplicado | ✅ corregido | `views/components.py:18` · `core/vacancy_catalog.py:20-103` |
| 2.8 | El corte de pertinencia encoge el resultado | ❌ **falso positivo** | ver §4 |
| 2.9 | `core/security.py`: seis problemas | ✅ reescrito | `core/security.py` completo |
| 2.10 | `DEBUG_MODE` por defecto `True` | ✅ corregido | `config/settings.py:160` |
| 2.11 | Traductor sin regla anti-inyección | ✅ corregido | `core/query_translator.py:77, 83-103, 105` |
| 2.12 | Filtro léxico por substring | ✅ corregido | `core/search_engine.py:41-77, 111, 121` |
| 2.13 | Tests no herméticos | ✅ corregido | `core/store_client.py` + 6 módulos |

**Defectos encontrados que no estaban en el documento**, los tres corregidos:

| Ref | Defecto | Dónde |
|---|---|---|
| N1 | Usuario `admin` / `admin123` escrito en el código | `core/security.py:155` |
| N2 | `JWT_SECRET_KEY` sin longitud mínima (RFC 7518 §3.2) | `core/security.py:57, 69` |
| N3 | El último día de vigencia de la vacante se perdía | `core/vacancy_catalog.py:45` |

---

## 2. Cambios por fichero y línea

### `config/settings.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 16 | 2.3 | `load_dotenv(override=True)`. Sin él, una variable ya presente en el entorno del sistema gana al `.env`. |
| 35 | 2.4 | `OPENAI_API_KEY` pierde el relleno `"placeholder_key_clean"`; queda `""`. |
| 134-153 | 2.9 | Bloque nuevo de seguridad: `JWT_SECRET_KEY`, `JWT_HORAS_VALIDEZ`, `USUARIOS_DB_PATH`, `ADMIN_INICIAL_USUARIO`, `ADMIN_INICIAL_PASSWORD`, `LOGIN_MAX_INTENTOS`, `LOGIN_BLOQUEO_MINUTOS`. |
| 160 | 2.10 | `DEBUG_MODE` por defecto `"False"` (era `"True"`). |

### `config/providers.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 41 | 2.4 | Registro `REQUISITOS`: qué configuración necesita cada proveedor. |
| 54 | 2.4 | `_verificar_requisitos()`: comprueba la credencial del proveedor elegido. |
| 78 | 2.4 | `verificar_configuracion()`: validación de arranque, la llama `app.py`. |
| 102 | 2.4 | `get_ai_provider()` valida antes de instanciar. |

### `core/security.py` — reescritura completa

| Línea | Ref | Qué cambió |
|---|---|---|
| 57 | N2 | `LONGITUD_MINIMA_CLAVE = 32`. RFC 7518 §3.2 lo exige para HS256; PyJWT solo avisaba. |
| 69 | 2.9 | `_clave_de_firma()`: sin valor por defecto, falla explicando cómo generarla. |
| 97 | 2.9 | `verificar_configuracion()`. |
| 107 | 2.9 | `_conexion()`: sqlite con `closing()`, cierre garantizado. |
| 128 | 2.9 | `crear_usuario()`: alta sin tocar el código. |
| 155 | N1 | `_crear_admin_inicial()`: contraseña del entorno o aleatoria, mostrada **una vez y nunca al log**. |
| 192 | 2.9 | `init_db()` deja de correr al importar; idempotente. |
| 199 | 2.9 | `inicializar_seguridad()`: punto de arranque explícito. |
| 226 | 2.9 | `minutos_de_bloqueo()`: límite de intentos por usuario. |
| 251 | 2.9 | `verificar_credenciales()` respeta el bloqueo. |
| 279 | 2.9 | `generar_token()` con `datetime.now(timezone.utc)` (era `utcnow()`, deprecado). |
| 289 | 2.9 | `validar_token()`. |

### `core/query_translator.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 77 | 2.11 | Regla 6 del prompt: `SECURITY RULE`, la que los dos extractores ya tenían. |
| 83-90 | 2.11 | Delimitadores `APERTURA`/`CIERRE` y patrón de tokens de control. |
| 92 | 2.11 | `_sanear_entrada()`: quita delimitadores y `<\|im_start\|>` de la entrada. |
| 105 | 2.11 | `translate()` envía la petición delimitada; antes interpolaba entre comillas simples sin escapar. |

### `core/search_engine.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 21-22 | 2.13 | Cliente y función de embeddings vía `store_client`. |
| 41 | 2.12 | `_CARACTER_DE_PALABRA`. |
| 44 | 2.12 | `_coincide_termino()`: emparejado por palabra completa sin usar `\b`. |
| 111, 121 | 2.12 | Las dos ramas del filtro pasan a usarlo. |

### `core/store_client.py` — **fichero nuevo**

| Línea | Ref | Qué cambió |
|---|---|---|
| 35 | 2.13 | `crear_cliente()`: construcción única del cliente, import diferido. |
| 46 | 2.13 | `crear_funcion_embeddings()`: función de embeddings compartida. |

### `core/vacancy_catalog.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 20 | 2.7 | `_silos()`: colecciones que son silo, excluida la bolsa global. |
| 27 | 2.7 | `_leer_vacante()`: acceso por clave `get(ids=["VACANTE_PRINCIPAL"])`. |
| 45 | N3 | `_dias_restantes()`: compara **fechas**, no instantes. |
| 68 | 2.7 | `obtener_silos_del_reclutador()`: la proyección del dashboard, ahora en el dominio. |
| 88, 120 | 2.13 | Cliente vía `store_client`. |

### `models/ai_provider.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 155 | 2.5 | Se elimina `_extract_clean_json`; queda el comentario que explica por qué. |
| 232, 266 | 2.5 | Las dos rutas pasan a `core.json_sanitizer.extraer_json`. |
| 4 | 2.5 | Se retira `import re`, ya sin uso. |

### `core/extractor.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 33 | 2.13 | `fitz` y `PIL` se importan dentro del método que los usa. |

### `core/database.py`, `core/auto_match.py`, `core/orchestrator.py`

| Fichero | Línea | Ref | Qué cambió |
|---|---|---|---|
| `core/database.py` | 17-18 | 2.13 | Cliente y embeddings vía `store_client`. |
| `core/auto_match.py` | 50, 80 | 2.13 | Ídem. |
| `core/orchestrator.py` | 22 | 2.13 | Ídem. |

### `views/dashboard.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 7 | 2.2 | Importa `get_ai_provider`; ya no importa proveedores concretos. |
| 47 | 2.9 | El formulario distingue bloqueo de credencial incorrecta. |
| 84 | N3 | Distingue «⚠️ Expirada» de «⏳ Último día». |
| 126, 165 | 2.2 | Los dos `if AI_PROVIDER_TYPE` pasan a `get_ai_provider()`. |
| 231, 257 | 2.1 | `/match:` y búsqueda libre pasan `vacante=`. |
| 292 | 2.1 | Muestra la línea de `explicar()`, que se calculaba y se tiraba. |
| 301 | 2.1 | La etiqueta sigue a `tipo_puntuacion`: «Afinidad» o «Similitud». |

### `views/portal.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 8 | 2.2 | Importa `get_ai_provider`. |
| 15-22 | 2.2 | Se elimina `_instanciar_proveedor()`, que devolvía `None` ante un valor desconocido. |
| 99, 209 | 2.2 | Las dos construcciones usan el composition root. |

### `views/components.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 18 | 2.7 | `obtener_resumen_silos()` delega en el dominio (35 líneas → 1). |
| 81 | 2.13 | Cliente vía `store_client`. |

### `app.py`

| Línea | Ref | Qué cambió |
|---|---|---|
| 23 | 2.9 | `inicializar_seguridad()`: crea la base de usuarios y valida la clave. |
| 24 | 2.4 | `verificar_proveedor()`: valida la credencial del proveedor. |

### `.env.example` · `.gitignore` · `.gitattributes`

| Fichero | Qué cambió |
|---|---|
| `.env.example` | Documenta las siete variables de seguridad nuevas. |
| `.gitignore` | Acota el repositorio a código y configuración; `!/README.md` anclado a la raíz. |
| `.gitattributes` | Normalización de finales de línea a LF. |

---

## 3. Tests

**Ficheros nuevos** (63 tests):

| Fichero | Tests | Cubre |
|---|---|---|
| `tests/unit/test_security.py` | 19 | 2.9, N1, N2. Dos regresiones escritas contra los secretos concretos que llegaron a estar en el código. |
| `tests/unit/test_filtro_lexico.py` | 22 | 2.12. «R», «Go», «SQL», «Java» y los nombres con símbolos. |
| `tests/unit/test_vacancy_catalog.py` | 16 | 2.7, N3. Dos miden el coste contando lecturas sobre un doble. |
| `tests/unit/test_query_translator_seguridad.py` | 10 | 2.11. Saneo y forma de lo que llega al modelo. |

**Ficheros modificados**:

| Fichero | Qué cambió |
|---|---|
| `tests/unit/test_settings.py` | Dos tests **afirmaban los defectos** como comportamiento esperado (el relleno de la clave y `DEBUG_MODE is True`). Reescritos en sentido contrario. |
| `tests/unit/test_providers.py` | +8 tests: requisitos del proveedor, y una regresión que analiza el **AST** de `views/` para que ninguna vista vuelva a decidir el proveedor. |
| `test_search_rerank`, `test_busqueda_identidad`, `test_auto_match`, `test_vacancy_catalog` | Parchean `store_client` en lugar de `chromadb`. |
| `test_vacancy_embedding_coherence` | Se elimina el `chromadb` falso que fabricaba en `sys.modules`. |
| `test_extractor_temp_files`, `test_provider_observability_init` | `pytest.importorskip`: se saltan limpiamente si falta el paquete, en vez de reventar en la recolección. |

---

## 4. Correcciones al documento de traspaso

Tres afirmaciones de `ESTADO_PROYECTO.md` no se sostienen al contrastarlas.

**§2.8 — El corte de pertinencia no puede encoger el resultado.** ChromaDB
devuelve los vecinos ordenados por distancia ascendente, y el corte es
`similitud < base − MARGEN`, equivalente a `distancia > 1 − base + MARGEN`: un
umbral **monótono sobre la misma clave que ya ordena la lista**. Por tanto
elimina siempre un sufijo, y no puede haber candidatos válidos más abajo que
reponer. Además solo se activa en la bolsa global, donde devolver menos de
`limit` es el comportamiento buscado. **No se tocó nada.**

**§4 — La deuda de finales de línea era un índice sucio, no el repositorio.** El
commit de normalización cambió solo `.gitattributes`, tres líneas. Si hubiera
habido 30 ficheros con CRLF en el índice, `git add --renormalize .` los habría
reescrito todos. Los «4046 insertions / 4049 deletions» eran el residuo de un
`git add --renormalize .` de una sesión anterior que quedó preparado sin
commitear.

**§2.7 — La mitad del reproche.** El coste era real. Que el sidebar «no descarte
expiradas» **es deliberado y correcto**: los candidatos de una vacante cerrada
siguen ahí, y ocultárselos al reclutador sería esconderle sus propios datos. Lo
que sí faltaba es que la diferencia con el portal estuviera decidida por alguien.

---

## 5. Defecto 2.6 — PDFs huérfanos · corregido

**No tenía nada que ver con documentación.** Eran ficheros PDF sueltos en
`storage/cv_files/` del disco duro.

**No confundir con el defecto de las imágenes temporales, que sí estaba
resuelto.** `pdf_to_images` escribía `temp_page_N.png` con nombre fijo y dos
postulaciones simultáneas se pisaban las páginas; se arregló con un directorio
por invocación (`core/extractor.py:42`). Aquel afectaba a los **PNG derivados**;
este, al **PDF original**, y seguía abierto.

### Qué pasaba

`extract_candidate` copiaba el PDF a la carpeta **definitiva** antes de que el
candidato confirmase en la fase 2 del portal. Si abandonaba ahí, el fichero
quedaba en disco sin ningún registro que lo referenciase. Y
`_reiniciar_postulacion()` limpiaba el estado de sesión sin borrarlo.

El directorio crecía sin techo, y —lo que más pesa— se retenían currículums con
datos personales de personas que **decidieron no postularse**.

### Qué se hizo

| Línea | Qué cambió |
|---|---|
| `core/orchestrator.py:19` | `PREFIJO_PENDIENTE`: el estado se lee de la ruta, sin bandera aparte que desincronizar. |
| `core/orchestrator.py:24` | `_es_pendiente()`. |
| `core/orchestrator.py:29` | `persistir_pdf()`: traslada al almacén, **idempotente**. |
| `core/orchestrator.py:49` | `descartar_extraccion()`: borra la copia de trabajo. |
| `core/orchestrator.py:173` | La copia va a `tempfile.mkdtemp()`, no a `storage/`. |
| `core/orchestrator.py:237` | `register_candidate` persiste **antes** de indexar, para que la ruta que viaja a los metadatos sea la final. |
| `views/portal.py:31` | `_reiniciar_postulacion()` descarta también el fichero. |

La invariante que ahora se cumple: **`storage/cv_files/` solo contiene
postulaciones confirmadas**. Y si alguien cierra la pestaña sin tocar nada, lo
que queda es un temporal del sistema operativo —que el propio SO recicla— en vez
de un residuo permanente de la aplicación.

Cubierto por `tests/unit/test_pdf_pendientes.py`, 15 tests.

---

## 6. Lo que queda abierto

### 2.13 — Cobertura de `views/` y flujo end-to-end

La parte de hermeticidad está resuelta. Lo que sigue sin cubrir son las pruebas
de interfaz: requieren el arnés `streamlit.testing.v1.AppTest` y conviene
abordarlas después de la Fase 0, cuando el almacén sea sustituible por un doble
completo. Hoy existe una salvaguarda parcial: el test de AST sobre `views/` en
`tests/unit/test_providers.py`.
