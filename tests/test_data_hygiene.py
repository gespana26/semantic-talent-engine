"""Unit tests for `core/data_hygiene.py`.

Estos tests fijan el contrato de precedencia entre el dato humano (formulario
confirmado) y el dato probabilistico (extraccion del LLM). El caso de regresion
central es el centinela "0000": al ser *truthy*, un `a or b` lo daba por bueno y
descartaba el telefono real extraido del documento.
"""

from __future__ import annotations

import pytest

from core.data_hygiene import (
    PLACEHOLDERS,
    email_valido,
    es_ausente,
    primer_dato_valido,
    telefono_valido,
)


# ---------------------------------------------------------------------------
# es_ausente
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "valor",
    [None, "", "   ", "0000", "N/A", "n/a", "No especificado", "NO ESPECIFICADA", "none", "-"],
)
def test_centinelas_se_reconocen_como_ausentes(valor) -> None:
    assert es_ausente(valor) is True


@pytest.mark.parametrize(
    "valor",
    ["jane@example.com", "Jane Doe", "+57 300 000 0000", "0", "00001"],
)
def test_datos_reales_no_se_confunden_con_centinelas(valor) -> None:
    assert es_ausente(valor) is False


def test_placeholders_se_comparan_en_minusculas() -> None:
    """El conjunto declarado debe estar normalizado para que la comparacion sea correcta."""
    assert all(p == p.lower().strip() for p in PLACEHOLDERS)


# ---------------------------------------------------------------------------
# primer_dato_valido
# ---------------------------------------------------------------------------


def test_regresion_el_centinela_0000_no_descarta_el_telefono_extraido() -> None:
    """Regresion: el formulario web enviaba "0000" y el `or` sepultaba el dato del CV."""
    telefono_formulario = "0000"
    telefono_extraido = "+57 300 111 2233"

    assert (telefono_formulario or telefono_extraido) == "0000"  # comportamiento antiguo
    assert primer_dato_valido(telefono_formulario, telefono_extraido) == telefono_extraido


def test_el_dato_humano_tiene_precedencia_cuando_es_real() -> None:
    assert primer_dato_valido("+57 320 999 8877", "+57 300 111 2233") == "+57 320 999 8877"


def test_devuelve_el_default_si_todos_los_valores_son_centinelas() -> None:
    assert primer_dato_valido("", None, "N/A", default="Nombre no disponible") == "Nombre no disponible"


def test_default_vacio_es_el_comportamiento_por_omision() -> None:
    assert primer_dato_valido("", None) == ""


def test_los_valores_devueltos_vienen_normalizados() -> None:
    assert primer_dato_valido("  Jane Doe  ") == "Jane Doe"


def test_respeta_el_orden_de_precedencia_con_varios_candidatos() -> None:
    assert primer_dato_valido(None, "0000", "", "segundo real", "tercero") == "segundo real"


# ---------------------------------------------------------------------------
# email_valido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "correo",
    ["jane@example.com", "j.doe@sub.acme.co", "JANE@EXAMPLE.COM", "  jane@example.com  "],
)
def test_correos_utilizables_se_aceptan(correo: str) -> None:
    assert email_valido(correo) is True


@pytest.mark.parametrize(
    "correo",
    ["", None, "jane@", "@example.com", "no-es-correo", "a b@x.com", "jane@example", "N/A"],
)
def test_correos_inutilizables_se_rechazan(correo) -> None:
    assert email_valido(correo) is False


# ---------------------------------------------------------------------------
# telefono_valido
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "telefono",
    [
        "+57 300 111 2233",
        "3001112233",
        "(+34) 612-345-678",
        "912 345 678",
        "+1 (555) 123-4567",
    ],
)
def test_telefonos_reales_se_aceptan(telefono: str) -> None:
    assert telefono_valido(telefono) is True


@pytest.mark.parametrize(
    ("telefono", "motivo"),
    [
        ("0000", "el centinela historico no alcanza los 7 digitos"),
        ("", "vacio"),
        (None, "ausente"),
        ("123456", "6 digitos, por debajo del minimo E.164"),
        ("1234567890123456", "16 digitos, por encima del maximo E.164"),
        ("no-tengo", "sin digitos"),
        ("300 111 2233 ext. 45", "caracteres alfabeticos no admitidos"),
        ("N/A", "centinela"),
    ],
)
def test_telefonos_invalidos_se_rechazan(telefono, motivo: str) -> None:
    assert telefono_valido(telefono) is False, motivo


def test_el_centinela_0000_no_puede_colarse_como_telefono_confirmado() -> None:
    """Cierre del bug: ni por precedencia ni por validacion el "0000" llega a persistirse."""
    assert es_ausente("0000") is True
    assert telefono_valido("0000") is False
