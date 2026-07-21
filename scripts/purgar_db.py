"""
Purga completa de la base de datos vectorial (ChromaDB) y archivos físicos.

Uso:
    python purgar_db.py              # Limpia ChromaDB + PDFs, conserva usuarios.db
    python purgar_db.py --auth       # También elimina la DB de usuarios/credenciales
"""

import chromadb
from config import settings
import os
import sys

REMOVE_AUTH = "--auth" in sys.argv

print("=" * 55)
print("🧹 PURGA COMPLETA DEL MOTOR VECTORIAL LOCAL")
print("=" * 55)

# 1. Eliminar TODAS las colecciones de ChromaDB (silos + global)
try:
    client = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
    collections = client.list_collections()
    
    if not collections:
        print("[INFO] No hay colecciones que eliminar. ChromaDB ya está vacío.")
    else:
        for col in collections:
            nombre = col.name
            count = col.count()
            client.delete_collection(name=nombre)
            print(f"  ✅ '{nombre}' eliminada ({count} vectores)")
    
except Exception as e:
    print(f"[ERROR] No se pudo conectar a ChromaDB: {e}")

# 2. Limpiar archivos físicos (PDFs de CVs)
silo_path = settings.LOCAL_STORAGE_CV_PATH
if os.path.exists(silo_path):
    archivos = [f for f in os.listdir(silo_path) if os.path.isfile(os.path.join(silo_path, f))]
    if not archivos:
        print("[INFO] No hay PDFs en el silo de archivos.")
    else:
        for archivo in archivos:
            ruta = os.path.join(silo_path, archivo)
            try:
                os.unlink(ruta)
                print(f"  🗑️  {archivo}")
            except Exception as e:
                print(f"[ERROR] No se pudo borrar {archivo}: {e}")
        print(f"[EXITO] {len(archivos)} PDFs eliminados del silo.")
else:
    print(f"[INFO] El directorio '{silo_path}' no existe. Nada que limpiar.")

# 3. Usuarios DB (credenciales de login)
db_usuarios = os.path.join(os.path.dirname(__file__), "storage", "usuarios.db")
if REMOVE_AUTH:
    if os.path.exists(db_usuarios):
        os.unlink(db_usuarios)
        print("[EXITO] Base de datos de usuarios eliminada (usuarios.db).")
    else:
        print("[INFO] usuarios.db no existe. Nada que eliminar.")
else:
    print(f"[INFO] usuarios.db conservado ({db_usuarios}). Usá --auth para borrarlo también.")

print("=" * 55)
print("✅ PURGA COMPLETADA. Base de datos reseteada.")