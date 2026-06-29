"""Capa de observabilidad para los proveedores LLM (Langfuse v4.x).

Este modulo encapsula:
  - `PII_FIELDS`: conjunto de campos sensibles del esquema CandidateStructure.
  - `mask_pii()`: redaccion recursiva a nivel SDK para Langfuse.
  - `get_langfuse_client()`: inicializacion perezosa con circuit breaker.
  - `observe`: re-exportacion segura del decorador de Langfuse (o no-op).
  - `_update_span()` / `_update_generation()`: helpers para metadatos en spans.

Contrato de degradacion graceful:
  Si el paquete `langfuse` no esta instalado, o si `LANGFUSE_ENABLED=False`,
  el modulo sigue siendo importable y exporta un `observe` no-op. La
  observabilidad NUNCA debe romper el parsing (requisito: circuit breaker).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional

from config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# PII masking: esquema CandidateStructure
# ---------------------------------------------------------------------------
PII_FIELDS = {
    "nombre_completo",
    "correo_electronico",
    "telefono_movil",
    "ubicacion",
    "educacion_detalle",
    "historial_laboral",
    "perfil_profesional",
}


def mask_pii(data: Any, **kwargs: Any) -> Any:
    """Redacta recursivamente los campos PII de una estructura.

    Opera a nivel SDK: se pasa como `mask=mask_pii` al cliente Langfuse.
    Maneja dicts, listas, strings JSON, y modelos Pydantic.

    Langfuse v4 serializa la respuesta de OpenAI como:
      {"role": "assistant", "content": '{"nombre_completo": "Juan", ...}'}
    El `content` es un string JSON — hay que parsearlo para redactar los
    campos PII que contiene.
    """
    # Convertir Pydantic models a dicts para inspeccionar sus campos
    try:
        from pydantic import BaseModel
        if isinstance(data, BaseModel):
            data = data.model_dump(mode="json")
    except ImportError:
        pass

    # Si es un string que parece JSON, parsearlo y redactar recursivamente
    if isinstance(data, str):
        stripped = data.strip()
        if stripped.startswith(("{", "[")):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (dict, list)):
                    masked = mask_pii(parsed, **kwargs)
                    return json.dumps(masked, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        return data

    if isinstance(data, dict):
        return {
            k: ("[REDACTED]" if k in PII_FIELDS else mask_pii(v, **kwargs))
            for k, v in data.items()
        }
    if isinstance(data, list):
        return [mask_pii(item, **kwargs) for item in data]
    return data


# ---------------------------------------------------------------------------
# Cliente Langfuse (inicializacion perezosa con circuit breaker)
# ---------------------------------------------------------------------------

_langfuse_client: Optional[Any] = None
_langfuse_init_attempted = False


def get_langfuse_client() -> Optional[Any]:
    """Inicializa y devuelve el cliente Langfuse singleton (v4.x).

    El cliente se crea con `mask=mask_pii` para redaccion a nivel SDK.
    `langfuse.openai.OpenAI` detecta automaticamente el cliente activo
    del proceso y aplica su configuracion de masking.
    """
    global _langfuse_client, _langfuse_init_attempted

    if not settings.LANGFUSE_ENABLED:
        return None

    if _langfuse_init_attempted:
        return _langfuse_client

    _langfuse_init_attempted = True

    try:
        from langfuse import Langfuse  # v4.x
    except ImportError:
        logger.warning(
            "Langfuse enabled but the `langfuse` package is not installed. "
            "Tracing disabled. Install with `pip install langfuse`."
        )
        return None
    except Exception as exc:
        logger.warning("Failed to import Langfuse client. Tracing disabled: %s", exc)
        return None

    try:
        _langfuse_client = Langfuse(
            host=settings.LANGFUSE_HOST,
            public_key=settings.LANGFUSE_PUBLIC_KEY,
            secret_key=settings.LANGFUSE_SECRET_KEY,
            mask=mask_pii,
        )
        logger.info("Langfuse client initialized (host=%s)", settings.LANGFUSE_HOST)
    except Exception as exc:
        logger.warning(
            "Failed to initialize Langfuse client. Tracing disabled: %s", exc
        )
        _langfuse_client = None
        return None

    return _langfuse_client


# ---------------------------------------------------------------------------
# Helpers para actualizar metadatos en spans activos (v4.x API)
# ---------------------------------------------------------------------------


def _update_span(**metadata: Any) -> None:
    """Actualiza el span activo con metadatos (error_type, stage, etc.).

    No-op silencioso cuando el tracing esta deshabilitado o no hay span activo.
    """
    try:
        if _langfuse_client is not None:
            _langfuse_client.update_current_span(metadata=metadata)
    except Exception:
        pass


def _update_generation(**usage: Any) -> None:
    """Actualiza la generation activa con token counts (best-effort).

    No-op silencioso cuando el tracing esta deshabilitado.
    """
    try:
        if _langfuse_client is not None:
            _langfuse_client.update_current_generation(usage=usage)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Decorador `observe` seguro (real o no-op) — v4.x usa `langfuse.observe`
# ---------------------------------------------------------------------------


def _dummy_observe(*args: Any, **kwargs: Any) -> Callable[..., Any]:
    """No-op decorator compatible con `@observe()` y `@observe(as_type=...)`."""
    if len(args) == 1 and callable(args[0]) and not kwargs:
        return args[0]

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        return func

    return decorator


def _resolve_observe() -> Callable[..., Any]:
    """Resuelve el decorador observe real (v4: `langfuse.observe`) o no-op."""
    if not settings.LANGFUSE_ENABLED:
        return _dummy_observe

    try:
        from langfuse import observe as _real_observe  # v4.x location
        return _real_observe
    except ImportError:
        logger.warning(
            "Langfuse enabled but `langfuse.observe` is unavailable. "
            "Falling back to no-op observe decorator."
        )
        return _dummy_observe
    except Exception as exc:
        logger.warning("Failed to load langfuse observe decorator: %s", exc)
        return _dummy_observe


observe = _resolve_observe()

__all__ = [
    "PII_FIELDS",
    "mask_pii",
    "get_langfuse_client",
    "observe",
    "_update_span",
    "_update_generation",
]
