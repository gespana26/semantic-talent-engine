"""Autenticacion del dashboard: usuarios en SQLite y sesion sin estado por JWT.

QUE CAMBIO Y POR QUE
--------------------
El modulo ejecutaba `init_db()` como efecto secundario del import, firmaba los
tokens con una clave escrita en el codigo y creaba un usuario `admin/admin123`
igual de fijo. Los tres son el mismo error: **el arranque decidia en silencio
algo que corresponde a la configuracion**, y el repositorio acababa publicando
el secreto del que depende la sesion. Con la clave en el fuente, leer el codigo
equivale a poder firmarse un token valido: el formulario de login deja de ser
una frontera y pasa a ser decoracion.

Tres consecuencias practicas del rediseno:

1. **La clave de firma es obligatoria.** No hay valor por defecto. Si falta, el
   sistema se niega a arrancar con un mensaje que dice como generarla, en lugar
   de funcionar aparentemente bien con una proteccion que no existe.
2. **La inicializacion es explicita.** `inicializar_seguridad()` se invoca desde
   el composition root (`app.py`), no al importar. Importar un modulo no deberia
   crear ficheros ni usuarios, y ademas el efecto secundario obligaba a que el
   orden de imports fuese el correcto para que `load_dotenv()` ya hubiera
   corrido.
3. **La configuracion llega por `config.settings`**, que es quien carga el
   `.env`. Antes se leia con `os.getenv` directo y el resultado dependia de quien
   hubiera importado que cosa antes.

LIMITACION CONOCIDA DEL LIMITADOR DE INTENTOS
---------------------------------------------
El recuento de fallos vive en memoria del proceso: se reinicia si se reinicia
Streamlit y no se comparte entre varios procesos. Es suficiente para lo que
protege —un despliegue local de un solo proceso— y se documenta en lugar de
disfrazarse. Un despliegue multiproceso necesitaria llevarlo a la propia base.
"""

import logging
import os
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import settings

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"

# Longitud minima de la clave de firma, en bytes. No es una preferencia: RFC 7518
# 3.2 exige para HMAC una clave de al menos el tamano de la salida del hash, que
# en SHA-256 son 32 bytes. Una clave mas corta produce una firma mas debil sin
# que nada falle, que es la misma clase de defecto silencioso que motivo la
# reescritura de este modulo: parece protegido y no lo esta.
LONGITUD_MINIMA_CLAVE = 32

# Fallos de acceso recientes por usuario, en tiempo monotono. Ver la limitacion
# documentada en el docstring del modulo.
_INTENTOS_FALLIDOS: dict = {}


# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------


def _clave_de_firma() -> str:
    """Devuelve la clave con la que se firman los tokens, o falla explicandolo.

    Falla en vez de degradarse a un valor por defecto: una sesion firmada con una
    clave conocida no es una sesion protegida, y el sistema no debe poder
    afirmar lo contrario.
    """
    clave = (settings.JWT_SECRET_KEY or "").strip()
    if not clave:
        raise RuntimeError(
            "Falta JWT_SECRET_KEY. La firma de sesion no tiene valor por defecto "
            "a proposito: con una clave conocida cualquiera puede emitirse un "
            "token valido. Genere una y anadala al .env:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"\n'
            "  JWT_SECRET_KEY=<el valor generado>"
        )
    if len(clave.encode("utf-8")) < LONGITUD_MINIMA_CLAVE:
        raise RuntimeError(
            f"JWT_SECRET_KEY es demasiado corta ({len(clave.encode('utf-8'))} bytes). "
            f"HS256 exige al menos {LONGITUD_MINIMA_CLAVE} bytes (RFC 7518 3.2): por "
            "debajo de esa longitud la firma se debilita y PyJWT lo avisa por "
            "consola, pero el sistema seguiria funcionando como si nada. Genere "
            "una clave suficiente:\n"
            '  python -c "import secrets; print(secrets.token_urlsafe(48))"'
        )
    return clave


def verificar_configuracion() -> None:
    """Comprueba al arrancar lo que de otro modo fallaria en mitad de un login."""
    _clave_de_firma()


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------


def _conexion():
    """Abre la base de usuarios asegurando el cierre pase lo que pase.

    Las conexiones se abrian y se cerraban a mano, de modo que una excepcion
    entre medias dejaba el descriptor colgando. `closing` lo garantiza; el `with
    conn` de cada escritura confirma o revierte la transaccion.
    """
    os.makedirs(os.path.dirname(settings.USUARIOS_DB_PATH), exist_ok=True)
    return closing(sqlite3.connect(settings.USUARIOS_DB_PATH))


def _guardar_usuario(conn, username: str, password: str) -> None:
    """Inserta o reemplaza un usuario con su contrasena ya cifrada."""
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    with conn:
        conn.execute(
            "INSERT OR REPLACE INTO usuarios (username, password_hash) VALUES (?, ?)",
            (username, hashed.decode("utf-8")),
        )


def crear_usuario(username: str, password: str) -> None:
    """Alta o cambio de contrasena de un reclutador.

    Existe para que dar de alta a alguien no obligue a tocar el codigo, que era
    la razon por la que el usuario inicial estaba escrito en el fuente.
    """
    if not username or not password:
        raise ValueError("El usuario y la contrasena son obligatorios.")
    with _conexion() as conn:
        _crear_esquema(conn)
        _guardar_usuario(conn, username.strip(), password)


def _crear_esquema(conn) -> None:
    """Crea la tabla de usuarios si no existe."""
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
            """
        )


def _crear_admin_inicial(conn) -> None:
    """Crea el usuario inicial solo si no hay ninguno.

    La contrasena sale del entorno o se genera al azar y se muestra una unica
    vez. Nunca vuelve a haber una credencial conocida de antemano por quien lea
    el repositorio.
    """
    if conn.execute("SELECT 1 FROM usuarios LIMIT 1").fetchone():
        return

    usuario = settings.ADMIN_INICIAL_USUARIO
    declarada = settings.ADMIN_INICIAL_PASSWORD
    clave = declarada or secrets.token_urlsafe(12)
    _guardar_usuario(conn, usuario, clave)

    if declarada:
        logger.info("Usuario inicial '%s' creado con la contrasena declarada en el entorno.", usuario)
        return

    # La contrasena va SOLO a la consola, nunca al log. "Se muestra una vez" y
    # "queda escrita en un fichero de log" son afirmaciones incompatibles, y este
    # proyecto deja varios .log en el arbol. Al log va el hecho, no el secreto.
    logger.warning(
        "Usuario inicial '%s' creado con contrasena generada al azar y mostrada "
        "por consola. Declare ADMIN_INICIAL_PASSWORD para fijarla usted mismo.",
        usuario,
    )
    print(
        f"\n{'=' * 68}\n"
        f"  Usuario inicial creado: {usuario}\n"
        f"  Contrasena generada:    {clave}\n"
        "  Se muestra UNA sola vez y no queda en ningun log. Guardela.\n"
        "  Para fijarla usted mismo: ADMIN_INICIAL_PASSWORD=... en el .env\n"
        f"{'=' * 68}\n"
    )


def init_db() -> None:
    """Prepara la base de usuarios. Idempotente y de invocacion explicita."""
    with _conexion() as conn:
        _crear_esquema(conn)
        _crear_admin_inicial(conn)


def inicializar_seguridad() -> None:
    """Punto unico de arranque del subsistema de autenticacion.

    Se llama desde `app.py`. Valida primero y crea despues, para que una clave
    ausente se detecte antes de haber tocado el disco.
    """
    verificar_configuracion()
    init_db()


# ---------------------------------------------------------------------------
# Limite de intentos
# ---------------------------------------------------------------------------


def _fallos_recientes(username: str) -> list:
    """Fallos del usuario dentro de la ventana de bloqueo, descartando los viejos."""
    ventana = settings.LOGIN_BLOQUEO_MINUTOS * 60
    ahora = time.monotonic()
    recientes = [t for t in _INTENTOS_FALLIDOS.get(username, []) if ahora - t < ventana]
    if recientes:
        _INTENTOS_FALLIDOS[username] = recientes
    else:
        _INTENTOS_FALLIDOS.pop(username, None)
    return recientes


def minutos_de_bloqueo(username: str) -> int:
    """Minutos que faltan para poder reintentar; 0 si el usuario no esta bloqueado.

    Se expone para que la vista pueda decir la verdad. Presentar un bloqueo como
    "credenciales incorrectas" hace que el reclutador legitimo siga probando
    contrasenas correctas sin entender por que no entra.
    """
    fallos = _fallos_recientes(str(username or "").strip())
    if len(fallos) < settings.LOGIN_MAX_INTENTOS:
        return 0
    transcurrido = time.monotonic() - min(fallos)
    restante = settings.LOGIN_BLOQUEO_MINUTOS * 60 - transcurrido
    return max(1, int(restante // 60) + 1)


def _registrar_fallo(username: str) -> None:
    """Anota un intento fallido para el limitador."""
    _INTENTOS_FALLIDOS.setdefault(username, []).append(time.monotonic())


# ---------------------------------------------------------------------------
# Credenciales y sesion
# ---------------------------------------------------------------------------


def verificar_credenciales(username: str, password: str) -> bool:
    """Comprueba la contrasena contra el hash almacenado.

    Devuelve `False` tambien cuando el usuario esta bloqueado por intentos
    fallidos. La vista consulta `minutos_de_bloqueo` para distinguir ambos casos.
    """
    usuario = str(username or "").strip()
    if not usuario or not password:
        return False

    if minutos_de_bloqueo(usuario):
        logger.warning("Acceso bloqueado por exceso de intentos para '%s'.", usuario)
        return False

    with _conexion() as conn:
        _crear_esquema(conn)
        fila = conn.execute(
            "SELECT password_hash FROM usuarios WHERE username = ?", (usuario,)
        ).fetchone()

    if fila and bcrypt.checkpw(password.encode("utf-8"), fila[0].encode("utf-8")):
        _INTENTOS_FALLIDOS.pop(usuario, None)
        return True

    _registrar_fallo(usuario)
    return False


def generar_token(username: str) -> str:
    """Emite el JWT de sesion con la validez declarada en la configuracion."""
    expira = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_HORAS_VALIDEZ)
    return jwt.encode(
        {"sub": username, "exp": expira},
        _clave_de_firma(),
        algorithm=ALGORITHM,
    )


def validar_token(token: str):
    """Devuelve el usuario del token si es valido y no ha expirado; si no, `None`."""
    try:
        payload = jwt.decode(token, _clave_de_firma(), algorithms=[ALGORITHM])
        return payload["sub"]
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
