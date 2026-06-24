# Semantic Talent Engine

ATS (*Applicant Tracking System*) inteligente impulsado por IA multimodal que automatiza el matching entre vacantes y candidatos usando búsqueda semántica sobre vectores. Procesa documentos PDF reales —no formularios planos— y permite a los reclutadores buscar talento en lenguaje natural sin conocer operadores de base de datos.

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
git clone <repo-url>
cd semantic-talent-engine
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # Linux/Mac

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Configurar el proveedor de IA
cp .env.example .env
# Editar .env con tu OPENAI_API_KEY o configurar Ollama

# 4. Ejecutar
python main.py
```

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
┌─────────────────────────────────────────────────┐
│                  CLI (ui/)                       │
│        Menú interactivo: vacantes, candidatos,   │
│        búsqueda semántica                        │
└────────────────────┬────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────┐
│            Core Orchestrators                    │
│  VacancyOrchestrator  │  CandidateOrchestrator   │
│  - Ingesta + TTL      │  - Postulación           │
│  - Conciliación       │  - Doble indexación      │
└──────┬───────────────┴──────────┬───────────────┘
       │                           │
┌──────▼──────┐  ┌──────────┐  ┌──▼───────────────┐
│  AI Provider │  │ Search   │  │  Vector Store    │
│  (models/)   │  │ Engine   │  │  (ChromaDB)      │
│              │  │          │  │                   │
│  OpenAI/Ollama│  │ Afinidad │  │  Silo + Global    │
│  Extracción  │  │ Híbrida  │  │  Pool            │
│  multimodal  │  │          │  │                   │
└─────────────┘  └──────────┘  └──────────────────┘
```

**Principio arquitectónico**: los orquestadores dependen de una interfaz, no de una implementación concreta de IA. Cambiar de OpenAI a Ollama es cambiar una variable de entorno —cero cambios en la lógica de negocio—.

---

## Funcionalidades

### Para el reclutador
- **Ingesta de vacantes** desde texto libre o PDF corporativo con extracción multimodal
- **Edición inteligente** con conciliación semántica que detecta si la vacante ya existe y la actualiza en lugar de duplicarla
- **Búsqueda en lenguaje natural**: _"buscame un ingeniero civil con experiencia en obras hidráulicas y que hable inglés"_
- **Filtros MongoDB-style** generados automáticamente por el QueryTranslator sin que el usuario toque un operador
- **Porcentaje de afinidad** legible por humanos (no distancia de coseno cruda)

### Para el candidato
- **Postulación** con formulario + CV en PDF
- **Doble indexación**: el perfil queda asociado a la vacante específica Y disponible en la bolsa global para futuras búsquedas

---

## Estructura del proyecto

```
semantic-talent-engine/
├── config/           # settings.py: rutas, credenciales, DEBUG_MODE
├── models/           # schemas.py (Pydantic), ai_provider.py (OpenAI/Ollama)
├── core/             # Lógica de negocio
│   ├── orchestrator.py    # VacancyOrchestrator + CandidateOrchestrator
│   ├── extractor.py       # PDF → PNG (PyMuPDF, 300 DPI)
│   ├── database.py        # Capa de persistencia en ChromaDB
│   ├── search_engine.py   # Búsqueda semántica + cálculo de afinidad
│   ├── query_translator.py # Lenguaje natural → filtros ChromaDB
│   └── cli_console.py     # Interfaz de línea de comandos
├── ui/               # Capa de presentación
├── storage/          # Datos persistentes (excluido de Git)
│   ├── chroma_vector_db/  # Índices vectoriales
│   └── cv_files/          # PDFs originales de candidatos
├── tests/            # Tests unitarios con pytest
├── main.py           # Punto de entrada
└── requirements.txt
```

### Decisiones de diseño

| Decisión | Motivo |
|---|---|
| PDF → imágenes antes que texto | Los layouts de CVs reales (columnas, tablas, íconos) rompen cualquier parser de texto. Un modelo multimodal entiende la página como la ve un humano |
| ChromaDB sobre Pinecone/Weaviate | Zero-deps de infraestructura cloud. Corre 100% local para el TFM sin servicios externos |
| Doble indexación | Si un candidato postula a "Ingeniero Civil", su perfil debe aparecer tanto en esa vacante como en búsquedas globales de "Ingeniero Estructural" —sin duplicar embeddings— |
| Query-Time TTL | La vigencia de la vacante se evalúa al momento de la búsqueda, no con jobs programados. Simplifica la infraestructura |
| Pydantic como contrato | Inmuniza el sistema contra alucinaciones de formato del LLM. Si el modelo devuelve un JSON inválido, Pydantic lo rechaza antes de llegar a la base de datos |

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
| Vector DB | ChromaDB |
| Extracción PDF | PyMuPDF (300 DPI) |
| Procesamiento de imagen | Pillow |
| Modelos de IA | OpenAI GPT-4o-mini / Ollama + Gemma |
| Validación de datos | Pydantic |
| Testing | pytest |
| Configuración | python-dotenv |
