# Semantic Talent Engine

ATS (*Applicant Tracking System*) inteligente con interfaz web (Streamlit) impulsado por IA multimodal. Automatiza el matching entre vacantes y candidatos usando búsqueda semántica sobre vectores, procesa documentos PDF reales —no formularios planos— y alerta por email cuando detecta talento de alto ajuste.

Proyecto desarrollado como Trabajo de Fin de Máster (TFM).

---

## Qué resuelve

Los ATS tradicionales funcionan con filtros exactos: pedís "5 años de experiencia en Python" y perdés al candidato que escribió "5+ años liderando equipos con Django". El reclutador termina haciendo el trabajo real fuera del sistema.

Semantic Talent Engine ataca tres problemas de raíz:

| Problema | Cómo lo resuelve |
|---|---|
| PDFs con layouts complejos que rompen los parsers de texto | Convierte cada página a imagen de alta resolución y la procesa con un modelo multimodal (visión + lenguaje) |
| Búsqueda por keywords que ignora el contexto semántico | Embeddings vectoriales en ChromaDB con cálculo de porcentaje de afinidad real |
| Duplicación de vacantes y silos de datos desconectados | Conciliación semántica de identidades y estrategia de doble indexación (silo de vacante + bolsa global) |

---

## Quick start

```bash
# 1. Clonar y crear entorno virtual
git clone https://github.com/jpcamilo/semantic-talent-engine.git
cd semantic-talent-engine
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar el entorno
cp .env.example .env
# Editar .env con tu OPENAI_API_KEY, credenciales de email, etc.

# 4. Ejecutar la app web
streamlit run app.py
```

**Acceso inicial al dashboard**: usuario `admin` / contraseña `admin123` (cambiala apenas entres).

---

## Configuración del entorno (`.env`)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `AI_PROVIDER_TYPE` | Sí | `openai` o `ollama` |
| `OPENAI_API_KEY` | Con OpenAI | Tu API key de OpenAI |
| `MODEL_NAME` | No | Modelo a usar (default: `gpt-4o-mini`) |
| `DEBUG_MODE` | No | `True` conserva imágenes temporales y activa telemetría |
| `EMAIL_SENDER_USER` | No | Correo Gmail para enviar alertas de talento |
| `EMAIL_SENDER_PASSWORD` | No | App password de Gmail |
| `EMAIL_RECRUITER_TARGET` | No | Correo del reclutador que recibe las alertas |
| `JWT_SECRET_KEY` | No | Clave para firmar tokens JWT |
| `LANGFUSE_ENABLED` | No | `True` activa el tracing de llamadas LLM |
| `LANGFUSE_HOST` | Con Langfuse | `http://localhost:3000` (self-hosted) o `https://cloud.langfuse.com` |
| `LANGFUSE_PUBLIC_KEY` | Con Langfuse | Clave pública de tu proyecto Langfuse |
| `LANGFUSE_SECRET_KEY` | Con Langfuse | Clave secreta de tu proyecto Langfuse |

---

## Proveedores de IA soportados

El sistema abstrae completamente la capa cognitiva. Elegís el proveedor en el archivo `.env` y el código de negocio no cambia.

| Proveedor | Variable `.env` | Requisito |
|---|---|---|
| OpenAI (GPT-4o-mini) | `AI_PROVIDER_TYPE=openai` | API key |
| Ollama local (Gemma) | `AI_PROVIDER_TYPE=ollama` | Ollama corriendo en `localhost:11434` |

El switch de proveedor se resuelve en tiempo de ejecución por inyección de dependencias —no hay ifs dispersos por el código—.

---

## Arquitectura

```
┌──────────────────────────────────────────────────────────┐
│                   INTERFAZ WEB (Streamlit)                │
│  ┌─────────────────────┐  ┌──────────────────────────┐   │
│  │  Portal Candidato   │  │  Dashboard Reclutador 🔒  │   │
│  │  Postulación + CV    │  │  Búsqueda + Silos + Email │   │
│  └─────────┬───────────┘  └────────────┬─────────────┘   │
└────────────┼──────────────────────────┼─────────────────┘
             │                            │
┌────────────▼────────────────────────────▼─────────────────┐
│                    Core Orchestrators                      │
│  VacancyOrchestrator       │  CandidateOrchestrator        │
│  - Ingesta + TTL           │  - Postulación                │
│  - Conciliación semántica  │  - Doble indexación           │
│                             │  - Auto-match background      │
└──────┬─────────────────────┴──────────┬───────────────────┘
       │                                  │
┌──────▼──────┐  ┌──────────┐  ┌─────────▼────────┐  ┌──────────────┐
│ AI Provider │  │  Search   │  │  Vector Store    │  │  Security    │
│ (models/)   │  │  Engine   │  │  (ChromaDB)      │  │  (JWT+bcrypt)│
│             │  │           │  │                  │  │              │
│ OpenAI/     │  │ Afinidad  │  │  Silo + Global   │  │  Login        │
│ Ollama      │  │ Híbrida   │  │  Pool            │  │  reclutador   │
│ Extracción  │  │           │  │                  │  │              │
│ multimodal  │  │           │  │                  │  │              │
└──────┬──────┘  └──────────┘  └──────────────────┘  └──────────────┘
       │
┌──────▼──────────┐
│  Email Service  │
│  (SMTP Gmail)   │
│                 │
│  Alerta cuando  │
│  afinidad ≥ 85% │
└─────────────────┘
```

**Principio arquitectónico**: los orquestadores dependen de una interfaz, no de una implementación concreta de IA. Cambiar de OpenAI a Ollama es cambiar una variable de entorno —cero cambios en la lógica de negocio—.

---

## Funcionalidades

### Interfaz web (Streamlit)

Dos espacios separados por pestañas, cada uno con su flujo completo:

#### 🎓 Portal del Candidato
- **Postulación** con formulario + CV en PDF procesado por IA multimodal
- **Auto-match silencioso**: al postularse, un hilo en background evalúa la afinidad contra la vacante objetivo
- **Doble indexación**: el perfil queda asociado a la vacante específica Y disponible en la bolsa global para futuras búsquedas

#### 🏢 Dashboard del Reclutador (protegido con login)
- **Autenticación JWT**: acceso restringido con usuario/contraseña (bcrypt)
- **Ingesta de vacantes** desde texto libre o PDF corporativo con extracción multimodal
- **Edición inteligente** con conciliación semántica que detecta si la vacante ya existe y la actualiza sin duplicar
- **Sidebar de silos activos** con vencimiento visible y acceso rápido a cada vacante
- **Búsqueda híbrida** con comandos naturales: `/crear vacante:`, `/match:`, `/nombre:` y consultas en lenguaje natural
- **Porcentaje de afinidad** legible por humanos (no distancia de coseno cruda)
- **Filtros MongoDB-style** generados automáticamente por el QueryTranslator

### Alertas por email

Cuando un candidato se postula y su afinidad con la vacante supera el **85%**, el sistema envía automáticamente un correo HTML al reclutador con el perfil, el porcentaje de match y un extracto del CV. Si no se configuran las credenciales SMTP, la funcionalidad se desactiva silenciosamente sin romper la app.

---

## Estructura del proyecto

```
semantic-talent-engine/
├── app.py                # Punto de entrada (Streamlit)
├── views/                # Interfaz web
│   ├── portal.py              # Portal del candidato
│   ├── dashboard.py           # Dashboard del reclutador (login JWT)
│   └── components.py          # Componentes reutilizables
├── config/               # settings.py: rutas, credenciales, DEBUG_MODE
├── models/               # schemas.py (Pydantic), ai_provider.py (OpenAI/Ollama), observability.py (Langfuse)
├── core/                 # Lógica de negocio
│   ├── orchestrator.py        # VacancyOrchestrator + CandidateOrchestrator
│   ├── extractor.py           # PDF → PNG (PyMuPDF, zoom 1.5x, ~108 DPI equivalentes)
│   ├── database.py            # Capa de persistencia en ChromaDB
│   ├── search_engine.py       # Búsqueda semántica + cálculo de afinidad
│   ├── query_translator.py    # Lenguaje natural → filtros ChromaDB
│   ├── security.py            # JWT + bcrypt + SQLite (usuarios)
│   ├── email_service.py       # Alertas SMTP para candidatos top
│   └── cli_console.py         # Interfaz alternativa por terminal
├── storage/              # Datos persistentes (excluido de Git)
│   ├── chroma_vector_db/      # Índices vectoriales
│   └── cv_files/              # PDFs originales de candidatos
├── tests/                # Tests unitarios con pytest
│   ├── conftest.py
│   └── unit/
│       ├── test_settings.py
│       ├── test_schemas.py
│       ├── test_langfuse_settings.py
│       ├── test_pii_masking.py
│       └── test_provider_observability_init.py
├── main.py               # CLI alternativa (python main.py)
├── requirements.txt
└── .env.example
```

### Decisiones de diseño

| Decisión | Motivo |
|---|---|
| PDF → imágenes antes que texto | Los layouts de CVs reales (columnas, tablas, íconos) rompen cualquier parser de texto. Un modelo multimodal entiende la página como la ve un humano |
| ChromaDB sobre Pinecone/Weaviate | Zero-deps de infraestructura cloud. Corre 100% local para el TFM sin servicios externos |
| Doble indexación | Si un candidato postula a "Ingeniero Civil", su perfil debe aparecer tanto en esa vacante como en búsquedas globales de "Ingeniero Estructural" —sin duplicar embeddings— |
| Query-Time TTL | La vigencia de la vacante se evalúa al momento de la búsqueda, no con jobs programados. Simplifica la infraestructura |
| Pydantic como contrato | Inmuniza el sistema contra alucinaciones de formato del LLM |
| JWT stateless | Sin sesiones en servidor. El token viaja en `st.session_state` y expira en 8 horas |
| Auto-match en background | El candidato no espera. Un `threading.Thread` ejecuta la búsqueda y dispara el email si corresponde |
| Email fails silently | Si faltan credenciales SMTP, la app sigue funcionando normalmente —las alertas son un plus, no un requisito |
| Tracing no bloquea | Si Langfuse no está disponible o `LANGFUSE_ENABLED=False`, el parseo de CVs y vacantes sigue funcionando sin degradación |
| PII masking en traces | Los campos personales del candidato (nombre, email, teléfono, ubicación, educación, historial laboral) se redactan a nivel SDK antes de salir de la app |

---

## Observabilidad LLM (Langfuse)

El sistema incluye tracing automático de todas las llamadas a modelos de lenguaje mediante Langfuse:

- **OpenAI**: tracing automático vía drop-in import — cero cambios en el cuerpo de los métodos
- **Ollama**: tracing vía decoradores `@observe()` con metadatos de modelo, latencia y outcome
- **Costos**: tracking automático de tokens y costo USD en llamadas OpenAI
- **Errores**: clasificación automática de fallos de parseo JSON y reintentos de auto-corrección
- **PII masking**: 7 campos de datos personales se redactan antes de que los traces salgan de la aplicación

Para activarlo, configurá las variables `LANGFUSE_*` en tu `.env`. Funciona tanto con una instancia self-hosted (Docker) como con Langfuse Cloud.

---

## Reset Utility (`purgar_db.py`)

⚠️ **Destructive operation** — deletes all ChromaDB collections and data.

```bash
python purgar_db.py
```

Use only when you need a clean slate for testing or re-indexing.

---

## Tests

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

---

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| Lenguaje | Python 3.x |
| Interfaz web | Streamlit |
| Vector DB | ChromaDB |
| Extracción PDF | PyMuPDF (zoom 1.5x, ~108 DPI equivalentes) |
| Procesamiento de imagen | Pillow |
| Modelos de IA | OpenAI GPT-4o-mini / Ollama + Gemma |
| Validación de datos | Pydantic |
| Autenticación | PyJWT + bcrypt + SQLite |
| Email | smtplib (Gmail SMTP) |
| Testing | pytest |
| Observabilidad LLM | Langfuse (tracing, costos, PII masking) |
| Configuración | python-dotenv |
