import os
import tempfile
import threading

import streamlit as st

from config import settings
from core.auto_match import evaluar_y_notificar
from core.data_hygiene import email_valido, primer_dato_valido, telefono_valido
from core.orchestrator import CandidateOrchestrator
from core.vacancy_catalog import obtener_vacantes_publicas
from models.ai_provider import LocalOllamaProvider, OpenAIProvider
from views.components import render_grilla_perfil


def _instanciar_proveedor():
    """Selecciona la estrategia de inferencia declarada en la configuración."""
    tipo_proveedor = settings.AI_PROVIDER_TYPE.lower()
    if tipo_proveedor == "openai":
        return OpenAIProvider()
    if tipo_proveedor == "ollama":
        return LocalOllamaProvider()
    return None


def _reiniciar_postulacion():
    """Descarta el borrador en curso para permitir una nueva postulación."""
    for clave in ("extraccion_pendiente", "cargo_destino", "titulo_vacante"):
        st.session_state.pop(clave, None)


OPCION_BOLSA_GLOBAL = "🌐 Bolsa Global (sin vacante específica)"


def _seleccionar_vacante():
    """Presenta el catálogo de vacantes activas y devuelve la elegida.

    El selector vive fuera del formulario a propósito: Streamlit no re-ejecuta
    el script hasta el envío de un formulario, de modo que el detalle de la
    oferta no se actualizaría al cambiar de vacante.

    Sustituir el campo de texto libre por un catálogo cerrado elimina además la
    creación de silos residuales: antes, un error de tecleo generaba una
    colección nueva y vacía, el auto-match no encontraba vacante y la
    postulación se perdía sin aviso para nadie.
    """
    vacantes = obtener_vacantes_publicas()
    opciones = [OPCION_BOLSA_GLOBAL] + [v["titulo"] for v in vacantes]

    indice = st.selectbox(
        "¿A qué vacante te postulas?",
        options=range(len(opciones)),
        format_func=lambda i: opciones[i],
        help="Elige una vacante para que tu perfil se compare con ella, o postúlate a la bolsa global."
    )

    if indice == 0:
        st.caption("Tu perfil quedará disponible para futuros procesos de selección.")
        return "", OPCION_BOLSA_GLOBAL

    vacante = vacantes[indice - 1]
    if vacante["dias"] is not None:
        st.caption(f"⏳ Quedan {vacante['dias']} días para postularse.")

    with st.expander("📄 Ver el detalle de la vacante", expanded=False):
        if vacante["detalle"]:
            st.text_area("Descripción del cargo:", value=vacante["detalle"], height=260, disabled=True)
        else:
            st.info("Esta vacante no tiene una descripción publicada.")

    return vacante["coleccion"], vacante["titulo"]


def _render_fase_carga():
    """Fase 1: el candidato elige la vacante, sube el documento y la IA propone un perfil."""
    st.markdown("Elige una vacante y sube tu currículum. La IA extraerá tu perfil y podrás **revisarlo y corregirlo** antes de enviarlo.")

    cargo_destino, titulo_vacante = _seleccionar_vacante()

    with st.form("form_carga_cv"):
        archivo_cv = st.file_uploader("Adjunta tu Currículum (PDF)", type=["pdf"])
        submitted = st.form_submit_button("Analizar Currículum", type="primary")

    if not submitted:
        return

    if not archivo_cv:
        st.error("⚠️ Por favor, adjunta un archivo PDF para continuar.")
        return

    ruta_temporal = None
    with st.spinner("🤖 Analizando y extrayendo datos con Inteligencia Artificial..."):
        try:
            # El PDF entra por un archivo temporal: la copia definitiva al storage
            # la realiza el orquestador con un nombre libre de colisiones.
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(archivo_cv.getbuffer())
                ruta_temporal = tmp.name

            orquestador = CandidateOrchestrator(ai_provider=_instanciar_proveedor())
            resultado = orquestador.extract_candidate(pdf_path=ruta_temporal)
        except Exception as e:
            st.error(f"Fallo crítico en el procesamiento multimodal: {e}")
            return
        finally:
            if ruta_temporal:
                try:
                    os.remove(ruta_temporal)
                except OSError:
                    pass

    if not resultado or resultado.get("status") != "success":
        st.error("Hubo un problema al extraer los datos del documento.")
        return

    st.session_state["extraccion_pendiente"] = resultado
    st.session_state["cargo_destino"] = cargo_destino
    st.session_state["titulo_vacante"] = titulo_vacante
    st.rerun()


def _render_fase_confirmacion():
    """Fase 2: el candidato valida los datos de identidad antes de que se persistan.

    Los datos de contacto son la clave de identidad del candidato y el canal por
    el que viaja la alerta de auto-match. Un correo alucinado por el modelo no
    produce un registro incompleto sino un registro *falso*: colisiona con otra
    identidad y envía la notificación a un tercero. Por eso la persistencia se
    condiciona a una confirmación humana explícita.
    """
    extraccion = st.session_state["extraccion_pendiente"]
    datos = extraccion["datos_extraidos"]
    cargo_destino = st.session_state.get("cargo_destino", "")

    st.success("✅ Hemos leído tu currículum. Revisa que tus datos de contacto sean correctos.")
    st.caption(f"Postulación a: **{st.session_state.get('titulo_vacante', OPCION_BOLSA_GLOBAL)}**")

    with st.expander("👀 Ver tu Perfil Estructurado (Auditoría de IA)", expanded=False):
        render_grilla_perfil(datos)

    with st.form("form_confirmacion"):
        st.markdown("#### Confirma tus datos de contacto")

        nombre = st.text_input(
            "Nombre completo *",
            value=primer_dato_valido(datos.get("nombre_completo"))
        )
        correo = st.text_input(
            "Correo electrónico *",
            value=primer_dato_valido(datos.get("correo_electronico")),
            help="Es el canal por el que te contactaremos si tu perfil encaja con la vacante."
        )
        telefono = st.text_input(
            "Número de contacto (móvil o fijo) *",
            value=primer_dato_valido(datos.get("telefono_movil")),
            help="Incluye el prefijo internacional si aplica. Ej: +57 300 111 2233"
        )
        consentimiento = st.checkbox(
            "Autorizo el tratamiento de mis datos personales para procesos de selección. *"
        )

        st.caption("Los campos marcados con * son obligatorios. Corrige cualquier dato que la IA haya leído mal.")
        confirmado = st.form_submit_button("Confirmar y Enviar Postulación", type="primary")

    if st.button("↩️ Subir otro currículum"):
        _reiniciar_postulacion()
        st.rerun()

    if not confirmado:
        return

    # --- Validación bloqueante de los campos de Nivel 1 ---
    # Nombre, correo, teléfono y consentimiento son la identidad y la base legal
    # del registro. No se derivan de la extracción: se confirman.
    errores = []
    if not nombre.strip():
        errores.append("El nombre completo es obligatorio.")

    if not correo.strip():
        errores.append("El correo electrónico es obligatorio.")
    elif not email_valido(correo):
        errores.append("El correo electrónico no tiene un formato válido.")

    if not telefono.strip():
        errores.append("El número de contacto es obligatorio.")
    elif not telefono_valido(telefono):
        errores.append(
            "El número de contacto no es válido. Debe tener entre 7 y 15 dígitos "
            "y admite prefijo internacional, espacios y guiones."
        )

    if not consentimiento:
        errores.append("Debes autorizar el tratamiento de tus datos para continuar.")

    if errores:
        for error in errores:
            st.error(f"⚠️ {error}")
        return

    datos_candidato_web = {
        "nombre": nombre.strip(),
        "correo": correo.strip().lower(),
        "telefono": telefono.strip(),
        "origen": "Portal Web Streamlit",
        "consentimiento": True
    }

    with st.spinner("Indexando tu perfil..."):
        try:
            orquestador = CandidateOrchestrator(ai_provider=_instanciar_proveedor())
            resultado = orquestador.register_candidate(
                candidate_data=extraccion["candidate_data"],
                ruta_persistente_pdf=extraccion["ruta_pdf_fisico"],
                cargo_objetivo=cargo_destino,
                datos_formulario=datos_candidato_web,
                # El veredicto de verificación viaja con la extracción: se persiste
                # en los metadatos y, si marca sospecha, alerta al reclutador.
                # Al candidato no se le muestra: la revisión es asunto interno.
                verificacion=extraccion.get("verificacion")
            )
        except Exception as e:
            st.error(f"Fallo crítico al registrar la postulación: {e}")
            return

    if not resultado or resultado.get("status") != "success":
        st.error("Hubo un problema al registrar tu postulación.")
        return

    # El auto-match se evalúa sobre los datos confirmados, no sobre los inferidos.
    datos_confirmados = dict(resultado.get("datos_extraidos", {}))
    datos_confirmados["nombre_completo"] = datos_candidato_web["nombre"]
    datos_confirmados["correo_electronico"] = datos_candidato_web["correo"]
    datos_confirmados["telefono_movil"] = datos_candidato_web["telefono"]

    if cargo_destino.strip():
        # La decisión de alerta vive en core.auto_match, la misma que usa la CLI:
        # cobertura de requisitos más percentil en el banco, no un umbral fijo de
        # afinidad. El portal la invoca en lugar de reimplementarla.
        # El veredicto de verificación viaja con la evaluación: un perfil
        # sospechoso suprime la alerta de talento (ya disparó la de revisión).
        hilo_alerta = threading.Thread(
            target=evaluar_y_notificar,
            args=(cargo_destino, datos_confirmados, resultado.get("verificacion"))
        )
        hilo_alerta.start()

    _reiniciar_postulacion()
    st.session_state["postulacion_confirmada"] = datos_confirmados
    st.rerun()


def render_portal_candidato():
    """Renderiza el portal de postulación y coordina la ingesta de documentos."""
    st.subheader("Postulación Inteligente de Talento")

    if "postulacion_confirmada" in st.session_state:
        datos = st.session_state["postulacion_confirmada"]
        st.success("✅ ¡Postulación exitosa! Tu perfil ha sido indexado en la base de datos.")
        with st.expander("👀 Ver tu Perfil Registrado", expanded=True):
            render_grilla_perfil(datos)
        if st.button("Postular otro currículum"):
            st.session_state.pop("postulacion_confirmada", None)
            st.rerun()
        return

    if "extraccion_pendiente" in st.session_state:
        _render_fase_confirmacion()
        return

    _render_fase_carga()
