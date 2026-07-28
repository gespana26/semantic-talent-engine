import chromadb
import streamlit as st

from config import settings
from core.vacancy_catalog import obtener_silos_del_reclutador


def obtener_resumen_silos():
    """Silos y su vigencia para el panel lateral del reclutador.

    Delega en `core.vacancy_catalog`. Antes calculaba lo suyo por su cuenta,
    recorriendo la colección entera —con el `raw_json` de cada candidato— para
    leer un único registro que se direcciona por clave, y repitiéndolo en cada
    repintado de Streamlit. Con la lógica en el dominio, esta capa vuelve a
    limitarse a presentar, y la diferencia de criterio frente al portal pasa a
    ser una decisión escrita en un sitio en lugar de una divergencia accidental
    entre dos ficheros.
    """
    return obtener_silos_del_reclutador()

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

@st.dialog("📄 Detalle Completo de la Vacante", width="large")
def modal_detalle_vacante(nombre_silo):
    """Renderiza el texto original de la vacante leyendo los metadatos de ChromaDB."""
    st.markdown(f"### 🏢 {nombre_silo.replace('-', ' ').title()}")
    
    with st.spinner("Consultando expediente original..."):
        try:
            cliente = chromadb.PersistentClient(path=settings.CHROMA_DB_PATH)
            coleccion = cliente.get_collection(name=nombre_silo)
            
            datos = coleccion.get(include=["metadatas", "documents"])
            texto_a_mostrar = None
            
            if datos and datos.get("metadatas"):
                for meta in datos["metadatas"]:
                    if meta and "texto_original" in meta:
                        texto_a_mostrar = meta["texto_original"]
                        break
            
            if not texto_a_mostrar and datos and datos.get("documents") and len(datos["documents"]) > 0:
                texto_a_mostrar = datos["documents"][0]
                st.caption("⚠️ Nota: Esta es una vacante legacy. Mostrando versión optimizada para RAG.")
                
            if texto_a_mostrar:
                st.text_area("Descripción del Cargo:", value=texto_a_mostrar, height=300, disabled=True)
            else:
                st.warning("No se encontró información para esta vacante.")
                
        except Exception as e:
            st.error(f"Error crítico al leer la base de datos: {e}")

@st.dialog("Expediente Completo del Candidato", width="large")
def modal_perfil_completo(candidato):
    """Renderiza una ventana emergente (Modal) inyectando el componente estandarizado."""
    st.markdown(f"## 👤 {candidato.get('nombre', 'Desconocido')}")
    st.caption(f"📧 **Contacto:** {candidato.get('correo', 'No registrado')} | 📄 **Ruta Física:** `{candidato.get('pdf_origen', 'No disponible')}`")
    
    json_data = candidato.get('perfil_completo_json', {})
    render_grilla_perfil(json_data)