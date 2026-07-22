# Semantic Talent Engine

Sistema de seguimiento de candidatos (*Applicant Tracking System*) que empareja
vacantes y candidatos por el significado de su experiencia y no por la
coincidencia exacta de palabras. Procesa los currículums en PDF interpretando
cada página como imagen —sin depender de la extracción de texto, que se rompe
ante diseños a dos columnas o documentos exportados como imagen— y permite al
reclutador buscar en lenguaje natural.

Proyecto desarrollado como Trabajo de Fin de Máster del Máster en IA Generativa
(EBIS). Autores: Juan Camilo Pedraza y Gustavo España Paz. Python 3.12.

---

## Qué resuelve

Los sistemas tradicionales funcionan con filtros exactos: una búsqueda de «5 años
de experiencia en Python» descarta al candidato que escribió «5 años liderando
equipos con Django», y el reclutador termina revisando los CV a mano. El proyecto
aborda tres problemas de raíz:

| Problema | Solución |
|---|---|
| Los PDF con maquetas complejas rompen los extractores de texto | Cada página se convierte a imagen y se procesa con un modelo multimodal de visión y lenguaje |
| La búsqueda por palabras clave ignora el contexto | Recuperación vectorial en ChromaDB y una afinidad calculada por componentes verificables |
| Las vacantes se duplican y los datos quedan aislados | Conciliación semántica de vacantes y doble indexación: silo de la vacante más bolsa de talento global |

---

## Técnica utilizada

**Extracción multimodal.** El PDF se rasteriza con PyMuPDF y cada página se envía
como imagen a un modelo de visión y lenguaje (GPT-4o-mini en la nube, o Qwen2.5-VL
/ Gemma 3 en local a través de Ollama), que devuelve un perfil estructurado
validado con Pydantic en la frontera entre la IA y la lógica de negocio.

**Recuperación y re-puntuado.** La consulta se vectoriza con `nomic-embed-text` y
ChromaDB recupera los currículums más próximos. El orden vectorial no es la
puntuación final: decide a quién se evalúa, y sobre esa ventana se calcula la
afinidad compuesta.

```
Similitud normalizada = (Similitud − Línea base) / (1 − Línea base)
Afinidad (%) = (0,75 · Cobertura de requisitos + 0,25 · Similitud normalizada)
               × Factor de experiencia × Factor de profesión × 100
```

La **cobertura de requisitos** es la señal principal porque es la única cuya
escala tiene un cero real; la similitud desempata entre quienes cumplen lo mismo.
La **línea base** es la similitud que alcanza un perfil de un ámbito ajeno, medida
por vacante y descontada para que el cero de la escala signifique «sin relación».
Los dos factores multiplican en lugar de sumar: un requisito no se compensa
cumpliendo otra cosa.

**Alerta de auto-match.** Al completarse una postulación, un hilo en segundo plano
evalúa el perfil contra la vacante y avisa al reclutador por correo cuando el
candidato cubre los requisitos exigidos y destaca dentro del banco de talento. La
decisión se apoya en la cobertura y en el percentil del candidato, no en un umbral
fijo de porcentaje.

**Verificación del perfil contra el documento.** Las habilidades que devuelve el
modelo se contrastan con el texto visible del CV por un segundo canal en cascada:
la capa de texto del PDF (PyMuPDF) o, para documentos exportados como imagen, OCR
opcional (`rapidocr-onnxruntime`). La extracción de ese texto corre en paralelo
con la llamada al LLM, así que no añade latencia percibida. Un perfil cuyas
habilidades no aparecen escritas en el documento, o que contiene patrones de
instrucciones dirigidas al modelo (*prompt injection*), se indexa igualmente pero
queda marcado como sospechoso en sus metadatos y dispara un correo de revisión
manual al reclutador. El sistema nunca descarta solo: hace visible la sospecha
para que la decisión sea humana. Los system prompts de extracción incluyen además
la regla explícita de tratar el contenido del documento como datos y no como
instrucciones.

---

## Requisitos previos

| Requisito | Versión | Verificación |
|---|---|---|
| Python | 3.12 o superior | `python --version` |
| pip | — | `pip --version` |
| Git | cualquiera | `git --version` |
| Ollama | última | `ollama --version` |

**Ollama** es necesario para los *embeddings* (`nomic-embed-text`) y opcional como
proveedor de IA multimodal:

```bash
# 1. Descargar desde https://ollama.com/download e instalar
ollama --version

# 2. Descargar los modelos necesarios
ollama pull nomic-embed-text
ollama pull gemma3:12b        # proveedor local multimodal
# o, alternativamente:
ollama pull qwen2.5-vl:7b

# 3. Verificar que está corriendo
ollama list
```

---

## Puesta en marcha

```bash
# 1. Clonar y crear el entorno virtual
git clone https://github.com/jpcamilo/semantic-talent-engine.git
cd semantic-talent-engine
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux / macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar el entorno (ver sección «Configuración»)
copy .env.example .env         # cp en Linux / macOS

# 4. Ejecutar
streamlit run app.py           # interfaz web (recomendada) → http://localhost:8501
python main.py                 # interfaz por línea de comandos (alternativa)
```

Credenciales iniciales del dashboard: usuario `admin`, contraseña `admin123` (se
cambian editando el hash en `usuarios.db`).

---

## Configuración (`.env`)

Copiar la plantilla y editarla con las credenciales reales:

```bash
cp .env.example .env
```

```bash
# Proveedor de IA: "openai" o "ollama"
AI_PROVIDER_TYPE=openai

# Si se usa OpenAI (requerido para AI_PROVIDER_TYPE=openai)
OPENAI_API_KEY=sk-proj-tu-api-key-aqui
MODEL_NAME=gpt-4o-mini

# Si se usa Ollama (requerido para AI_PROVIDER_TYPE=ollama)
# MODEL_NAME=gemma3:12b

# Email (opcional — alertas de talento)
# EMAIL_SENDER_USER=tu_correo@gmail.com
# EMAIL_SENDER_PASSWORD=tu_app_password_de_16_caracteres
# EMAIL_RECRUITER_TARGET=reclutador@empresa.com

# Observabilidad LLM (opcional)
# LANGFUSE_ENABLED=True
# LANGFUSE_HOST=http://localhost:3000
# LANGFUSE_PUBLIC_KEY=pk-lf-...
# LANGFUSE_SECRET_KEY=sk-lf-...

# Verificación de skills contra el documento (anti-inyección; opcional)
# VERIFICACION_SKILLS_HABILITADA=True
# UMBRAL_SKILLS_VERIFICADAS=0.5

# Debug
DEBUG_MODE=False

# Seguridad (cambiar en producción)
# JWT_SECRET_KEY=tu_clave_secreta_personalizada
```

Cómo obtener las credenciales:

- **OpenAI API Key**: registrarse en <https://platform.openai.com> → *API Keys* →
  *Create new secret key*. Requiere un método de pago con crédito.
- **Gmail App Password**: activar la verificación en dos pasos en la cuenta de
  Google → *Contraseñas de aplicación* → generar para «Correo».
- **Langfuse**: opción A (self-hosted): `docker compose up` desde
  <https://github.com/langfuse/langfuse>; opción B (cloud):
  <https://cloud.langfuse.com>.

---

## Proveedores de IA

La capa cognitiva está abstraída tras la interfaz `BaseLLMProvider`. El proveedor
se elige en `.env` y la lógica de negocio no cambia; añadir uno nuevo es registrar
una clase en `config/providers.py`.

| Proveedor | Variable `.env` | Requisito |
|---|---|---|
| OpenAI (GPT-4o-mini) | `AI_PROVIDER_TYPE=openai` | Clave de API |
| Ollama local (Qwen2.5-VL / Gemma 3) | `AI_PROVIDER_TYPE=ollama` | Ollama en `localhost:11434` con `nomic-embed-text` y un modelo multimodal |

La decisión de proveedor se resuelve en un único punto de composición por
inyección de dependencias, sin ramificaciones dispersas por el código.

---

## Uso

**Portal del candidato (pestaña 🎓).** El candidato elige la vacante en el
desplegable (opcional) y adjunta su CV en PDF; al pulsar «Analizar Currículum» el
sistema copia el PDF a `storage/cv_files/`, extrae el perfil con IA multimodal y
lo muestra para su revisión, sin indexarlo todavía. Tras confirmar los datos de
contacto y enviar la postulación, el perfil se indexa en la vacante objetivo (si
se indicó) y en la bolsa global, y el auto-match se evalúa en segundo plano.

**Dashboard del reclutador (pestaña 🏢).** Se inicia sesión (JWT válido 8 horas) y
se busca en lenguaje natural desde el chat; las palabras `OBLIGATORIO`/`DEBE TENER`
y `EXCLUYENTE` fuerzan filtros sobre términos concretos. El panel lateral lista los
silos de vacantes activas con sus días restantes y permite acotar la búsqueda a una
vacante. Cada resultado muestra nombre, contacto, extracto, afinidad porcentual y
su desglose, con un modal de perfil completo. En modo depuración
(`DEBUG_MODE=True`) un *expander* muestra la estructura interna del QueryTranslator.

| Comando | Función | Ejemplo |
|---|---|---|
| `/crear vacante:` | Registrar una nueva vacante | `/crear vacante: Ingeniero Civil con experiencia en obras viales y AutoCAD` |
| `/match:` | Auto-match de candidatos contra la vacante del silo actual | `/match:` |
| `/nombre:` | Búsqueda directa por nombre o correo | `/nombre: Luis` · `/nombre: luis@gmail.com` |
| Texto libre | Búsqueda semántica con filtros opcionales | `project manager OBLIGATORIO con experiencia en metodologías ágiles` |

**Verificación rápida del funcionamiento:**

1. Abrir <http://localhost:8501>.
2. En «Dashboard del Reclutador», iniciar sesión con `admin` / `admin123`.
3. Crear una vacante de prueba: `/crear vacante: Ingeniero de Software Senior. 5+ años en Python, Django, PostgreSQL y AWS; experiencia liderando equipos; inglés avanzado.`
4. Verificar que aparece el mensaje de éxito y el JSON extraído.
5. En «Portal del Candidato», subir un CV en PDF (usar los de la carpeta `CV/`).
6. Volver al Dashboard y buscar: `Ingeniero de Software con Python y AWS`.
7. Verificar que aparecen resultados con porcentaje de afinidad.

---

## Arquitectura

El proyecto sigue una arquitectura en capas con dependencias en un solo sentido:
la interfaz depende del dominio, y el dominio de las abstracciones de
infraestructura, nunca al revés.

```
┌──────────────────────────────────────────────────────────────┐
│  Interfaces (views/, main.py)                                 │
│  Portal del candidato · Dashboard del reclutador (JWT) · CLI   │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────┐
│  Orquestación (core/orchestrator.py)                          │
│  VacancyOrchestrator     · ingesta, TTL, conciliación          │
│  CandidateOrchestrator   · postulación, doble indexación,      │
│                            auto-match en segundo plano         │
└───────────────────────────────┬──────────────────────────────┘
                                │
┌──────────────┬────────────────┼─────────────────┬────────────┐
│ Proveedor IA │  Motor de       │  Almacén         │  Seguridad  │
│ (models/)    │  búsqueda       │  vectorial       │  (core/)    │
│              │  (core/)        │  (ChromaDB)      │             │
│ OpenAI /     │  Afinidad por   │  Silo de vacante │  JWT +      │
│ Ollama       │  componentes    │  + bolsa global  │  bcrypt     │
│ Extracción   │  Cobertura de   │                  │             │
│ multimodal   │  requisitos     │                  │             │
└──────────────┴─────────────────┴─────────────────┴────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Servicio de correo    │
                    │  (SMTP) · alerta de    │
                    │  auto-match            │
                    └───────────────────────┘
```

**Principio arquitectónico:** los orquestadores dependen de la interfaz
`BaseLLMProvider`, no de una implementación concreta. Cambiar de OpenAI a Ollama
es cambiar una variable de entorno, sin tocar la lógica de negocio.

---

## Estructura del proyecto

```
config/     Configuración por variables de entorno y composition root de proveedores
core/       Lógica de dominio: afinidad, cobertura, búsqueda, auto-match, base vectorial
models/     Interfaz de proveedor, esquemas Pydantic y observabilidad
views/      Interfaces Streamlit: portal del candidato y dashboard del reclutador
scripts/    Scripts de medición y utilidades (línea base, discriminación, reproducibilidad)
tests/      Suite unitaria con pytest
```

---

## Prompts clave

Los prompts completos viven en el código; a continuación, su función y parámetros.

- **Extracción multimodal — OpenAI** (`models/ai_provider.py`): parser de visión
  para CVs. Mecanismo `beta.chat.completions.parse` con
  `response_format=CandidateStructure`; el esquema Pydantic fuerza la estructura de
  salida del lado del servidor.
- **Extracción multimodal — Ollama** (`models/ai_provider.py`): extractor que
  devuelve exclusivamente un JSON válido con el esquema `CandidateStructure`,
  saneado con `core/json_sanitizer.py` y validado con `model_validate_json`.
  Parámetros: `num_ctx=8192`, `temperature=0.0`, `num_predict=-1`.
- **Traducción NLI → filtro ChromaDB — QueryTranslator** (`core/query_translator.py`):
  few-shot con 3 ejemplos anotados; convierte la petición en lenguaje natural en una
  consulta estructurada (`ChromaQueryStructure`: `query_text_conceptual` para la
  búsqueda vectorial y `where_filter` con el operador `$contains`), que se evalúa
  en Python con lógica *fail-closed*. Usa `complete_json` (`format="json"` en
  Ollama, `response_format=json_object` en OpenAI).
- **Conciliación semántica de vacantes**: mapea un título nuevo a una colección
  existente de producción o devuelve `"NUEVA"` para registros netamente nuevos;
  `temperature=0.0`.

---

## Calidad de código

El linting se realiza con **Ruff**, configurado en `pyproject.toml` (reglas de
Pyflakes, pycodestyle e isort). Verificación:

```bash
pip install -r requirements-dev.txt
ruff check .          # linting; el proyecto pasa sin avisos
pytest tests/ -q      # suite unitaria
```

Los tests se ejecutan sin dependencias externas: ChromaDB, OpenAI y Ollama se
sustituyen por dobles, de modo que la suite es determinista y rápida.

---

## Observabilidad

La integración opcional con **Langfuse** registra trazas de las llamadas al
modelo, costes y tiempos, y enmascara los datos personales antes de enviarlos
(`mask_pii` a nivel de SDK). Se activa con `LANGFUSE_ENABLED=True` y las claves
correspondientes; si no está configurada, el sistema funciona sin ella.

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| `ConnectionError` al iniciar | Ollama no está corriendo | Ejecutar `ollama serve` en otra terminal |
| Error `does not exist` en búsqueda | El silo de vacante no fue creado | Usar `/crear vacante:` primero, o dejar el campo *Silo* en blanco para búsqueda global |
| `OPENAI_API_KEY` no funciona | Key inválida o sin crédito | Verificar en <https://platform.openai.com/usage> |
| El CV no se procesa | PDF corrupto o protegido | Probar con otro PDF; verificar que no tenga contraseña |
| Error de tensor en Ollama | Dimensiones de imagen incompatibles con Qwen2.5-VL | El `CVImageExtractor` ya aplica el parche de múltiplos de 28; si persiste, verificar la versión de Ollama |
| Langfuse no inicializa | Claves faltantes o host inaccesible | El sistema se degrada silenciosamente; revisar los logs por *warnings* |

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.12 |
| Interfaz web | Streamlit |
| Base vectorial | ChromaDB (índice HNSW, distancia coseno) |
| Extracción de PDF | PyMuPDF |
| Procesamiento de imagen | Pillow |
| Modelos de IA | OpenAI GPT-4o-mini · Ollama (Qwen2.5-VL / Gemma 3) |
| Embeddings | nomic-embed-text |
| Validación de datos | Pydantic |
| Autenticación | PyJWT · bcrypt · SQLite |
| Correo | smtplib (SMTP) |
| Observabilidad | Langfuse |
| Linting | Ruff |
| Pruebas | pytest |
| Configuración | python-dotenv |
