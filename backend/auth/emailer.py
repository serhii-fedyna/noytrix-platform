import os
import smtplib
from email.mime.text import MIMEText

from dotenv import load_dotenv


def _smtp_config() -> dict:
    load_dotenv("/root/backend/.env")
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", "587") or "587")
    smtp_user = (
        os.getenv("SMTP_USER")
        or os.getenv("NOYTRIX_SMTP_USER")
        or ""
    ).strip()
    smtp_pass = (
        os.getenv("SMTP_PASS")
        or os.getenv("NOYTRIX_SMTP_PASS")
        or ""
    ).strip()
    mail_from = (
        os.getenv("MAIL_FROM")
        or os.getenv("FROM_EMAIL")
        or smtp_user
        or "no-reply@noytrix.app"
    ).strip()

    return {
        "host": smtp_host,
        "port": smtp_port,
        "user": smtp_user,
        "password": smtp_pass,
        "from": mail_from,
    }


def _email_html(code: str, purpose: str) -> str:
    is_reset = purpose == "reset"
    title = "Reset your password" if is_reset else "Your verification code"
    subtitle = (
        "Use this code to reset your Noytrix account password."
        if is_reset
        else "Use this code to verify your Noytrix account."
    )
    escaped_code = str(code).strip()

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#070914;font-family:Arial,Helvetica,sans-serif;color:#ffffff;">
    <div style="max-width:680px;margin:0 auto;padding:28px 14px;">
      <div style="text-align:center;margin-bottom:22px;">
        <div style="font-size:32px;font-weight:900;letter-spacing:8px;color:#ffffff;">
          NOYTRI<span style="color:#ffb020;">X</span>
        </div>
        <div style="margin-top:8px;color:#9aa3b8;font-size:15px;">
          Scam and Wallet Protection
        </div>
      </div>

      <div style="background:linear-gradient(180deg,#111827 0%,#090d18 100%);border:1px solid rgba(255,176,32,.35);border-radius:26px;padding:30px 22px;box-shadow:0 0 40px rgba(255,176,32,.14);">
        <div style="text-align:center;">
          <div style="width:70px;height:70px;margin:0 auto 20px;border-radius:22px;background:rgba(255,176,32,.12);border:1px solid rgba(255,176,32,.45);line-height:70px;font-size:30px;">NX</div>
          <h1 style="margin:0;color:#ffffff;font-size:32px;line-height:1.2;">{title}</h1>
          <p style="margin:16px auto 26px;max-width:480px;color:#b8c0d4;font-size:17px;line-height:1.6;">
            {subtitle}<br>Enter the code below to continue.
          </p>
        </div>

        <div style="margin:0 auto 26px;max-width:460px;border-radius:22px;border:1px solid rgba(255,176,32,.75);background:#080c18;padding:26px 14px;text-align:center;">
          <div style="color:#ffb020;font-size:42px;font-weight:900;letter-spacing:8px;line-height:1;white-space:nowrap;">{escaped_code}</div>
          <div style="margin-top:18px;color:#b8c0d4;font-size:15px;">This code is valid for 15 minutes.</div>
        </div>

        <div style="border-radius:18px;border:1px solid rgba(255,255,255,.10);background:rgba(255,255,255,.035);padding:20px;margin-bottom:24px;">
          <div style="font-size:18px;font-weight:800;color:#ffffff;margin-bottom:8px;">Security tips</div>
          <div style="color:#b8c0d4;font-size:15px;line-height:1.6;">
            Never share this code with anyone. Noytrix will never ask for your password or verification code.
          </div>
        </div>

        <div style="text-align:center;margin-top:28px;color:#9aa3b8;font-size:14px;line-height:1.6;">
          Need help? Contact us at
          <a href="mailto:noytrixapp@gmail.com" style="color:#ffb020;text-decoration:none;">noytrixapp@gmail.com</a>
          <br><br>
          2026 Noytrix. All rights reserved.
        </div>
      </div>
    </div>
  </body>
</html>"""


def send_code_email(to_email: str, code: str, purpose: str = "register") -> None:
    cfg = _smtp_config()
    if not cfg["host"] or not cfg["user"] or not cfg["password"]:
        raise RuntimeError("smtp_not_configured")

    is_reset = purpose == "reset"
    subject = "Noytrix password reset code" if is_reset else "Noytrix verification code"
    msg = MIMEText(_email_html(code, purpose), "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = f"Noytrix <{cfg['from']}>"
    msg["To"] = to_email

    with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
        server.starttls()
        server.login(cfg["user"], cfg["password"])
        server.sendmail(cfg["from"], [to_email], msg.as_string())
