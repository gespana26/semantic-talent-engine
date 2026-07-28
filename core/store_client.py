"""Punto único de construcción del cliente del almacén vectorial.

POR QUÉ EXISTE
--------------
Seis módulos del dominio hacían `import chromadb` en su cabecera y construían
cada uno su propio `PersistentClient`. Eso tenía dos consecuencias, y ninguna es
de estilo.

**La primera se pagaba en cada ejecución de la suite.** Importar
`core.search_engine` importaba ChromaDB entero, aunque el test fuera a montar el
motor sobre un doble y no llegara a tocar el almacén. Los tests no necesitaban el
servicio levantado, pero sí el paquete instalado, y por eso la suite fallaba en
*collection* —antes de ejecutar nada— en cualquier entorno sin él. Las pruebas
llevaban tiempo peleándose con ello: `test_vacancy_embedding_coherence` llegaba a
fabricar un `chromadb` falso en `sys.modules`, y el docstring del fixture de
`test_busqueda_identidad` documenta los dieciséis `ImportError` que aquello
provocó cuando el módulo falso convivía con el real.

**La segunda es de diseño.** El proyecto abstrajo el proveedor de IA tras
`BaseLLMProvider` pero no el almacén, de modo que cambiar de LLM es una variable
de entorno y cambiar de base de datos es cirugía sobre seis ficheros. Esta costura
no es todavía ese puerto —no define un contrato, solo centraliza la construcción—
pero reduce a uno los sitios que nombran a ChromaDB, que es el primer paso de la
Fase 0 y el que la hace barata.

**El import es diferido a propósito**, igual que en `config/providers.py`: allí
cada proveedor de IA se importa solo cuando se elige, para que instalar un SDK no
obligue a instalar el otro. El criterio es el mismo, y aquí además significa que
importar un módulo del dominio deja de arrastrar el almacén.
"""

from config import settings


def crear_cliente(ruta: str = None):
    """Cliente persistente del almacén vectorial.

    `ruta` permite apuntar a otro directorio, lo que sirve sobre todo para
    pruebas de integración; en ejecución normal se toma de la configuración.
    """
    import chromadb

    return chromadb.PersistentClient(path=ruta or settings.CHROMA_DB_PATH)


def crear_funcion_embeddings():
    """Función de embeddings del proyecto, compartida por todas las colecciones.

    Que la construya un solo sitio es lo que sostiene la coherencia del índice:
    una colección creada con otra función de embeddings produce vectores de
    dimensión distinta y deja de ser comparable con el resto del silo.
    """
    from chromadb.utils import embedding_functions

    return embedding_functions.OllamaEmbeddingFunction(
        url=settings.OLLAMA_EMBEDDINGS_ENDPOINT,
        model_name=settings.EMBEDDING_MODEL,
    )
