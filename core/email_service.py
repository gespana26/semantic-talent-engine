"""Módulo encargado de despachar notificaciones asíncronas vía SMTP."""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import settings


def _bloque_requisitos(cobertura: dict, percentil) -> str:
    """Redacta la justificación de la alerta en términos verificables.

    Un porcentaje de afinidad no le dice al reclutador si merece la pena abrir el
    CV. Saber qué requisitos cumple y cuáles no, sí. Es también la vía por la que
    la decisión automática se vuelve auditable.
    """
    if not cobertura or cobertura.get("sin_requisitos"):
        return ""

    cubiertos = cobertura.get("cubiertos") or []
    faltantes = cobertura.get("faltantes") or []
    por_similitud = cobertura.get("por_similitud") or {}
    total = cobertura.get("total", 0)

    filas = [f"<p><strong>✅ Requisitos cubiertos:</strong> {len(cubiertos)} de {total}</p>"]
    if cubiertos:
        filas.append("<ul style='margin-top:4px;'>")
        for req in cubiertos:
            if req in por_similitud:
                equivalente, similitud = por_similitud[req]
                filas.append(
                    f"<li>{req} <span style='color:#888;font-size:12px;'>"
                    f"(por equivalencia con «{equivalente}», similitud {similitud})</span></li>"
                )
            else:
                filas.append(f"<li>{req}</li>")
        filas.append("</ul>")

    if faltantes:
        filas.append(
            "<p><strong style='color:#C0392B;'>⚠️ No se detectó:</strong> "
            + ", ".join(faltantes) + "</p>"
        )

    if percentil is not None:
        filas.append(
            f"<p><strong>📊 Posición:</strong> percentil {percentil:.0f} del banco de talento "
            f"para esta vacante.</p>"
        )

    return "".join(filas)


def _bloque_factores(desglose: dict) -> str:
    """Explica los dos multiplicadores cuando alguno rebaja la afinidad.

    Solo se mencionan si penalizan. Un factor de 1,0 no aporta información al
    reclutador y alargaría el correo con lo que se da por supuesto.
    """
    if not desglose:
        return ""

    filas = []
    if desglose.get("factor_experiencia", 1) < 1:
        filas.append(
            f"<li>Experiencia: {desglose.get('anios_candidato')} de "
            f"{desglose.get('anios_requeridos')} años exigidos</li>"
        )
    academico = desglose.get("academico") or {}
    if desglose.get("factor_profesion", 1) < 1 and not academico.get("sin_requisitos"):
        faltan = ", ".join(academico.get("faltantes") or [])
        filas.append(f"<li>Formación: no se detectó {faltan}</li>" if faltan
                     else "<li>Formación: no coincide con la exigida</li>")

    if not filas:
        return ""
    return (
        "<p><strong>⚖️ Ajustes aplicados a la afinidad:</strong></p>"
        "<ul style='margin-top:4px;'>" + "".join(filas) + "</ul>"
    )


def enviar_alerta_talento(nombre_candidato: str, silo_destino: str, afinidad: float,
                          extracto: str, cobertura: dict = None, percentil=None,
                          desglose: dict = None):
    """Redacta y despacha un correo HTML al reclutador notificando un alto match."""

    correo_origen = settings.EMAIL_SENDER_USER
    password_app = settings.EMAIL_SENDER_PASSWORD
    correo_destino = settings.EMAIL_RECRUITER_TARGET

    # Si faltan las credenciales, cancelamos silenciosamente para no tumbar la app
    if not correo_origen or not password_app or not correo_destino:
        return

    asunto = f"🚨 ALERTA DE TALENTO: {nombre_candidato} ({afinidad}% Match)"
    
    # Cuerpo del correo en HTML bonito
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #2E86C1;">¡Nuevo Talento Excepcional Detectado! 🎯</h2>
            <p>El sistema ATS ha indexado un currículum que cumple los requisitos de una de tus vacantes activas.</p>

            <div style="background-color: #F4F6F6; padding: 15px; border-left: 4px solid #2E86C1; border-radius: 5px;">
                <p><strong>👤 Candidato:</strong> {nombre_candidato}</p>
                <p><strong>🏢 Vacante:</strong> {silo_destino.replace('-', ' ').title()}</p>
                <p><strong>🔥 Afinidad:</strong> <span style="color: #27AE60; font-weight: bold; font-size: 16px;">{afinidad}%</span></p>
            </div>

            <h3>Por qué te avisamos:</h3>
            {_bloque_requisitos(cobertura, percentil)}
            {_bloque_factores(desglose)}

            <h3>Extracto del Perfil:</h3>
            <p style="font-style: italic; color: #555;">"{extracto}"</p>
            
            <br>
            <p>Por favor, revisa el Dashboard del Reclutador para ver el expediente completo.</p>
            <p style="font-size: 12px; color: #999;">Generado automáticamente por tu ATS Talent Engine.</p>
        </body>
    </html>
    """

    _despachar_html(asunto, html_content)


def enviar_alerta_revision_cv(nombre_candidato: str, correo_candidato: str, vacante_destino: str,
                              veredicto: dict, pdf_path: str = ""):
    """Avisa al reclutador de que un CV requiere revisión manual.

    Se dispara cuando la verificación contra el documento marca sospecha: o el
    perfil declara habilidades que no aparecen escritas en el CV, o el
    documento contiene texto con forma de instrucciones dirigidas a la IA. El
    correo muestra *qué* disparó la sospecha, para que la decisión de descartar
    sea humana e informada; el sistema nunca descarta solo.
    """
    if not veredicto:
        return

    no_verificadas = veredicto.get("no_verificadas") or []
    patrones = veredicto.get("patrones_inyeccion") or []
    verificadas = veredicto.get("verificadas") or []
    ratio = veredicto.get("ratio")

    filas = [f"<p><strong>Motivo:</strong> {veredicto.get('motivo', 'Sospecha en la verificación.')}</p>"]
    if patrones:
        filas.append(
            "<p><strong style='color:#C0392B;'>🚩 Texto con forma de instrucciones para la IA:</strong></p>"
            "<ul>" + "".join(f"<li><code>{p}</code></li>" for p in patrones) + "</ul>"
        )
    if no_verificadas:
        filas.append(
            "<p><strong style='color:#C0392B;'>⚠️ Habilidades declaradas que NO aparecen "
            "escritas en el documento:</strong> " + ", ".join(no_verificadas) + "</p>"
        )
    if ratio is not None:
        filas.append(
            f"<p><strong>Contraste:</strong> {len(verificadas)} habilidades verificadas "
            f"({ratio:.0%}) vía <em>{veredicto.get('canal', '')}</em>.</p>"
        )

    asunto = f"⚠️ REVISIÓN MANUAL: inconsistencia en el CV de {nombre_candidato}"
    html_content = f"""
    <html>
        <body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #C0392B;">Un CV requiere tu revisión manual 🔎</h2>
            <p>El sistema indexó la postulación, pero la verificación del perfil contra el
            texto del documento detectó inconsistencias. <strong>Revisa el PDF original antes
            de considerar a este candidato.</strong></p>

            <div style="background-color: #FDF2F0; padding: 15px; border-left: 4px solid #C0392B; border-radius: 5px;">
                <p><strong>👤 Candidato:</strong> {nombre_candidato}</p>
                <p><strong>📧 Contacto:</strong> {correo_candidato or 'No disponible'}</p>
                <p><strong>🏢 Postulación a:</strong> {str(vacante_destino).replace('-', ' ').title()}</p>
                <p><strong>📄 PDF:</strong> <code>{pdf_path}</code></p>
            </div>

            <h3>Qué disparó la alerta:</h3>
            {"".join(filas)}

            <p style="font-size: 12px; color: #999;">El perfil sigue indexado y visible en el
            Dashboard; esta alerta solo pide verificación humana. Generado automáticamente por
            tu ATS Talent Engine.</p>
        </body>
    </html>
    """
    _despachar_html(asunto, html_content)


def _despachar_html(asunto: str, html_content: str):
    """Envío SMTP compartido por todas las alertas. Nunca propaga errores."""
    correo_origen = settings.EMAIL_SENDER_USER
    password_app = settings.EMAIL_SENDER_PASSWORD
    correo_destino = settings.EMAIL_RECRUITER_TARGET

    if not correo_origen or not password_app or not correo_destino:
        return

    try:
        mensaje = MIMEMultipart("alternative")
        mensaje["Subject"] = asunto
        mensaje["From"] = f"ATS Talent Engine <{correo_origen}>"
        mensaje["To"] = correo_destino
        mensaje.attach(MIMEText(html_content, "html"))

        # Conexión segura al servidor de Gmail
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(correo_origen, password_app)
            server.sendmail(correo_origen, correo_destino, mensaje.as_string())

    except Exception as e:
        print(f"Error silencioso al enviar el correo: {e}")