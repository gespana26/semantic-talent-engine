import os
import streamlit as st
import json
import chromadb

# --- IMPORTACIONES LOCALES DE TU PROYECTO ---
from config import settings
from config.settings import clean_collection_name
from core.search_engine import CVSearchEngine
from core.query_translator import QueryTranslator
from core.orchestrator import CandidateOrchestrator
from models.ai_provider import OpenAIProvider, LocalOllamaProvider

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ATS Global Recruitment", page_icon="🎯", layout="wide")

# --- INICIALIZACIÓN DE ESTADOS ---
if "resultados_busqueda" not in st.session_state:
    st.session_state.resultados_busqueda = []
if "telemetria" not in st.session_state:
    st.session_state.telemetria = None


def render_grilla_perfil(json_data):
    """Componente visual estandarizado para mostrar el perfil extraído por la IA."""
    st.markdown("### 🎯 Perfil Profesional")
    st.info(json_data.get('perfil_profesional', 'El candidato no especificó un perfil profesional.'))
    
    st.markdown("### 📊 Datos Clave")
    col1, col2, col3 = st.columns(3)
    col1.metric("Años de Experiencia", json_data.get('anios_experiencia_total', 0))
    col2.metric("Nivel Académico Máximo", json_data.get('nivel_academico_maximo', 'No especificado'))
    col3.metric("Modalidad / Disponibilidad", "A evaluar") 
    
    st.divider()

    st.markdown("### 🛠️ Competencias (Skills)")
    col_h, col_s = st.columns(2)
    with col_h:
        st.markdown("**Hard Skills (Técnicas)**")
        hard_skills = json_data.get('hard_skills', [])
        if isinstance(hard_skills, list) and hard_skills:
            st.markdown(" ".join([f"`{skill}`" for skill in hard_skills]))
        else:
            st.write("No extraídas.")

    with col_s:
        st.markdown("**Soft Skills (Blandas)**")
        soft_skills = json_data.get('soft_skills', [])
        if isinstance(soft_skills, list) and soft_skills:
            st.markdown(" ".join([f"`{skill}`" for skill in soft_skills]))
        else:
            st.write("No extraídas.")

    st.divider()

    st.markdown("### 💼 Historial Profesional")
    experiencia = json_data.get('historial_laboral', json_data.get('experiencia_laboral', []))
    if isinstance(experiencia, list) and len(experiencia) > 0:
        for exp in experiencia:
            cargo = exp.get('cargo', 'Cargo no definido')
            empresa = exp.get('empresa', 'Empresa no definida')
            
            with st.expander(f"🏢 {cargo} en {empresa}"):
                if 'duracion_anios' in exp:
                    st.write(f"**Duración estimada:** {exp.get('duracion_anios')} años")
                elif 'meses_duracion' in exp:
                    st.write(f"**Duración estimada:** {exp.get('meses_duracion')} meses")
                else:
                    st.write("**Duración estimada:** No especificada")
                
                responsabilidades = exp.get('responsabilidades', '')
                if responsabilidades:
                    st.write(f"**Responsabilidades:** {responsabilidades}")
    else:
        st.write("No se registraron experiencias laborales.")

# =====================================================================
# COMPONENTES VISUALES (MODALES)
# =====================================================================
@st.dialog("Expediente Completo del Candidato", width="large")
def modal_perfil_completo(candidato):
    """Renderiza una ventana emergente (Modal) inyectando el componente estandarizado."""
    st.markdown(f"## 👤 {candidato.get('nombre', 'Desconocido')}")
    st.caption(f"📧 **Contacto:** {candidato.get('correo', 'No registrado')} | 📄 **Ruta Física:** `{candidato.get('pdf_origen', 'No disponible')}`")
    
    # Inyectamos el componente visual reutilizable
    json_data = candidato.get('perfil_completo_json', {})
    render_grilla_perfil(json_data)

# =====================================================================
# PESTAÑA 1: PORTAL DEL CANDIDATO
# =====================================================================
def render_portal_candidato():
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
                
            # Spinner genérico (ahora dinámico según el proveedor)
            with st.spinner("🤖 Analizando y extrayendo datos con Inteligencia Artificial..."):
                try:
                    # 1. Puente RAM -> Disco Duro (Usando configuración global DRY)
                    directorio_storage = settings.LOCAL_STORAGE_CV_PATH
                    os.makedirs(directorio_storage, exist_ok=True)
                    
                    nombre_seguro = archivo_cv.name.replace(" ", "_")
                    ruta_fisica = os.path.join(directorio_storage, nombre_seguro)
                    
                    with open(ruta_fisica, "wb") as f:
                        f.write(archivo_cv.getbuffer())
                    
                    # Datos vitales para el Orquestador (el teléfono se usa en el nombre del archivo)
                    datos_candidato_web = {
                        "telefono": "0000",
                        "origen": "Portal Web Streamlit"
                    }
                        
                    # 2. INYECCIÓN DINÁMICA DEL PROVEEDOR COGNITIVO (.env)
                    proveedor_ia = None
                    tipo_proveedor = settings.AI_PROVIDER_TYPE.lower()
                    #nombre_modelo = settings.MODEL_NAME
                    
                    if tipo_proveedor == "openai":
                        proveedor_ia = OpenAIProvider()
                    elif tipo_proveedor == "ollama":
                        proveedor_ia = LocalOllamaProvider()
                    else:
                        st.error(f"Proveedor '{tipo_proveedor}' no soportado en la configuración.")
                        st.stop()
                    
                    # 3. Activación del Back-End
                    orquestador = CandidateOrchestrator(ai_provider=proveedor_ia)
                    
                    # Ejecutamos la arquitectura de Doble Indexación
                    resultado = orquestador.process_and_register_candidate(
                        pdf_path=ruta_fisica,
                        cargo_objetivo=cargo_destino,
                        datos_formulario=datos_candidato_web
                    )
                    
                    if resultado and resultado.get("status") == "success":
                        st.success("✅ ¡Postulación exitosa! Tu perfil ha sido indexado en la base de datos.")
                        with st.expander("👀 Ver los datos extraídos de tu CV"):
                            if resultado and resultado.get("status") == "success":
                                st.success("✅ ¡Postulación exitosa! Tu perfil ha sido indexado en la base de datos.")

                                with st.expander("👀 Ver tu Perfil Estructurado (Auditoría de IA)", expanded=True):
                                    # Inyectamos la misma grilla que ve el reclutador
                                    datos_extraidos = resultado.get("datos_extraidos", {})
                                    render_grilla_perfil(datos_extraidos)
                    else:
                        st.error("Hubo un problema al extraer los datos del documento.")

                        
                except Exception as e:
                    st.error(f"Fallo crítico en el procesamiento multimodal: {e}")

# =====================================================================
# PESTAÑA 2: DASHBOARD DEL RECLUTADOR
# =====================================================================
def render_dashboard_reclutador():
    st.subheader("Buscador Híbrido RAG & Nominal")
    
    # Panel lateral con silos activos
    with st.sidebar:
        st.header("📋 Vacantes Activas (Silos)")
        st.caption("Copie el nombre exacto en la caja de Silo para filtrar.")
        try:
            cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
            colecciones = cliente.list_collections()
            silos = [col.name for col in colecciones if col.name != "talento-global-empresa"]
            
            if silos:
                for silo in silos:
                    st.code(silo, language="text")
            else:
                st.info("No hay silos específicos registrados aún.")
        except Exception as e:
            st.error(f"No se pudieron cargar los silos: {e}")

    # Enrutamiento y Buscador
    silo_objetivo = st.text_input(
        "Silo de Vacante (Deje en blanco para Búsqueda Global):", 
        placeholder="Ej: Project Manager"
    )
    
    coleccion_target = clean_collection_name(silo_objetivo) if silo_objetivo.strip() else "talento-global-empresa"
    prompt_busqueda = st.chat_input("Ej: /match, /nombre Luis, o búsqueda natural 'experiencia en...'")
    
    if prompt_busqueda:
        st.session_state.resultados_busqueda = [] 
        st.session_state.telemetria = None
        
        # Blindaje de colección inexistente
        try:
            buscador = CVSearchEngine(collection_name=coleccion_target)
        except Exception as e:
            if "does not exist" in str(e).lower():
                st.warning(f"⚠️ El silo de vacante '{silo_objetivo}' no existe. Verifique el nombre en el panel lateral.")
                st.stop()
            else:
                st.error(f"Fallo crítico en el motor de base de datos: {e}")
                st.stop()
        
        with st.spinner("Procesando consulta..."):
            try:
                comando = prompt_busqueda.lower().strip()
                
                # ESTRATEGIA A: NOMINAL
                if comando.startswith("/nombre "):
                    termino_nominal = prompt_busqueda[8:].strip()
                    candidatos = buscador.buscar_candidato_por_identidad(termino_busqueda=termino_nominal)
                    candidatos_filtrados = [
                        {
                            "nombre": c.get('nombre_completo'), 
                            "correo": c.get('correo_electronico'), 
                            "porcentaje_afinidad": "Léxico", 
                            "pdf_origen": c.get('pdf_file_path'),
                            "perfil_completo_json": c
                        }
                        for c in candidatos if c.get('nombre_completo')
                    ]
                    st.session_state.resultados_busqueda = candidatos_filtrados
                    st.success(f"Búsqueda nominal ejecutada para: '{termino_nominal}'")
                
                # ESTRATEGIA B: AUTO-MATCH
                elif comando == "/match":
                    if coleccion_target == "talento-global-empresa":
                        st.warning("⚠️ El comando /match requiere un Silo de Vacante específico.")
                        st.stop()
                        
                    texto_vacante = buscador.obtener_perfil_vacante()
                    if not texto_vacante:
                        st.warning("No se encontró el perfil de la vacante para el auto-match.")
                        st.stop()
                        
                    candidatos = buscador.search_candidates(query_text=texto_vacante, limit=10)
                    st.session_state.resultados_busqueda = [c for c in candidatos if c.get('nombre')]
                    st.success(f"Auto-Match ejecutado contra el perfil de la vacante '{silo_objetivo}'.")

                # ESTRATEGIA C: RAG NATURAL
                else:
                    traductor = QueryTranslator()
                    query_estructurada = traductor.translate_prompt_to_chroma(prompt_busqueda)
                    
                    if settings.DEBUG_MODE:
                        st.session_state.telemetria = {
                            "foco": query_estructurada.query_text_conceptual,
                            "filtro": query_estructurada.where_filter
                        }
                    
                    filtro = query_estructurada.where_filter if query_estructurada.where_filter else None
                    candidatos = buscador.search_candidates(
                        query_text=query_estructurada.query_text_conceptual, limit=5, where_filter=filtro
                    )
                    st.session_state.resultados_busqueda = [c for c in candidatos if c.get('nombre')]
                    st.success("Búsqueda semántica híbrida completada.")
                    
            except Exception as e:
                st.error(f"Error en el motor de búsqueda: {e}")

    # Renderizado de Resultados
    if st.session_state.resultados_busqueda:
        st.markdown(f"### Resultados Encontrados: {len(st.session_state.resultados_busqueda)}")
        for idx, cand in enumerate(st.session_state.resultados_busqueda):
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                
                with col1:
                    st.markdown(f"#### #{idx+1} - {cand.get('nombre', 'Desconocido').upper()}")
                    st.caption(f"📧 `{cand.get('correo', 'Sin correo')}` | 📄 `{cand.get('pdf_origen', '')}`")
                    
                    json_data = cand.get('perfil_completo_json', {})
                    extracto = json_data.get('perfil_profesional', 'Extracto no disponible')[:150] + "..."
                    st.write(f"**Extracto:** {extracto}")
                
                with col2:
                    afinidad = cand.get('porcentaje_afinidad', 0)
                    if isinstance(afinidad, (int, float)):
                        st.metric(label="Afinidad", value=f"{afinidad}%")
                    else:
                        st.metric(label="Match", value="Léxico")
                        
                    if st.button("Ver Perfil Completo", key=f"btn_cv_{idx}", use_container_width=True):
                        modal_perfil_completo(cand)

    # Telemetría
    if st.session_state.telemetria:
        with st.expander("📊 Log de Telemetría (Intent Translator)", expanded=False):
            st.json(st.session_state.telemetria)

# =====================================================================
# BLOQUE PRINCIPAL
# =====================================================================
def main():
    st.title("Sistema ATS - Talent Engine")
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["🎓 Portal del Candidato", "🏢 Dashboard del Reclutador"])
    
    with tab1:
        render_portal_candidato()
        
    with tab2:
        render_dashboard_reclutador()

if __name__ == "__main__":
    main()