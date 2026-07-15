import os
import uuid
import streamlit as st
import threading
from config import settings
from core.orchestrator import CandidateOrchestrator
from models.ai_provider import OpenAIProvider, LocalOllamaProvider
from core.auto_match import evaluar_y_notificar_background
from views.components import render_grilla_perfil

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
                    
                    # Sanitize filename: use basename only, strip path traversal, generate safe name
                    original_name = os.path.basename(archivo_cv.name)
                    nombre_seguro = f"{uuid.uuid4().hex[:8]}_{original_name}"
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