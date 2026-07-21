"""Módulo encargado de despachar notificaciones asíncronas vía SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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