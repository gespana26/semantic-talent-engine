# Bitácora de Cambios (Changelog) - TFM ATS Global Recruitment

## [Versión 1.1.0] - 2026-06-23
### Añadido
- **Interfaz Gráfica (GUI):** Migración iniciada del modelo CLI (Consola) a una aplicación web interactiva utilizando el framework Streamlit (`app.py`).
- **Omnibox Conversacional:** Implementación de una barra de búsqueda universal para el reclutador capaz de procesar tanto lenguaje natural como Comandos de Barra (Slash Commands).
- **Búsqueda Nominal (Bypass IA):** Nuevo método en `search_engine.py` para interceptar comandos `/nombre` y ejecutar búsquedas léxicas exactas sin consumir tokens del motor vectorial.

### Cambiado
- **Arquitectura de Búsqueda Híbrida:** Transición de un modelo de "Pre-Retrieval Filtering" (usando el `$contains` de ChromaDB) a un modelo de "Post-Retrieval Filtering" utilizando una evaluación léxica nativa en Python (`_evaluar_filtro_python`) para resolver la ceguera del motor ante subcadenas.
- **Visibilidad de Datos (Transparencia IA):** Modificación del `VacancyOrchestrator` para que retorne el `model_dump()` del Pydantic Schema, permitiendo al usuario ver exactamente qué entendió la IA al ingestar una vacante.

### Arreglado
- **Excepción de Atributo Faltante:** Resolución del quiebre en la tubería multimodal (`meses_duracion`) mediante la implementación de extracción defensiva (`getattr`) en la capa de persistencia (`database.py`).
- **Sesgo de Instrucción en Pydantic:** Ajuste en el prompt del `nivel_academico_maximo` dentro de `schemas.py` para forzar la extracción literal del título y evitar traducciones categóricas que rompían los cruces relacionales.

### Planeado (Próximos Pasos)
- Desarrollo del Portal del Candidato (Formulario + Carga de PDF) en Streamlit.
- Implementación de seguridad Stateless (JWT + Base de datos local SQLite) para el dashboard del reclutador.


# Bitácora de Cambios (Changelog) - TFM ATS Global Recruitment

## [Versión 1.2.0 - Release Candidate] - 2026-06-24
### Añadido
- **Ventanas Modales (UI):** Implementación de la directiva `@st.dialog` de Streamlit para la exploración de perfiles completos de candidatos sin perder el contexto de la búsqueda actual en el Dashboard del Reclutador.
- **Diseño de Interfaz "LinkedIn-Style":** Reemplazo de JSON crudo por una grilla analítica estructurada con métricas clave, etiquetas visuales (pills) para habilidades y acordeones expansibles para el historial laboral.
- **Portal del Candidato (End-to-End):** Activación completa de la pestaña web de postulación. Soporta carga de archivos PDF, persistencia física en disco local y ejecución concurrente del *pipeline* multimodal de Inteligencia Artificial (Doble Indexación).

### Cambiado
- **Componentización UI (Arquitectura DRY):** Abstracción de la interfaz de currículums en un componente centralizado (`render_grilla_perfil`) para garantizar simetría visual y reutilización de código entre el portal del candidato y el dashboard del reclutador.
- **Estandarización PEP 8:** Limpieza y reorganización de importaciones globales en `app.py` para cumplir con las mejores prácticas de Python y mejorar la mantenibilidad del código fuente.

### Arreglado
- **Tolerancia a Fallos en Mapeo JSON:** Corrección de la desconexión entre el Front-End y el Back-End implementando una búsqueda dinámica de llaves retrocompatibles (`historial_laboral` vs `experiencia_laboral`, `duracion_anios` vs `meses_duracion`).
- **Conflicto de Instanciación en Orquestador:** Resolución del error de parámetros no reconocidos (`collection_name`), permitiendo que el `CandidateOrchestrator` opere correctamente sin alterar su arquitectura nativa de ruteo y Doble Indexación.
- **Blindaje de Formularios Vacíos:** Implementación de programación defensiva para evitar excepciones cuando la capa web no provee datos complementarios (ej. teléfono), inyectando variables por defecto (`"0000"`) para asegurar la persistencia en disco.

### Planeado (Próximos Pasos)
- Implementación de seguridad Stateless (JWT + Base de datos local SQLite) para el dashboard del reclutador.
---
# Bitácora de Cambios (Changelog) - TFM ATS Global Recruitment

## [Versión 1.3.0] - 2026-06-25
### Añadido
- **Módulo UI de Creación de Vacantes:** Implementación de ventana modal (`@st.dialog`) en el Dashboard del Reclutador para ingestar texto de nuevas vacantes, conectado directamente al `VacancyOrchestrator` y la inyección dinámica de IA.
- **Motor de Visibilidad TTL (Time-to-Live):** Nueva función centralizada (`obtener_resumen_silos`) que consulta la base de datos vectorial ChromaDB, extrae el `timestamp_expiracion` de los metadatos y calcula matemáticamente los días de vigencia restantes.
- **Tablero de Anuncios (Job Board):** Inyección de un panel lateral en el Portal del Candidato que expone las vacantes activas y sus días restantes, mejorando la experiencia del postulante.

### Cambiado
- **Arquitectura de Navegación (Split-Screen):** Eliminación del `st.sidebar` global a favor de un diseño de columnas internas (`st.columns`). Esto encapsula los controles administrativos estrictamente dentro de la vista del reclutador.
- **Refinamiento UI/UX en Métricas:** Reemplazo de componentes `st.metric` por tarjetas personalizadas (`st.container(border=True)`) para estandarizar el tamaño de fuente. 
- **Gestión de Datos Legacy:** Traducción de valores matemáticos nulos o infinitos ("∞") en silos antiguos a lenguaje natural humano ("⏳ Abierta (Sin fecha límite)").

### Arreglado
- **Fuga de Controles de Administración (Security/UI):** Solucionado el error arquitectónico de Streamlit donde el candidato podía visualizar y acceder al botón de "Crear Nueva Vacante".
- **Blindaje de Interfaz (Defensive UI):** Implementación de bloques `try/except` envolventes en el renderizado visual de los menús laterales para prevenir caídas de la aplicación por fallos de conexión a la base de datos local.

### Planeado (Próximos Pasos)
- Implementación de capa de seguridad Stateless (JWT + Base de datos local SQLite) para restringir el acceso al Dashboard del Reclutador.

---
## [Versión 1.3.0] - 2026-06-25
### Añadido
- **Módulo UI de Creación de Vacantes:** Implementación de ventana modal (`@st.dialog`) en el Dashboard del Reclutador para ingestar texto de nuevas vacantes, conectado directamente al `VacancyOrchestrator` y la inyección dinámica de IA.
- **Motor de Visibilidad TTL (Time-to-Live):** Nueva función centralizada (`obtener_resumen_silos`) que consulta la base de datos vectorial ChromaDB, extrae el `timestamp_expiracion` de los metadatos y calcula matemáticamente los días de vigencia restantes.
- **Tablero de Anuncios (Job Board):** Inyección de un panel lateral en el Portal del Candidato que expone las vacantes activas y sus días restantes, mejorando la experiencia del postulante.

### Cambiado
- **Arquitectura de Navegación (Split-Screen):** Eliminación del `st.sidebar` global a favor de un diseño de columnas internas (`st.columns`). Esto encapsula los controles administrativos estrictamente dentro de la vista del reclutador.
- **Refinamiento UI/UX en Métricas:** Reemplazo de componentes `st.metric` por tarjetas personalizadas (`st.container(border=True)`) para estandarizar el tamaño de fuente. 
- **Gestión de Datos Legacy:** Traducción de valores matemáticos nulos o infinitos ("∞") en silos antiguos a lenguaje natural humano ("⏳ Abierta (Sin fecha límite)").

### Arreglado
- **Fuga de Controles de Administración (Security/UI):** Solucionado el error arquitectónico de Streamlit donde el candidato podía visualizar y acceder al botón de "Crear Nueva Vacante".
- **Blindaje de Interfaz (Defensive UI):** Implementación de bloques `try/except` envolventes en el renderizado visual de los menús laterales para prevenir caídas de la aplicación por fallos de conexión a la base de datos local.


## [Versión 1.4.0 - Clean Architecture & Security] - 2026-06-26
### Añadido
- **Seguridad Stateless (JWT + SQLite):** Implementación de motor criptográfico en `core/security.py` utilizando *Bcrypt* y *JSON Web Tokens*. Protege el Dashboard del Reclutador requiriendo autenticación y emitiendo un token en memoria (`st.session_state`) con 8 horas de vigencia.
- **Notificaciones Proactivas (Fire-and-Forget):** Desarrollo del módulo `core/email_service.py` (SMTP/HTML). Si un candidato supera el 85% de afinidad (*match*), el sistema alerta automáticamente al reclutador por correo electrónico.
- **Procesamiento Asíncrono (Multithreading):** Integración de hilos en segundo plano (`threading.Thread`) tanto en la web (`portal.py`) como en la CLI (`cli_console.py`) para ejecutar cruces matemáticos RAG y enviar correos sin bloquear la interfaz del candidato.
- **Clean Architecture (Modularización):** Creación del directorio `views/` (`components.py`, `portal.py`, `dashboard.py`) para erradicar el antipatrón de *God Object*, separando la lógica visual por dominio.

### Cambiado
- **Refactorización del Core UI:** Reducción del archivo monolítico `app.py` a un simple enrutador de vistas (Router), delegando responsabilidades a módulos especializados para mejorar la mantenibilidad y escalabilidad.
- **Estandarización ChatOps:** Unificación de la sintaxis en la interfaz conversacional del Omnibox. Todos los comandos rápidos ahora exigen el sufijo de dos puntos (ej. `/crear vacante:`, `/match:`, `/nombre:`) e incluyen validaciones defensivas.
- **Prompt Engineering Defensivo (Zero-Loss):** Ajuste en las reglas críticas del *System Prompt* en `query_translator.py` para forzar a la IA a conservar el texto íntegro de profesiones o *skills* compuestas (ej. "Ingeniero Industrial"), evitando resúmenes semánticos destructivos.

### Arreglado
- **Filtro Omnidireccional (Síndrome IA Estricta):** Refactorización de la función `_evaluar_filtro_python` en `search_engine.py` para evaluar coincidencias léxicas aplanando todo el JSON del candidato. Esto permite restaurar el umbral matemático (`UMBRAL_MAXIMO_DISTANCIA = 1.2`) garantizando alta precisión RAG y cero descartes por errores de categorización de la IA.
- **Regresión Visual de UI:** Eliminación definitiva de fragmentos de código legacy que causaban la reaparición no deseada del panel *Job Board* en la vista central del candidato.