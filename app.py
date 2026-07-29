import streamlit as st

from config.providers import verificar_configuracion as verificar_proveedor
from core.security import inicializar_seguridad
from views.dashboard import render_dashboard_reclutador
from views.portal import render_portal_candidato

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ATS Global Recruitment", page_icon="🎯", layout="wide")

# --- COMPOSITION ROOT ---
# Todo lo que puede estar mal configurado se comprueba aquí, antes de dibujar
# nada. Crear la base de usuarios y validar la clave de firma ocurrían antes como
# efecto secundario de importar `core.security`, y la ausencia de clave de OpenAI
# no se detectaba en absoluto: el cliente se construía con un valor de relleno y
# el fallo reaparecía mucho después como «Fallo crítico en el procesamiento
# multimodal», un mensaje que no menciona la causa.
#
# El criterio es que una configuración incompleta impida arrancar, con un texto
# que diga qué falta y cómo resolverlo. Es más barato leer un error al abrir la
# aplicación que diagnosticarlo a mitad de una postulación.
try:
    inicializar_seguridad()
    verificar_proveedor()
except (RuntimeError, ValueError) as fallo_configuracion:
    st.error(str(fallo_configuracion))
    st.stop()

# --- INICIALIZACIÓN DE ESTADOS GLOBALES ---
if "resultados_busqueda" not in st.session_state:
    st.session_state.resultados_busqueda = []
if "telemetria" not in st.session_state:
    st.session_state.telemetria = None
if "jwt_token" not in st.session_state:
    st.session_state.jwt_token = None

# =====================================================================
# ENRUTADOR PRINCIPAL (ROUTER)
# =====================================================================
def main():
    st.title("Sistema ATS - Talent Engine")
    st.markdown("---")
    
    # Declaración de la estructura base
    tab1, tab2 = st.tabs(["🎓 Portal del Candidato", "🏢 Dashboard del Reclutador"])
    
    # Renderizado Modular
    with tab1:
        render_portal_candidato()
        
    with tab2:
        render_dashboard_reclutador()

if __name__ == "__main__":
    main()