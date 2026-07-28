"""Unit tests del catálogo de vacantes (`core/vacancy_catalog.py`).

QUÉ FIJAN ESTOS TESTS
---------------------
El panel lateral del reclutador calculaba su propio resumen de silos en
`views/components.py`, en paralelo a este módulo. Dos consecuencias:

1. **Coste.** Recorría la colección completa —arrastrando el `raw_json` de cada
   candidato— para leer un registro que se direcciona por clave, y lo repetía en
   cada repintado de Streamlit.
2. **Divergencia sin dueño.** Las dos proyecciones aplicaban reglas de
   visibilidad distintas, pero nadie había decidido esa diferencia: era el
   resultado de que cada fichero resolviera el problema por su cuenta.

Ahora la diferencia existe, está escrita y se prueba: el portal descarta las
vacantes expiradas porque su pregunta es a qué puede uno postularse hoy; el
dashboard las marca pero las conserva, porque sus candidatos siguen ahí y
ocultárselos al reclutador sería esconderle sus propios datos.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core import vacancy_catalog as catalogo

HOY = datetime.now()


def _fecha(dias_desde_hoy: int) -> str:
    """Marca de expiración en el formato `YYYYMMDD` que persiste el registro."""
    return (HOY + timedelta(days=dias_desde_hoy)).strftime("%Y%m%d")


class ColeccionFalsa:
    """Doble de una colección de ChromaDB que contabiliza cómo se la consulta."""

    def __init__(self, nombre, vacante=None, candidatos=0):
        self.name = nombre
        self.vacante = vacante
        self.candidatos = candidatos
        self.lecturas_por_clave = 0
        self.lecturas_completas = 0

    def get(self, ids=None, include=None):
        if ids == [catalogo.ID_VACANTE]:
            self.lecturas_por_clave += 1
            if self.vacante is None:
                return {"ids": [], "metadatas": []}
            return {"ids": ids, "metadatas": [self.vacante]}

        # Lectura sin filtro: devuelve la coleccion entera, candidatos incluidos.
        self.lecturas_completas += 1
        perfiles = [{"nombre_completo": f"Candidato {i}"} for i in range(self.candidatos)]
        return {"ids": [], "metadatas": perfiles}


class ClienteFalso:
    def __init__(self, colecciones):
        self._colecciones = colecciones

    def list_collections(self):
        return self._colecciones


def _vacante(titulo, expira_en_dias=None, texto="Descripcion de la oferta"):
    meta = {"titulo_cargo": titulo, "texto_original": texto}
    if expira_en_dias is not None:
        meta["timestamp_expiracion"] = _fecha(expira_en_dias)
    return meta


@pytest.fixture
def colecciones(monkeypatch):
    """Instala un cliente falso y devuelve las colecciones para inspeccionarlas."""
    catalogo_colecciones = {
        "vigente":   ColeccionFalsa("project-manager", _vacante("Project Manager", 10), candidatos=40),
        "expirada":  ColeccionFalsa("data-analyst", _vacante("Data Analyst", -5), candidatos=12),
        "ultimodia": ColeccionFalsa("qa-engineer", _vacante("QA Engineer", 0), candidatos=3),
        "sinlimite": ColeccionFalsa("devops", _vacante("DevOps"), candidatos=7),
        "residual":  ColeccionFalsa("silo-huerfano", None, candidatos=2),
        "global":    ColeccionFalsa(catalogo.COLECCION_GLOBAL, None, candidatos=500),
    }
    monkeypatch.setattr(
        catalogo.store_client, "crear_cliente",
        lambda *_a, **_k: ClienteFalso(list(catalogo_colecciones.values()))
    )
    return catalogo_colecciones


# ---------------------------------------------------------------------------
# Coste: el defecto medible
# ---------------------------------------------------------------------------


def test_el_resumen_no_recorre_ninguna_coleccion_entera(colecciones) -> None:
    """El defecto: cargar 40 perfiles completos para leer una fecha."""
    catalogo.obtener_silos_del_reclutador()

    for nombre, col in colecciones.items():
        assert col.lecturas_completas == 0, (
            f"{nombre} se leyo entera; basta un acceso por clave."
        )


def test_cada_silo_se_lee_por_clave_una_sola_vez(colecciones) -> None:
    catalogo.obtener_silos_del_reclutador()

    assert colecciones["vigente"].lecturas_por_clave == 1
    assert colecciones["global"].lecturas_por_clave == 0, "La bolsa global no es un silo."


# ---------------------------------------------------------------------------
# La proyeccion del reclutador
# ---------------------------------------------------------------------------


def test_el_reclutador_ve_las_expiradas_marcadas(colecciones) -> None:
    """Sus candidatos siguen ahi: ocultarlas seria esconderle sus propios datos."""
    silos = {s["nombre"]: s for s in catalogo.obtener_silos_del_reclutador()}

    assert "data-analyst" in silos
    assert silos["data-analyst"]["expirada"] is True
    assert silos["data-analyst"]["dias"] == 0


def test_la_vacante_que_cierra_hoy_no_esta_expirada(colecciones) -> None:
    """`dias == 0` y `expirada` son estados distintos: hoy todavia admite postulacion.

    Regresion de un error de fecha que este test destapo. La resta se hacia entre
    el `datetime` de la expiracion —que `strptime` situa a las 00:00— y el
    instante actual, de modo que el propio dia de cierre daba −1 y la vacante
    constaba cerrada desde las 00:00:01. Con treinta dias de vigencia por defecto,
    el candidato disponia de veintinueve.
    """
    silos = {s["nombre"]: s for s in catalogo.obtener_silos_del_reclutador()}

    assert silos["qa-engineer"]["dias"] == 0
    assert silos["qa-engineer"]["expirada"] is False


def test_el_ultimo_dia_sigue_admitiendo_postulacion(colecciones) -> None:
    """La otra cara del mismo error: el portal la ocultaba un dia antes de tiempo."""
    nombres = [v["coleccion"] for v in catalogo.obtener_vacantes_publicas()]
    assert "qa-engineer" in nombres


def test_los_dias_restantes_no_dependen_de_la_hora(colecciones) -> None:
    """Comparar instantes hacia que el resultado cambiara a lo largo del dia."""
    silos = {s["nombre"]: s for s in catalogo.obtener_silos_del_reclutador()}
    assert silos["project-manager"]["dias"] == 10


def test_la_vacante_sin_fecha_se_marca_sin_limite(colecciones) -> None:
    silos = {s["nombre"]: s for s in catalogo.obtener_silos_del_reclutador()}

    assert silos["devops"]["dias"] == catalogo.SIN_LIMITE
    assert silos["devops"]["expirada"] is False


def test_el_reclutador_ve_los_silos_sin_registro_de_vacante(colecciones) -> None:
    """Para el candidato no son postulables; para el reclutador son colecciones reales."""
    silos = {s["nombre"]: s for s in catalogo.obtener_silos_del_reclutador()}

    assert "silo-huerfano" in silos
    assert silos["silo-huerfano"]["dias"] == catalogo.SIN_LIMITE


def test_la_bolsa_global_nunca_aparece_como_silo(colecciones) -> None:
    nombres = [s["nombre"] for s in catalogo.obtener_silos_del_reclutador()]
    assert catalogo.COLECCION_GLOBAL not in nombres


# ---------------------------------------------------------------------------
# La proyeccion del candidato, y en que se diferencia
# ---------------------------------------------------------------------------


def test_el_portal_descarta_las_expiradas(colecciones) -> None:
    """Si no se puede postular, no se muestra."""
    nombres = [v["coleccion"] for v in catalogo.obtener_vacantes_publicas()]

    assert "data-analyst" not in nombres
    assert "project-manager" in nombres


def test_el_portal_descarta_los_silos_sin_oferta(colecciones) -> None:
    """Una coleccion sin registro de vacante es un silo residual, no una oferta."""
    nombres = [v["coleccion"] for v in catalogo.obtener_vacantes_publicas()]
    assert "silo-huerfano" not in nombres


def test_las_dos_proyecciones_difieren_a_proposito(colecciones) -> None:
    """La prueba de que la divergencia es una decision y no un descuido."""
    del_reclutador = {s["nombre"] for s in catalogo.obtener_silos_del_reclutador()}
    del_candidato = {v["coleccion"] for v in catalogo.obtener_vacantes_publicas()}

    assert del_candidato < del_reclutador
    assert del_reclutador - del_candidato == {"data-analyst", "silo-huerfano"}


def test_el_portal_ordena_por_titulo(colecciones) -> None:
    titulos = [v["titulo"] for v in catalogo.obtener_vacantes_publicas()]
    assert titulos == sorted(titulos, key=str.lower)


def test_el_texto_ausente_no_se_muestra_como_tal(colecciones, monkeypatch) -> None:
    """El marcador interno no es contenido que el candidato deba leer."""
    col = ColeccionFalsa("becario", _vacante("Becario", 5, texto=catalogo.TEXTO_AUSENTE))
    monkeypatch.setattr(
        catalogo.store_client, "crear_cliente", lambda *_a, **_k: ClienteFalso([col])
    )
    assert catalogo.obtener_vacantes_publicas()[0]["detalle"] == ""


# ---------------------------------------------------------------------------
# Degradacion
# ---------------------------------------------------------------------------


def test_un_almacen_caido_no_rompe_el_panel(monkeypatch) -> None:
    """El sidebar no puede tumbar el dashboard porque ChromaDB no responda."""
    def revienta(*_a, **_k):
        raise RuntimeError("almacen no disponible")

    monkeypatch.setattr(catalogo.store_client, "crear_cliente", revienta)

    assert catalogo.obtener_silos_del_reclutador() == []
    assert catalogo.obtener_vacantes_publicas() == []
