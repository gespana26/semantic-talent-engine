"""
Health checks for service dependencies required by the Semantic Talent Engine.

Usage in startup or demo scripts:

    from core.health import check_ollama_ready

    if not check_ollama_ready():
        print("Ollama not ready — start it with `ollama serve` and pull models")
"""
import logging

import requests

from config import settings

logger = logging.getLogger(__name__)


def check_ollama_ready() -> bool:
    """Verify Ollama is running and nomic-embed-text model is available."""
    try:
        resp = requests.get(
            f"{settings.OLLAMA_EMBEDDINGS_ENDPOINT.rstrip('/')}/api/tags",
            timeout=5,
        )
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        required = ["nomic-embed-text"]
        missing = [m for m in required if not any(m in name for name in models)]
        if missing:
            logger.warning(
                "Ollama running but missing models: %s. Run: ollama pull %s",
                missing,
                " ".join(missing),
            )
            return False
        logger.info("Ollama health check passed: %d models available", len(models))
        return True
    except requests.ConnectionError:
        logger.error(
            "Ollama not reachable at %s. Is Ollama running?",
            settings.OLLAMA_EMBEDDINGS_ENDPOINT,
        )
        return False
    except Exception as e:
        logger.error("Ollama health check failed: %s", e)
        return False