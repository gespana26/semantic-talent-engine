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

---

## Puesta en marcha

```bash
# 1. Clonar y crear el entorno virtual
git clone <repo-url>
cd semantic-talent-engine
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate    # Linux / macOS

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar el entorno
copy .env.example .env         # cp en Linux / macOS
#   Editar .env con la API key de OpenAI o la configuración de Ollama

# 4. Ejecutar la aplicación web
streamlit run app.py
#   Interfaz por línea de comandos alternativa:
python main.py
```

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
