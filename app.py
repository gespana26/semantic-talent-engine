import streamlit as st

from core.security import inicializar_seguridad
from views.dashboard import render_dashboard_reclutador
from views.portal import render_portal_candidato

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="ATS Global Recruitment", page_icon="🎯", layout="wide")

# --- COMPOSITION ROOT DE LA AUTENTICACIÓN ---
# Crear la base de usuarios y validar la clave de firma se piden aquí, de forma
# explícita. Antes ocurrían como efecto secundario de importar `core.security`:
# importar un módulo creaba ficheros, y que la clave se leyera correctamente
# dependía de que alguien hubiera importado antes la configuración. Si falta la
# clave, el sistema se niega a arrancar en vez de servir sesiones que no protegen.
try:
    inicializar_seguridad()
except RuntimeError as fallo_seguridad:
    st.error(str(fallo_seguridad))
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