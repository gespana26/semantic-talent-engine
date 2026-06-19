import chromadb
from config import settings
import shutil
import os

print("Iniciando purga del motor vectorial local...")

try:
    # 1. Conectamos al cliente local de Chroma
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    
    # 2. Eliminamos la coleccion corporativa completa
    coleccion = "talento-global-empresa"
    client.delete_collection(name=coleccion)
    print(f"[EXITO] Coleccion '{coleccion}' eliminada de ChromaDB.")
    
except Exception as e:
    print(f"[LOG] No se pudo borrar la coleccion (quiza ya no existe): {e}")

# 3. Limpiamos el silo de archivos fisicos para evitar huérfanos
silo_path = settings.LOCAL_STORAGE_CV_PATH
if os.path.exists(silo_path):
    for archivo in os.listdir(silo_path):
        ruta_archivo = os.path.join(silo_path, archivo)
        try:
            if os.path.isfile(ruta_archivo):
                os.unlink(ruta_archivo)
        except Exception as e:
            print(f"Error al borrar el archivo fisico {ruta_archivo}: {e}")
            
print("[EXITO] Silo de PDFs limpiado. Base de datos reseteada al 100%.")