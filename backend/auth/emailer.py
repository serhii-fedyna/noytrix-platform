# auth/emailer.py
import os, smtplib
from email.mime.text import MIMEText

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
FROM_EMAIL = os.getenv("FROM_EMAIL", "no-reply@noytrix.app")

def send_code_email(to_email: str, code: str, purpose: str):
    subj = "Ваш код подтверждения" if purpose == "register" else "Код для восстановления пароля"
    body = f"Ваш код: {code}\nОн действителен 15 минут."
    if not SMTP_HOST or not SMTP_USER:
        print(f"[DEV EMAIL] to={to_email} purpose={purpose} code={code}")
        return
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subj
    msg["From"] = FROM_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.send_message(msg)
