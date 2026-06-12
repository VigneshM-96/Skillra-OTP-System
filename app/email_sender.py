"""
Email delivery — supports plain SMTP and SendGrid.
Switch via USE_SENDGRID=true in .env
"""

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx

from app.config import get_settings

settings = get_settings()


# ── HTML email template ────────────────────────────────────────────────────

def _build_html(otp: str, expire_minutes: int) -> str:
    return f"""
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:30px;">
  <div style="max-width:480px;margin:auto;background:#fff;border-radius:8px;
              padding:40px;box-shadow:0 2px 8px rgba(0,0,0,.1);">
    <h2 style="color:#333;margin-top:0;">Your Verification Code</h2>
    <p style="color:#555;">Use the code below to complete your verification.
       It expires in <strong>{expire_minutes} minutes</strong>.</p>
    <div style="font-size:40px;font-weight:bold;letter-spacing:10px;
                text-align:center;color:#4F46E5;padding:20px 0;">
      {otp}
    </div>
    <p style="color:#999;font-size:13px;">
      If you didn't request this, you can safely ignore this email.
      Never share this code with anyone.
    </p>
  </div>
</body>
</html>
"""


def _build_plain(otp: str, expire_minutes: int) -> str:
    return (
        f"Your verification code is: {otp}\n"
        f"It expires in {expire_minutes} minutes.\n"
        f"Never share this code with anyone."
    )


# ── SMTP sender ────────────────────────────────────────────────────────────

async def send_otp_smtp(to_email: str, otp: str) -> None:
    expire_minutes = settings.otp_expire_seconds // 60

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Your Verification Code"
    msg["From"]    = f"{settings.smtp_from_name} <{settings.smtp_from_email}>"
    msg["To"]      = to_email

    msg.attach(MIMEText(_build_plain(otp, expire_minutes), "plain"))
    msg.attach(MIMEText(_build_html(otp, expire_minutes),  "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(settings.smtp_username, settings.smtp_password)
        server.sendmail(settings.smtp_from_email, to_email, msg.as_string())


# ── SendGrid sender ────────────────────────────────────────────────────────

async def send_otp_sendgrid(to_email: str, otp: str) -> None:
    expire_minutes = settings.otp_expire_seconds // 60

    payload = {
        "personalizations": [{"to": [{"email": to_email}]}],
        "from": {
            "email": settings.sendgrid_from_email,
            "name":  settings.sendgrid_from_name,
        },
        "subject": "Your Verification Code",
        "content": [
            {"type": "text/plain", "value": _build_plain(otp, expire_minutes)},
            {"type": "text/html",  "value": _build_html(otp, expire_minutes)},
        ],
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://api.sendgrid.com/v3/mail/send",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.sendgrid_api_key}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()


# ── Unified entry point ────────────────────────────────────────────────────

async def send_otp_email(to_email: str, otp: str) -> None:
    """
    Automatically picks SendGrid or SMTP based on USE_SENDGRID env var.
    Raises on delivery failure — let the caller handle the HTTP response.
    """
    if settings.use_sendgrid:
        await send_otp_sendgrid(to_email, otp)
    else:
        await send_otp_smtp(to_email, otp)