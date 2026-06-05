import json
from models.gemma_provider import GemmaMultimodalProvider
from core.database import CVVectorStoreManager
from core.orchestrator import CVEngineOrchestrator

def run_pipeline():
    # Archivo PDF que deseas procesar (Prueba con un CV escaneado o digital)
    RUTA_CV_PRUEBA = "mi_hoja_de_vida_prueba.pdf"
    
    # 1. Inicializar componentes de infraestructura básica
    gemma_vision_ai = GemmaMultimodalProvider()
    chroma_vector_db = CVVectorStoreManager()
    
    # 2. Construir el orquestador inyectando sus dependencias
    cv_pipeline = CVEngineOrchestrator(
        llm_provider=gemma_vision_ai, 
        db_manager=chroma_vector_db
    )
    
    try:
        # 3. Disparar la automatización
        resultado_json = cv_pipeline.process_and_store_candidate(RUTA_CV_PRUEBA)
        
        # 4. Imprimir el JSON resultante con fines de auditoría visual en desarrollo
        print("=" * 60)
        print("CONSOLA DE CONTROL - ENTIDADES EXTRAÍDAS DE MANERA MULTIMODAL")
        print("=" * 60)
        print(json.dumps(resultado_json, indent=2, ensure_ascii=False))
        print("=" * 60)
        
    except Exception as error:
        print(f"\n[SISTEMA APAGADO DE EMERGENCIA]: No se pudo procesar el candidato. Motivo: {error}")

if __name__ == "__main__":
    run_application = run_pipeline()