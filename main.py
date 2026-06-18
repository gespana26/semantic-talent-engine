"""Punto de entrada principal del sistema encargado del bootstraping e inicialización de dependencias."""

from config import settings
from core.orchestrator import VacancyOrchestrator, CandidateOrchestrator
from core.cli_console import RECRUITMENTConsoleApp

def main():
    # 1. Resolución e Inyección de dependencias dinámicas del proveedor de IA
    if settings.AI_PROVIDER_TYPE == "openai":
        from models.ai_provider import OpenAIProvider
        ai_service = OpenAIProvider()
    elif settings.AI_PROVIDER_TYPE == "ollama":
        from models.ai_provider import LocalOllamaProvider
        ai_service = LocalOllamaProvider()
    else:
        raise ValueError(f"Tipo de configuración de proveedor de IA no soportada: {settings.AI_PROVIDER_TYPE}")

    # 2. Inicialización de la capa lógica de negocio (Orquestadores)
    orquestador_vacantes = VacancyOrchestrator(ai_provider=ai_service)
    orquestador_candidatos = CandidateOrchestrator(ai_provider=ai_service)
    
    # 3. Inicialización y arranque del controlador de la interfaz visual
    app = RECRUITMENTConsoleApp(
        vacancy_orchestrator=orquestador_vacantes, 
        candidate_orchestrator=orquestador_candidatos
    )
    app.run()

if __name__ == "__main__":
    main()