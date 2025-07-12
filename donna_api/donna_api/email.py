from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig
from datetime import datetime

from donna_common.settings import settings

app = FastAPI()

# configure FastAPI-Mail (or use your own SMTP client)
conf = ConnectionConfig(
    MAIL_USERNAME=settings.support_email,
    MAIL_PASSWORD=settings.mail_password,
    MAIL_FROM=settings.verify_email,
    MAIL_PORT=587,
    MAIL_SERVER="mail.privateemail.com",
    MAIL_STARTTLS=True,
    MAIL_SSL_TLS=False
)

async def send_verification_email(email_to: str, token: str):
    verify_url = f"{settings.frontend_url}/verify?token={token}"
    message = MessageSchema(
        subject="Please verify your email",
        recipients=[email_to],
        body=f"""Welcome to Donatell.io. Please click the link below to verify your email address:

{verify_url}

If you did not request this, you can ignore this email.

If you're having trouble, contact us at support@donatell.io.

Best regards,
Donatell.io team""",
        subtype="plain",
        headers={
            "Reply-To": settings.support_email
        }
    )
    fm = FastMail(conf)
    await fm.send_message(message)
