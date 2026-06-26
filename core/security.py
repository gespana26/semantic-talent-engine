"""Módulo de autenticación y autorización utilizando SQLite y JSON Web Tokens (JWT)."""

import sqlite3
import bcrypt
import jwt
from datetime import datetime, timedelta
import os
from config import settings

# Usaremos una clave secreta para firmar los tokens. Si no existe en el .env, usa una por defecto.
# Idealmente, añade JWT_SECRET_KEY=tu_clave_super_secreta a tu archivo .env
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "ats_talent_engine_super_secret_key_2026")
ALGORITHM = "HS256"
DB_PATH = "usuarios.db"

def init_db():
    """Inicializa la base de datos de usuarios y crea un reclutador por defecto si está vacía."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Crear tabla de usuarios
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    # Verificar si ya existe el usuario admin
    cursor.execute('SELECT * FROM usuarios WHERE username = ?', ('admin',))
    if not cursor.fetchone():
        # Crear contraseña por defecto: "admin123" (Hasheada por seguridad)
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw("admin123".encode('utf-8'), salt)
        
        cursor.execute('INSERT INTO usuarios (username, password_hash) VALUES (?, ?)', 
                      ('admin', hashed.decode('utf-8')))
        conn.commit()
        print("✅ Base de datos de seguridad inicializada. Usuario por defecto: admin / admin123")
        
    conn.close()

def verificar_credenciales(username, password):
    """Verifica si la contraseña ingresada coincide con el hash en la base de datos."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT password_hash FROM usuarios WHERE username = ?', (username,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        hashed_password = row[0].encode('utf-8')
        if bcrypt.checkpw(password.encode('utf-8'), hashed_password):
            return True
    return False

def generar_token(username):
    """Emite un JSON Web Token (JWT) válido por 8 horas."""
    fecha_expiracion = datetime.utcnow() + timedelta(hours=8)
    payload = {
        "sub": username,
        "exp": fecha_expiracion
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token

def validar_token(token):
    """Verifica si el token es válido y no ha expirado."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload["sub"] # Retorna el username si es exitoso
    except jwt.ExpiredSignatureError:
        return None # Token expirado
    except jwt.InvalidTokenError:
        return None # Token manipulado o inválido

# Inicializar la base de datos al importar el módulo
init_db()