import os
import streamlit as st
from config import settings
from config.settings import clean_collection_name
from core.search_engine import CVSearchEngine
from core.query_translator import QueryTranslator
from core.orchestrator import VacancyOrchestrator
from models.ai_provider import OpenAIProvider, LocalOllamaProvider
from core.security import verificar_credenciales, generar_token, validar_token
from views.components import obtener_resumen_silos, modal_detalle_vacante, modal_perfil_completo

def render_dashboard_reclutador():
    """Renderiza el panel de búsqueda avanzado, protegiéndolo con autenticación JWT."""
    # 🔒 1. VERIFICACIÓN DE SEGURIDAD (STATELESS JWT)
    token = st.session_state.get("jwt_token")
    username = validar_token(token) if token else None

    if not username:
        st.subheader("🔒 Acceso Restringido")
        st.info("Por favor, inicie sesión con sus credenciales de Reclutador.")
        
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            with st.form("login_form", border=True):
                user_input = st.text_input("Usuario")
                pass_input = st.text_input("Contraseña", type="password")
                submit_login = st.form_submit_button("Ingresar al Dashboard", type="primary", use_container_width=True)

                if submit_login:
                    if verificar_credenciales(user_input, pass_input):
                        st.session_state.jwt_token = generar_token(user_input)
                        st.rerun() 
                    else:
                        st.error("❌ Credenciales incorrectas. Intente nuevamente.")
        return 
    
    # 🔓 2. SI LLEGA AQUÍ, EL TOKEN ES VÁLIDO
    col_izq, col_der = st.columns([5, 1])
    with col_izq:
        st.subheader("Buscador Híbrido RAG & Nominal")
    with col_der:
        st.caption(f"👤 Conectado: **{username.upper()}**")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            st.session_state.jwt_token = None
            st.rerun()

    # 📌 Panel lateral
    with st.sidebar:
        st.header("📋 Vacantes Activas (Silos)")
        st.caption("Copie el nombre exacto en la caja de Silo para filtrar.")
        try:
            silos_activos = obtener_resumen_silos()
            if silos_activos:
                for silo in silos_activos:
                    nombre_amigable = silo['nombre'].replace('-', ' ').title()
                    if st.button(f"🏢 {nombre_amigable}", key=f"btn_silo_{silo['nombre']}", use_container_width=True):
                        modal_detalle_vacante(silo['nombre'])
                    
                    if silo['dias'] == "∞":
                        st.caption("⏳ Abierta (Sin límite)")
                    elif silo['dias'] == 0:
                        st.error("⚠️ Expirada")
                    else:
                        st.caption(f"⏳ {silo['dias']} días restantes")
                    
                    st.markdown("---") 
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
    
    # 📄 Registro de vacante desde un PDF (alternativa al comando de texto /crear vacante:)
    with st.expander("📄 Registrar vacante desde un PDF"):
        with st.form("form_vacante_pdf", clear_on_submit=True):
            archivo_vacante = st.file_uploader("Adjunta el PDF de la vacante", type=["pdf"])
            submit_vacante_pdf = st.form_submit_button("Procesar vacante", type="primary")

        if submit_vacante_pdf:
            if not archivo_vacante:
                st.warning("⚠️ Adjunta un archivo PDF para continuar.")
            else:
                with st.spinner("🤖 Leyendo y estructurando la vacante..."):
                    ruta_temp_vacante = None
                    try:
                        os.makedirs(settings.LOCAL_STORAGE_CV_PATH, exist_ok=True)
                        nombre_seguro = "VACANTE_" + archivo_vacante.name.replace(" ", "_")
                        ruta_temp_vacante = os.path.join(settings.LOCAL_STORAGE_CV_PATH, nombre_seguro)
                        with open(ruta_temp_vacante, "wb") as f:
                            f.write(archivo_vacante.getbuffer())

                        tipo_proveedor = settings.AI_PROVIDER_TYPE.lower()
                        proveedor_ia = OpenAIProvider() if tipo_proveedor == "openai" else LocalOllamaProvider()
                        orquestador = VacancyOrchestrator(ai_provider=proveedor_ia)
                        resultado = orquestador.process_and_register_vacancy(pdf_path=ruta_temp_vacante)

                        if resultado.get("status") == "success":
                            st.success(f"✅ ¡Vacante '{resultado.get('coleccion')}' creada exitosamente!")
                            with st.expander("👀 Ver comprensión de la IA (JSON)", expanded=True):
                                st.json(resultado.get("datos_extraidos", {}))
                        else:
                            st.error("Hubo un error al crear la vacante.")
                    except Exception as e:
                        st.error(f"Fallo crítico al procesar la vacante: {e}")
                    finally:
                        if ruta_temp_vacante and os.path.exists(ruta_temp_vacante):
                            try:
                                os.remove(ruta_temp_vacante)
                            except Exception:
                                pass

    st.caption("💡 **Comandos rápidos:** `/crear vacante:` | `/match:` | `/nombre:`")
    prompt_busqueda = st.chat_input("Ej: /crear vacante:, /match:, /nombre: Luis, o búsqueda natural...")
    
    if prompt_busqueda:
        st.session_state.vacante_creada = None  # Limpiar resultado anterior al escribir nuevo prompt
        st.session_state.resultados_busqueda = [] 
        st.session_state.telemetria = None

        comando_original = prompt_busqueda.strip()
        comando = comando_original.lower()

        # --- CASO ESPECIAL: /crear vacante: se procesa fuera del spinner principal ---
        # Así el spinner asociado "Procesando consulta..." no interfiere con st.stop()
        if comando.startswith("/crear vacante:"):
            texto_vacante = comando_original.replace("/crear vacante:", "", 1).strip()
            
            if not texto_vacante:
                st.warning("⚠️ Debes pegar el texto de la vacante después de los dos puntos.")
                st.stop()
                
            with st.spinner("Creando vacante y configurando silo..."):
                tipo_proveedor = settings.AI_PROVIDER_TYPE.lower()
                proveedor_ia = OpenAIProvider() if tipo_proveedor == "openai" else LocalOllamaProvider()
                orquestador = VacancyOrchestrator(ai_provider=proveedor_ia)
                resultado = orquestador.process_and_register_vacancy(raw_text=texto_vacante)
            
            if resultado.get("status") == "success":
                # Guardar en session_state para mostrar DESPUÉS del rerun
                # así el sidebar se actualiza sin perder el resultado en el dashboard
                st.session_state.vacante_creada = resultado
                st.rerun()
            else:
                st.error("Hubo un error al crear la vacante.")
                st.stop()

        # --- RESTO DE COMANDOS: necesitan el motor de búsqueda ---
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
                if comando.startswith("/nombre:"):
                    termino_nominal = comando_original.replace("/nombre:", "", 1).strip()
                    
                    if not termino_nominal:
                        st.warning("⚠️ Debes escribir el nombre después de los dos puntos. Ej: /nombre: Luis")
                        st.stop()
                        
                    candidatos = buscador.buscar_candidato_por_identidad(termino_busqueda=termino_nominal)
                    candidatos_filtrados = [
                        {
                            "nombre": c.get('nombre_completo'), 
                            "correo": c.get('correo_electronico'), 
                            "porcentaje_afinidad": "Léxico", 
                            "pdf_origen": c.get('pdf_file_path'),
                            "perfil_completo_json": json.loads(c.get('raw_json', '{}')) if c.get('raw_json') else c
                        }
                        for c in candidatos if c.get('nombre_completo')
                    ]
                    st.session_state.resultados_busqueda = candidatos_filtrados
                    st.success(f"Búsqueda nominal ejecutada para: '{termino_nominal}'")
                
                elif comando.startswith("/match:"):
                    if coleccion_target == "talento-global-empresa":
                        st.warning("⚠️ El comando /match: requiere un Silo de Vacante específico.")
                        st.stop()
                        
                    texto_vacante = buscador.obtener_perfil_vacante()
                    if not texto_vacante:
                        st.warning("No se encontró el perfil de la vacante para el auto-match.")
                        st.stop()
                        
                    candidatos = buscador.search_candidates(query_text=texto_vacante, limit=10)
                    st.session_state.resultados_busqueda = [c for c in candidatos if c.get('nombre')]
                    st.success(f"Auto-Match ejecutado contra el perfil de la vacante '{silo_objetivo}'.")

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

    # Mostrar resultado de creación de vacante (persiste tras st.rerun())
    if st.session_state.get("vacante_creada"):
        resultado = st.session_state.vacante_creada
        st.success(f"✅ ¡Vacante '{resultado.get('coleccion')}' creada exitosamente!")
        with st.expander("👀 Ver comprensión de la IA (JSON)", expanded=True):
            st.json(resultado.get("datos_extraidos", {}))
        st.info("🔄 Sidebar actualizado. Puedes seguir operando en el dashboard.")

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