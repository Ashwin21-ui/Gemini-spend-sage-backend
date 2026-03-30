"""
Email Utility — Async SMTP email sender with branded HTML OTP template.
"""
import logging
import aiosmtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _build_otp_html(otp_code: str, purpose: str) -> str:
    """Build a clean, branded HTML email template for OTP delivery."""
    if purpose == "signup":
        action = "verify your account"
    elif purpose == "password_reset":
        action = "reset your password"
    else:  # login
        action = "log in"
    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Your Spend Sage OTP</title>
  <style>
    body {{ margin: 0; padding: 0; background: #f0f4f8; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
    .wrapper {{ max-width: 520px; margin: 40px auto; background: #ffffff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
    .header {{ background: linear-gradient(135deg, #3b82f6, #22c55e); padding: 36px 40px; text-align: center; }}
    .header h1 {{ margin: 0; color: #ffffff; font-size: 26px; font-weight: 700; letter-spacing: -0.5px; }}
    .header p {{ margin: 6px 0 0; color: rgba(255,255,255,0.85); font-size: 14px; }}
    .body {{ padding: 40px; }}
    .body p {{ color: #4a5568; font-size: 15px; line-height: 1.6; margin: 0 0 20px; }}
    .otp-box {{ background: #f7f9fc; border: 2px dashed #3b82f6; border-radius: 12px; padding: 28px; text-align: center; margin: 24px 0; }}
    .otp-code {{ font-size: 44px; font-weight: 800; letter-spacing: 10px; color: #1e40af; font-family: 'Courier New', monospace; }}
    .otp-note {{ font-size: 13px; color: #718096; margin-top: 10px; }}
    .footer {{ background: #f7f9fc; padding: 24px 40px; text-align: center; border-top: 1px solid #e2e8f0; }}
    .footer p {{ margin: 0; color: #a0aec0; font-size: 12px; }}
  </style>
</head>
<body>
  <div class="wrapper">
    <div class="header">
      <h1>✦ Spend Sage</h1>
      <p>Your personal finance assistant</p>
    </div>
    <div class="body">
      <p>Hello,</p>
      <p>We received a request to <strong>{action}</strong>. Use the code below to complete the process. This code is valid for <strong>5 minutes</strong>.</p>
      <div class="otp-box">
        <div class="otp-code">{otp_code}</div>
        <div class="otp-note">Do not share this code with anyone.</div>
      </div>
      <p>If you didn't request this, you can safely ignore this email.</p>
    </div>
    <div class="footer">
      <p>© 2025 Spend Sage. All rights reserved.</p>
    </div>
  </div>
</body>
</html>
"""


async def send_otp_email(email: str, otp_code: str, purpose: str) -> None:
    settings = get_settings()

    subject = "Your Spend Sage Verification Code"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = email

    html_body = _build_otp_html(otp_code, purpose)
    msg.attach(MIMEText(html_body, "html"))

    try:
        smtp = aiosmtplib.SMTP(
        hostname=settings.SMTP_SERVER,
        port=int(settings.SMTP_PORT),
        start_tls=True,   # TLS handled by the library
    )

        await smtp.connect()
        await smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        await smtp.send_message(msg)
        await smtp.quit()

        logger.info(f"OTP email sent to {email}")

    except Exception as e:
        logger.error(f"SMTP ERROR: {e}")
        raise
