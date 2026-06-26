import os
import streamlit as st
import threading
from config import settings
from config.settings import clean_collection_name
from core.search_engine import CVSearchEngine
from core.orchestrator import CandidateOrchestrator
from models.ai_provider import OpenAIProvider, LocalOllamaProvider
from core.email_service import enviar_alerta_talento
from views.components import render_grilla_perfil

def evaluar_y_notificar_background(silo_destino, datos_extraidos):
    """Ejecuta un auto-match silencioso. Si el candidato es Top y >= 85%, alerta al reclutador."""
    try:
        if not silo_destino:
            return 
            
        coleccion_target = clean_collection_name(silo_destino)
        buscador = CVSearchEngine(collection_name=coleccion_target)
        texto_vacante = buscador.obtener_perfil_vacante()
        
        if not texto_vacante:
            return
            
        candidatos_top = buscador.search_candidates(query_text=texto_vacante, limit=10)
        
        correo_nuevo = str(datos_extraidos.get('correo_electronico', '')).lower().strip()
        nombre_nuevo = datos_extraidos.get('nombre_completo', 'Candidato Destacado')
        extracto = datos_extraidos.get('perfil_profesional', 'Extracto no disponible')[:250] + "..."
        
        for cand in candidatos_top:
            if cand.get('correo', '').lower().strip() == correo_nuevo:
                afinidad = cand.get('porcentaje_afinidad', 0)
                if afinidad >= 85.0:
                    enviar_alerta_talento(nombre_nuevo, silo_destino, afinidad, extracto)
                break 
                
    except Exception as e:
        print(f"Error silencioso en el hilo de telemetría: {e}")

def render_portal_candidato():
    """Renderiza el portal de postulación y coordina la ingesta de documentos."""
    st.subheader("Postulación Inteligente de Talento")
    st.markdown("Sube tu currículum y nuestra IA multimodal extraerá tu perfil.")
    
    with st.form("form_postulacion"):
        cargo_destino = st.text_input(
            "¿A qué vacante te postulas? (Opcional)", 
            placeholder="Ej: Project Manager (Deje en blanco para la Bolsa Global)"
        )
        archivo_cv = st.file_uploader("Adjunta tu Currículum (PDF)", type=["pdf"])
        submitted = st.form_submit_button("Analizar y Enviar Postulación", type="primary")
        
        if submitted:
            if not archivo_cv:
                st.error("⚠️ Por favor, adjunta un archivo PDF para continuar.")
                st.stop()
                
            with st.spinner("🤖 Analizando y extrayendo datos con Inteligencia Artificial..."):
                try:
                    directorio_storage = settings.LOCAL_STORAGE_CV_PATH
                    os.makedirs(directorio_storage, exist_ok=True)
                    
                    nombre_seguro = archivo_cv.name.replace(" ", "_")
                    ruta_fisica = os.path.join(directorio_storage, nombre_seguro)
                    
                    with open(ruta_fisica, "wb") as f:
                        f.write(archivo_cv.getbuffer())
                    
                    datos_candidato_web = {
                        "telefono": "0000",
                        "origen": "Portal Web Streamlit"
                    }
                        
                    proveedor_ia = None
                    tipo_proveedor = settings.AI_PROVIDER_TYPE.lower()
                    
                    if tipo_proveedor == "openai":
                        proveedor_ia = OpenAIProvider()
                    elif tipo_proveedor == "ollama":
                        proveedor_ia = LocalOllamaProvider()
                        
                    orquestador = CandidateOrchestrator(ai_provider=proveedor_ia)
                    
                    resultado = orquestador.process_and_register_candidate(
                        pdf_path=ruta_fisica,
                        cargo_objetivo=cargo_destino,
                        datos_formulario=datos_candidato_web
                    )
                    
                    if resultado and resultado.get("status") == "success":
                        st.success("✅ ¡Postulación exitosa! Tu perfil ha sido indexado en la base de datos.")
                        
                        if cargo_destino.strip():
                            hilo_alerta = threading.Thread(
                                target=evaluar_y_notificar_background,
                                args=(cargo_destino, resultado.get("datos_extraidos", {}))
                            )
                            hilo_alerta.start() 
                            
                        with st.expander("👀 Ver tu Perfil Estructurado (Auditoría de IA)", expanded=True):
                            datos_extraidos = resultado.get("datos_extraidos", {})
                            render_grilla_perfil(datos_extraidos)
                    else:
                        st.error("Hubo un problema al extraer los datos del documento.")
                        
                except Exception as e:
                    st.error(f"Fallo crítico en el procesamiento multimodal: {e}")