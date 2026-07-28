"""Unit tests de la autenticación del dashboard (`core/security.py`).

QUÉ FIJAN ESTOS TESTS
---------------------
El módulo tenía tres defectos que compartían raíz: el arranque decidía en
silencio cosas que corresponden a la configuración. Firmaba con una clave
escrita en el fuente, creaba un `admin/admin123` igual de fijo, y hacía ambas
cosas como efecto secundario de importarse.

Los dos primeros son especialmente caros porque el repositorio está publicado:
quien leyera el código conocía la contraseña inicial **y** podía firmarse un
token válido sin pasar por el formulario. Por eso hay aquí dos tests de
regresión escritos contra los valores concretos que llegaron a estar en el
código: si alguien los reintroduce, la suite lo dice.

El límite de intentos se prueba sobre su comportamiento observable —bloquear,
seguir bloqueando aunque acierte, y soltarse al acertar antes del tope— y no
sobre su almacenamiento, que es un detalle interno documentado como limitación.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import jwt
import pytest

from config import settings
from core import security

RAIZ_PROYECTO = Path(__file__).resolve().parents[2]

# La clave que llegó a estar escrita en `core/security.py`. Se conserva aquí
# como valor prohibido, no como configuración.
CLAVE_FILTRADA_HISTORICA = "ats_talent_engine_super_secret_key_2026"

# Clave de los tests. Debe superar los 32 bytes que exige HS256: una más corta
# hace que PyJWT emita `InsecureKeyLengthWarning` en cada firma y ensucie la
# salida de la suite con un aviso que no describe ningún defecto del proyecto.
CLAVE_DE_PRUEBAS = "clave-solo-para-pruebas-con-longitud-suficiente-para-hs256"


@pytest.fixture
def entorno(tmp_path, monkeypatch):
    """Aísla la base de usuarios y la configuración de cada test."""
    monkeypatch.setattr(settings, "USUARIOS_DB_PATH", str(tmp_path / "usuarios.db"))
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", CLAVE_DE_PRUEBAS)
    monkeypatch.setattr(settings, "JWT_HORAS_VALIDEZ", 8)
    monkeypatch.setattr(settings, "ADMIN_INICIAL_USUARIO", "admin")
    monkeypatch.setattr(settings, "ADMIN_INICIAL_PASSWORD", "")
    monkeypatch.setattr(settings, "LOGIN_MAX_INTENTOS", 3)
    monkeypatch.setattr(settings, "LOGIN_BLOQUEO_MINUTOS", 15)
    security._INTENTOS_FALLIDOS.clear()
    yield
    security._INTENTOS_FALLIDOS.clear()


# ---------------------------------------------------------------------------
# Regresión: los secretos que estuvieron en el código
# ---------------------------------------------------------------------------


def test_la_contrasena_inicial_historica_ya_no_abre_nada(entorno) -> None:
    """`admin/admin123` estaba escrito en el fuente de un repositorio publicado."""
    security.init_db()
    assert security.verificar_credenciales("admin", "admin123") is False


def test_la_clave_de_firma_historica_ya_no_valida_sesiones(entorno) -> None:
    """Con la clave en el código, el login era decorativo: cualquiera se firmaba un token."""
    falsificado = jwt.encode(
        {"sub": "intruso"}, CLAVE_FILTRADA_HISTORICA, algorithm=security.ALGORITHM
    )
    assert security.validar_token(falsificado) is None


def test_el_usuario_inicial_recibe_una_contrasena_impredecible(entorno) -> None:
    """Sin contraseña declarada se genera al azar, así que dos bases no coinciden."""
    security.init_db()
    assert security.verificar_credenciales("admin", "admin") is False
    assert security.verificar_credenciales("admin", "admin123") is False
    assert security.verificar_credenciales("admin", "") is False


def test_importar_el_modulo_no_crea_la_base_de_datos(tmp_path) -> None:
    """`init_db()` corría al importar: importar creaba ficheros y un usuario."""
    destino = tmp_path / "no_debe_existir.db"
    entorno_hijo = {
        **os.environ,
        "USUARIOS_DB_PATH": str(destino),
        "JWT_SECRET_KEY": CLAVE_DE_PRUEBAS,
    }
    subprocess.run(
        [sys.executable, "-c", "import core.security"],
        cwd=str(RAIZ_PROYECTO),
        env=entorno_hijo,
        check=True,
        capture_output=True,
    )
    assert not destino.exists()


# ---------------------------------------------------------------------------
# La clave de firma es obligatoria
# ---------------------------------------------------------------------------


def test_sin_clave_de_firma_el_sistema_se_niega_a_emitir_sesion(entorno, monkeypatch) -> None:
    """Degradarse a un valor por defecto sería afirmar una protección inexistente."""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "")
    with pytest.raises(RuntimeError) as fallo:
        security.generar_token("reclutador")
    assert "JWT_SECRET_KEY" in str(fallo.value)


def test_el_mensaje_de_error_dice_como_resolverlo(entorno, monkeypatch) -> None:
    """Un fallo de configuración que no explica el remedio cuesta una sesión de diagnóstico."""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "   ")
    with pytest.raises(RuntimeError) as fallo:
        security.verificar_configuracion()
    assert "token_urlsafe" in str(fallo.value)


def test_la_clave_demasiado_corta_se_rechaza(entorno, monkeypatch) -> None:
    """RFC 7518 3.2: HS256 exige una clave de al menos el tamaño del hash.

    Por debajo de 32 bytes PyJWT firma igual y solo emite un aviso por consola.
    Un aviso no es una frontera: el sistema seguiría sirviendo sesiones firmadas
    con una clave que no sostiene la garantía que dice sostener.
    """
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "corta")
    with pytest.raises(RuntimeError) as fallo:
        security.verificar_configuracion()
    assert "demasiado corta" in str(fallo.value)


def test_la_clave_en_el_limite_exacto_se_acepta(entorno, monkeypatch) -> None:
    """El límite es inclusivo: 32 bytes exactos cumplen la especificación."""
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "a" * security.LONGITUD_MINIMA_CLAVE)
    security.verificar_configuracion()
    assert security.validar_token(security.generar_token("reclutador")) == "reclutador"


# ---------------------------------------------------------------------------
# Credenciales y ciclo de sesión
# ---------------------------------------------------------------------------


def test_el_alta_explicita_permite_entrar(entorno) -> None:
    security.crear_usuario("reclutador", "una-clave-larga-y-propia")
    assert security.verificar_credenciales("reclutador", "una-clave-larga-y-propia") is True


def test_la_contrasena_equivocada_no_entra(entorno) -> None:
    security.crear_usuario("reclutador", "una-clave-larga-y-propia")
    assert security.verificar_credenciales("reclutador", "otra-cosa") is False


def test_el_usuario_inexistente_no_entra(entorno) -> None:
    security.init_db()
    assert security.verificar_credenciales("fantasma", "lo-que-sea") is False


def test_init_db_es_idempotente(entorno) -> None:
    """Se invoca en cada rerun de Streamlit: repetirla no puede rehacer el usuario."""
    security.init_db()
    security.crear_usuario("admin", "contrasena-elegida-por-el-operador")
    security.init_db()
    assert security.verificar_credenciales("admin", "contrasena-elegida-por-el-operador") is True


def test_el_token_valido_devuelve_su_usuario(entorno) -> None:
    token = security.generar_token("reclutador")
    assert security.validar_token(token) == "reclutador"


def test_el_token_manipulado_se_rechaza(entorno) -> None:
    token = security.generar_token("reclutador")
    assert security.validar_token(token[:-4] + "abcd") is None


def test_el_token_expirado_se_rechaza(entorno, monkeypatch) -> None:
    """La validez sale de la configuración; en negativo el token nace caducado."""
    monkeypatch.setattr(settings, "JWT_HORAS_VALIDEZ", -1)
    assert security.validar_token(security.generar_token("reclutador")) is None


# ---------------------------------------------------------------------------
# Límite de intentos
# ---------------------------------------------------------------------------


def test_bloquea_al_alcanzar_el_maximo_de_intentos(entorno) -> None:
    """Sin límite, una contraseña de ocho caracteres es cuestión de tiempo de CPU."""
    security.crear_usuario("reclutador", "una-clave-larga-y-propia")
    for _ in range(settings.LOGIN_MAX_INTENTOS):
        security.verificar_credenciales("reclutador", "mal")
    assert security.minutos_de_bloqueo("reclutador") > 0


def test_el_bloqueo_rechaza_incluso_la_contrasena_correcta(entorno) -> None:
    """Si acertar durante el bloqueo abriera, el límite no limitaría nada."""
    security.crear_usuario("reclutador", "una-clave-larga-y-propia")
    for _ in range(settings.LOGIN_MAX_INTENTOS):
        security.verificar_credenciales("reclutador", "mal")
    assert security.verificar_credenciales("reclutador", "una-clave-larga-y-propia") is False


def test_acertar_antes_del_tope_reinicia_el_contador(entorno) -> None:
    """El reclutador que se equivoca una vez y luego acierta no arrastra penalización."""
    security.crear_usuario("reclutador", "una-clave-larga-y-propia")
    security.verificar_credenciales("reclutador", "mal")
    assert security.verificar_credenciales("reclutador", "una-clave-larga-y-propia") is True
    assert security.minutos_de_bloqueo("reclutador") == 0


def test_el_bloqueo_es_por_usuario_y_no_global(entorno) -> None:
    """Bloquear a todo el mundo porque uno falla sería una denegación de servicio trivial."""
    security.crear_usuario("otro", "su-propia-clave-larga")
    for _ in range(settings.LOGIN_MAX_INTENTOS):
        security.verificar_credenciales("reclutador", "mal")
    assert security.minutos_de_bloqueo("otro") == 0
    assert security.verificar_credenciales("otro", "su-propia-clave-larga") is True
