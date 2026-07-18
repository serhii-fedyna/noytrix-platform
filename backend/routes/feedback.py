import datetime
import json
import os
import pathlib
import smtplib
from email.message import EmailMessage
from typing import Any

from fastapi import APIRouter, Body, HTTPException


router = APIRouter()


@router.post("/api/contact")
async def api_contact(payload: dict = Body(...)):
    to_email = "noytrixapp@gmail.com"

    name = str(payload.get("name") or "").strip()
    email = str(payload.get("email") or "").strip()
    note = str(payload.get("note") or "").strip()
    product = str(payload.get("product") or "Noytrix Trading Center").strip()
    source = str(payload.get("source") or "mobile_app").strip()

    if not name or not email:
        raise HTTPException(status_code=400, detail="Missing name or contact")

    row = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "to": to_email,
        "name": name,
        "email": email,
        "note": note,
        "product": product,
        "source": source,
    }

    path = pathlib.Path("/root/backend/data/leads.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")

    smtp_user = os.getenv("NOYTRIX_SMTP_USER") or os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("NOYTRIX_SMTP_PASS") or os.getenv("SMTP_PASS", "")

    if smtp_user and smtp_pass:
        msg = EmailMessage()
        msg["Subject"] = "New Noytrix Trading Center request"
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Reply-To"] = email
        msg.set_content(
            f"""New Noytrix request

Product: {product}
Source: {source}

Name: {name}
Contact: {email}

Message:
{note}
"""
        )
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as smtp:
            smtp.login(smtp_user, smtp_pass)
            smtp.send_message(msg)

    return {"ok": True, "saved": True, "emailSent": bool(smtp_user and smtp_pass)}


@router.post("/api/app-feedback")
async def api_app_feedback(payload: dict = Body(...)):
    flow = str(payload.get("flow") or "").strip().lower()
    if flow not in {"positive", "negative"}:
        flow = "unknown"

    def clean_text(value: Any, limit: int = 1200) -> str:
        return str(value or "").strip()[:limit]

    row = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "app": clean_text(payload.get("app"), 80) or "noytrix_mobile",
        "platform": clean_text(payload.get("platform"), 40),
        "flow": flow,
        "language": clean_text(payload.get("language"), 8),
        "installUserId": clean_text(payload.get("installUserId"), 120),
        "userId": clean_text(payload.get("userId"), 160),
        "mostUseful": clean_text(payload.get("mostUseful"), 240),
        "problem": clean_text(payload.get("problem"), 240),
        "requestedFeature": clean_text(payload.get("requestedFeature"), 1200),
        "dailyChange": clean_text(payload.get("dailyChange"), 1200),
        "nps": payload.get("nps") if isinstance(payload.get("nps"), int) else None,
        "raw": {key: value for key, value in payload.items() if key not in {"privateKey", "seed", "seedPhrase"}},
    }

    path = pathlib.Path("/root/backend/data/app_feedback.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(row, ensure_ascii=False) + "\n")

    return {"ok": True, "saved": True}
