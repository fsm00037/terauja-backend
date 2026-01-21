import os
from dotenv import load_dotenv
from email.message import EmailMessage
import ssl
import smtplib

load_dotenv()

def send_credentials_email(email_receiver, access_code):
    email_sender = "infopsicouja@gmail.com"
    password = os.getenv("PASSWORD")

    if not password:
        print("Error: PASSWORD environment variable not set. Email not sent.")
        return

    subject = "Bienvenido a Psicouja"
    body = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: Arial, sans-serif;
            line-height: 1.6;
            color: #333;
        }}
        .container {{
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f9f9f9;
            border-radius: 8px;
        }}
        .header {{
            background-color: #0cc0df;
            color: white;
            padding: 20px;
            text-align: center;
            border-radius: 8px 8px 0 0;
        }}
        .content {{
            background-color: white;
            padding: 20px;
            border-radius: 0 0 8px 8px;
        }}
        .footer {{
            text-align: center;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 3px solid #007a3f;
            font-size: 12px;
            color: #666;
        }}
        .access-code {{
            background-color: #f0f9ff;
            border-left: 4px solid #0cc0df;
            padding: 15px;
            margin: 20px 0;
            border-radius: 4px;
        }}
        .access-code-label {{
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}
        .access-code-value {{
            font-size: 24px;
            font-weight: bold;
            color: #0cc0df;
            font-family: 'Courier New', monospace;
            margin-top: 8px;
            letter-spacing: 2px;
        }}
        .features {{
            margin: 20px 0;
        }}
        .feature-item {{
            display: flex;
            margin: 12px 0;
            align-items: center;
        }}
        .feature-icon {{
            color: #007a3f;
            font-weight: bold;
            font-size: 18px;
            margin-right: 12px;
        }}
        .button {{
            display: block;
            width: fit-content;
            margin: 20px auto 0 auto;
            background-color: #0cc0df;
            color: #ffffff !important;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 5px;
            font-weight: bold;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>¡Bienvenido a Psicouja!</h1>
        </div>
        <div class="content">
            <p>Hola,</p>
            <p>Nos complace recibirte como miembro de nuestra comunidad. En <strong>Psicouja</strong> nos dedicamos a proporcionar recursos y servicios de calidad para tu bienestar.</p>
            
            <div class="features">
                <h3 style="color: #0cc0df; margin-bottom: 15px;">¿Qué puedes hacer en Psicouja?</h3>
                <div class="feature-item">
                    <div class="feature-icon">✓</div>
                    <div><strong>Seguimiento de pacientes:</strong> Mantén un registro detallado del progreso de cada paciente.</div>
                </div>
                <div class="feature-item">
                    <div class="feature-icon">✓</div>
                    <div><strong>Asignar EMAs:</strong> Organiza y gestiona cuestionarios.</div>
                </div>
                <div class="feature-item">
                    <div class="feature-icon">✓</div>
                    <div><strong>Chat con pacientes:</strong> Comunícate directamente en tiempo real con tus pacientes.</div>
                </div>
            </div>

            <div class="access-code">
                <div class="access-code-label">Código de Acceso</div>
                <div class="access-code-value">{access_code}</div>
            </div>

            <p>Si tienes alguna pregunta o necesitas asistencia, no dudes en contactarnos.</p>
            <a href="#" class="button">Acceder a Psicouja</a>
        </div>
        <div class="footer">
            <p>© 2026 Psicouja. Todos los derechos reservados.</p>
            <p>Este es un correo automático. Por favor, no responder a esta dirección.</p>
        </div>
    </div>
</body>
</html>
"""

    em = EmailMessage()
    em["From"] = email_sender
    em["To"] = email_receiver
    em["Subject"] = subject
    em.set_content(body, subtype="html")

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as smtp:
            smtp.login(email_sender, password)
            smtp.sendmail(email_sender, email_receiver, em.as_string())
        print(f"Email sent successfully to {email_receiver}")
    except Exception as e:
        print(f"Failed to send email: {e}")
