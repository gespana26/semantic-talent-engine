"""Punto de entrada principal del sistema encargado del bootstraping e inicialización de dependencias."""

from config.providers import get_ai_provider
from core.cli_console import RECRUITMENTConsoleApp
from core.orchestrator import CandidateOrchestrator, VacancyOrchestrator


def main():
    # 1. Composition root: el unico punto donde se decide el proveedor de IA.
    ai_service = get_ai_provider()

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