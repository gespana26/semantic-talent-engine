tfm/
│
├── config/
│   ├── __init__.py
│   └── settings.py              # Configuración global, credenciales y banderas (DEBUG_MODE) para que borre o no las imágenes y JSON
│
├── models/
│   ├── __init__.py
│   ├── schemas.py               # Contratos de datos estrictos (Pydantic: Vacancy y Query)
│   └── ai_provider.py           # Proveedor cognitivo (OpenAI / Inferencia local Gemma)
│
├── core/
│   ├── __init__.py
│   ├── extractor.py             # Pipeline de conversión de PDF a imágenes PNG (PyMuPDF)
│   ├── database.py              # Capa de datos y persistencia en ChromaDB (Silos y Bolsa Global)
│   ├── search_engine.py         # Motor de búsqueda semántica y cálculo formal de afinidad
│   ├── query_translator.py      # Agente traductor de lenguaje natural local a sintaxis JSON
│   └── orchestrator.py          # Cerebro del sistema (VacancyOrchestrator y CandidateOrchestrator)
│
├── storage/                     # Almacenamiento desacoplado (Excluido de Git / Persistente)
│   ├── chroma_vector_db/        # Archivos binarios e índices nativos de ChromaDB
│   └── cv_files/                # Repositorio físico de PDFs originales de los candidatos
│
├── temp_cv_images/              # Directorio temporal de procesamiento de páginas PNG
│
├── main_vacancy_test.py         # Script de pruebas: Ingesta y edición de vacantes
├── main_candidate_test.py       # Script de pruebas: Postulación de candidatos y doble indexación
└── main_search_test.py          # Script de pruebas: Búsqueda avanzada con filtros MongoDB-style

 Explicación Breve de Cada Módulo:
 Carpeta config/
				settings.py (Módulo de Configuración y Utilidades):
				Actúa como el origen único de la verdad para los parámetros del sistema. 
				Centraliza las rutas de almacenamiento, las claves de API, la selección del modelo de lenguaje y, de forma crítica, la bandera DEBUG_MODE. 
				Además, contiene las funciones deterministas para normalizar y limpiar los nombres de las colecciones de ChromaDB en tiempo de ejecución.
 
 Carpeta models/
				schemas.py (Capa de Validación y Contratos de Datos):
							Define las estructuras rígidas del sistema utilizando Pydantic.
							Modela cómo debe lucir una vacante (sueldo, habilidades, vigencia) y cómo debe estructurarse una consulta traducida. 
							Esto inmuniza al sistema contra datos mal formados o alucinaciones de formato por parte de los LLMs.

				ai_provider.py (Capa de Abstracción de IA):
							Encapsula toda la comunicación con los modelos fundacionales (ya sea la API en la nube de OpenAI o el modelo local Gemma 4 a través de Ollama).
							Se encarga de la extracción de entidades desde imágenes y de ejecutar la Conciliación Semántica de Entidades para evitar duplicar vacantes en la infraestructura.
 
 Carpeta core/ (Núcleo de la Lógica de Negocio)
				extractor.py (Pipeline de Ingesta Gráfica):
							Es el componente encargado de transformar documentos PDF complejos en imágenes PNG de alta resolución (300 DPI) usando la librería PyMuPDF.
							Esto permite que los modelos multimodales procesen el currículum o la vacante respetando su diseño visual y espacial 
							
				database.py (Manejador de Persistencia Vectorial): Gobierna las interacciones de escritura en ChromaDB. 
							Implementa las funciones .upsert() para asegurar la idempotencia del sistema y encapsula la lógica de almacenamiento de metadatos, guardando únicamente
							la ruta del archivo físico bajo una arquitectura desacoplada.
							
				search_engine.py (Motor de Recuperación Avanzada): Interroga a las colecciones de ChromaDB.
							Su función principal es realizar búsquedas semánticas híbridas y traducir la distancia matemática de coseno en una métrica de valor de negocio:
							el Porcentaje de Afinidad Humana ($1 - \text{distancia}$).
							
				query_translator.py (Compilador Lingüístico Local): 
							Un agente especializado de IA local que toma las peticiones en lenguaje natural de los reclutadores y las compila a un diccionario estructurado
							compatible con la sintaxis de filtros de ChromaDB (estilo MongoDB: $and, $contains), abstrayendo al usuario de la complejidad técnica.
							
				orchestrator.py (Cerebro del Sistema / Orquestador de Procesos): Dirige los flujos de trabajo de punta a punta. Tiene 2 métodos:
							VacancyOrchestrator: Coordina la ingesta de ofertas de empleo, calcula de forma determinista las marcas de tiempo para el control de vigencia (Query-Time TTL) y gestiona la conciliación de nombres.
							CandidateOrchestrator: Gobierna la postulación de candidatos ejecutando la estrategia de Doble Indexación (Dual-Indexing), guardando simultáneamente la información en el silo cerrado de la vacante y en la bolsa de empleo global de la empresa.
 
 Carpeta storage/ (Persistencia Desacoplada)
				(carpeta) chroma_vector_db/: Contenedor de la base de datos vectorial donde se guardan los embeddings (vectores matemáticos) y los metadatos indexados de alta velocidad.
				(carpeta) cv_files/: El almacén de objetos local donde se respaldan físicamente los PDFs originales renombrados con identificadores únicos.
 
 Justificación de Arquitectura TFM:
 El sistema fue diseñado bajo un enfoque estrictamente modular y desacoplado, aplicando los principios SOLID de la ingeniería de software.
 La lógica de persistencia (ChromaDB) está completamente aislada de la lógica cognitiva (AI Providers) y de la lógica de orquestación de procesos (Core Orchestrators).
 Esta separación de conceptos garantiza que el sistema pueda migrar de un proveedor de IA en la nube (OpenAI) a un modelo de lenguaje 100% local (Gemma 4) o cambiar el motor de vectores subyacente sin necesidad de refactorizar el código de la interfaz de usuario o alterar las reglas de negocio principales."