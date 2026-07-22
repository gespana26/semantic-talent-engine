import streamlit as st

from views.dashboard import render_dashboard_reclutador
from views.portal import render_portal_candidato

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ATS Global Recruitment", page_icon="🎯", layout="wide")

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