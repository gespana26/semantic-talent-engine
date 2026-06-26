"""Módulo encargado de despachar notificaciones asíncronas vía SMTP."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import settings

def enviar_alerta_talento(nombre_candidato: str, silo_destino: str, afinidad: float, extracto: str):
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
            <p>El sistema ATS ha indexado un currículum que supera el umbral de idoneidad para una de tus vacantes activas.</p>
            
            <div style="background-color: #F4F6F6; padding: 15px; border-left: 4px solid #2E86C1; border-radius: 5px;">
                <p><strong>👤 Candidato:</strong> {nombre_candidato}</p>
                <p><strong>🏢 Vacante:</strong> {silo_destino.replace('-', ' ').title()}</p>
                <p><strong>🔥 Afinidad:</strong> <span style="color: #27AE60; font-weight: bold; font-size: 16px;">{afinidad}%</span></p>
            </div>
            
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