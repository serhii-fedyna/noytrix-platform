# auth/router.py
from fastapi import APIRouter, Depends, HTTPException, status, Body
from auth.deps import get_current_user
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import hashlib, random, string, requests

from db import get_db, Base, engine
from auth.models import User, EmailCode, RefreshToken
from auth.schemas import (
    RegisterStartReq, RegisterVerifyReq, LoginReq, UserPublic, AuthBundle, Tokens,
    ResetStartReq, ResetConfirmReq, GoogleAuthReq
)
from auth.security import hash_password, verify_password, make_access_token, make_refresh_token
from auth.emailer import send_code_email

Base.metadata.create_all(bind=engine)

router = APIRouter(tags=["auth"])

CODE_TTL_MINUTES = 15
REGISTER_RESEND_COOLDOWN_SECONDS = 30
RESET_RESEND_COOLDOWN_SECONDS = 30


@router.get("/health")
def auth_health():
    return {"ok": True}


def make_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def utcnow() -> datetime:
    return datetime.utcnow().replace(microsecond=0)


def calc_expires_at(now: datetime | None = None) -> datetime:
    now = now or utcnow()
    return now + timedelta(minutes=CODE_TTL_MINUTES)


def calc_sent_at(expires_at: datetime) -> datetime:
    return expires_at - timedelta(minutes=CODE_TTL_MINUTES)


def enforce_code_cooldown(
    rec: EmailCode | None,
    cooldown_seconds: int,
    message: str,
) -> None:
    if not rec or not rec.expires_at:
        return

    last_sent_at = calc_sent_at(rec.expires_at)
    seconds_passed = (utcnow() - last_sent_at).total_seconds()

    if seconds_passed < cooldown_seconds:
        seconds_left = int(cooldown_seconds - seconds_passed)
        if seconds_left < 1:
            seconds_left = 1
        raise HTTPException(
            status_code=429,
            detail=f"{message} Повторите через {seconds_left} сек.",
        )


@router.get("/me", response_model=UserPublic)
def me(current: User = Depends(get_current_user)):
    return current


@router.post("/register", response_model=AuthBundle)
def register_legacy(payload: dict = Body(...), db: Session = Depends(get_db)):
    """
    Упрощённая регистрация в один шаг для старого клиента:
    ожидает { email, password, confirm?, nick? } и сразу создаёт user.
    """
    email = str(payload.get("email", "")).lower().strip()
    password = str(payload.get("password", "")).strip()
    confirm = payload.get("confirm")
    nick = (payload.get("nick") or (email.split("@")[0] if "@" in email else "User")).strip()

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email и пароль обязательны")

    if confirm is not None and confirm != password:
        raise HTTPException(status_code=400, detail="Пароли не совпадают")

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован. Войдите.")

    user = User(
        email=email,
        name=nick,
        nick=nick,
        password_hash=hash_password(password),
        provider="local",
        email_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    access = make_access_token(user.id)
    refresh, exp = make_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh, expires_at=exp))
    db.commit()

    return {
        "user": user,
        "tokens": {
            "access_token": access,
            "refresh_token": refresh,
        },
    }


@router.post("/register/start")
def register_start(body: RegisterStartReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Email уже зарегистрирован. Войдите.")

    rec = (
        db.query(EmailCode)
        .filter(EmailCode.email == email, EmailCode.purpose == "register")
        .first()
    )

    enforce_code_cooldown(
        rec,
        REGISTER_RESEND_COOLDOWN_SECONDS,
        "Код уже был отправлен.",
    )

    code = make_code()
    code_hash = sha(code)
    expires_at = calc_expires_at()

    if rec:
        rec.code_hash = code_hash
        rec.expires_at = expires_at
    else:
        rec = EmailCode(
            email=email,
            code_hash=code_hash,
            purpose="register",
            expires_at=expires_at,
        )

    db.add(rec)
    db.commit()

    send_code_email(email, code, "register")
    return {"ok": True, "message": "Код отправлен на email."}


@router.post("/register/verify", response_model=AuthBundle)
def register_verify(body: RegisterVerifyReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    code = body.code.strip()

    rec = (
        db.query(EmailCode)
        .filter(EmailCode.email == email, EmailCode.purpose == "register")
        .first()
    )

    if not rec or rec.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Код просрочен. Запросите новый.")

    if sha(code) != rec.code_hash:
        raise HTTPException(status_code=400, detail="Неверный код.")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, email_verified=True, provider="local")
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.email_verified = True
        db.commit()

    access = make_access_token(user.id)
    refresh, exp = make_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh, expires_at=exp))
    db.query(EmailCode).filter(EmailCode.id == rec.id).delete()
    db.commit()

    return {
        "user": user,
        "tokens": {"access_token": access, "refresh_token": refresh}
    }


@router.post("/register/complete", response_model=AuthBundle)
def register_complete(body: RegisterStartReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.email_verified:
        raise HTTPException(status_code=400, detail="Сначала подтвердите email кодом.")

    if user.password_hash:
        raise HTTPException(status_code=409, detail="Пароль уже установлен. Войдите.")

    user.nick = body.nick.strip()
    user.name = body.nick.strip()
    user.password_hash = hash_password(body.password)
    user.provider = "local"
    db.commit()
    db.refresh(user)

    access = make_access_token(user.id)
    refresh, exp = make_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh, expires_at=exp))
    db.commit()

    return {"user": user, "tokens": {"access_token": access, "refresh_token": refresh}}


@router.post("/login", response_model=AuthBundle)
def login(body: LoginReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверные email или пароль")

    access = make_access_token(user.id)
    refresh, exp = make_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh, expires_at=exp))
    db.commit()

    return {"user": user, "tokens": {"access_token": access, "refresh_token": refresh}}


def _refresh(token: str, db: Session) -> dict:
    rec = db.query(RefreshToken).filter(RefreshToken.token == token).first()
    if not rec or rec.expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Refresh недействителен")

    access = make_access_token(rec.user_id)
    return {"access_token": access, "refresh_token": rec.token, "token_type": "bearer"}


@router.post("/token/refresh", response_model=Tokens)
def refresh_token_post(token: str, db: Session = Depends(get_db)):
    return _refresh(token, db)


@router.get("/token/refresh", response_model=Tokens)
def refresh_token_get(token: str, db: Session = Depends(get_db)):
    return _refresh(token, db)


@router.post("/reset/start")
def reset_start(body: ResetStartReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()

    if not user:
        return {"ok": True}

    rec = (
        db.query(EmailCode)
        .filter(EmailCode.email == email, EmailCode.purpose == "reset")
        .first()
    )

    enforce_code_cooldown(
        rec,
        RESET_RESEND_COOLDOWN_SECONDS,
        "Код уже был отправлен.",
    )

    code = make_code()
    code_hash = sha(code)
    expires_at = calc_expires_at()

    if rec:
        rec.code_hash = code_hash
        rec.expires_at = expires_at
    else:
        rec = EmailCode(
            email=email,
            code_hash=code_hash,
            purpose="reset",
            expires_at=expires_at,
        )

    db.add(rec)
    db.commit()

    send_code_email(email, code, "reset")
    return {"ok": True}


@router.post("/reset/confirm")
def reset_confirm(body: ResetConfirmReq, db: Session = Depends(get_db)):
    email = body.email.lower().strip()
    code = body.code.strip()

    rec = (
        db.query(EmailCode)
        .filter(EmailCode.email == email, EmailCode.purpose == "reset")
        .first()
    )

    if not rec or rec.expires_at < utcnow():
        raise HTTPException(status_code=400, detail="Код просрочен")

    if sha(code) != rec.code_hash:
        raise HTTPException(status_code=400, detail="Неверный код")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    user.password_hash = hash_password(body.new_password)
    db.query(EmailCode).filter(EmailCode.id == rec.id).delete()
    db.commit()

    return {"ok": True}


@router.post("/google", response_model=AuthBundle)
def google_login(body: GoogleAuthReq, db: Session = Depends(get_db)):
    r = requests.get(
        "https://www.googleapis.com/oauth2/v3/userinfo",
        headers={"Authorization": f"Bearer {body.access_token}"},
        timeout=10,
    )
    if r.status_code != 200:
        raise HTTPException(status_code=401, detail="Google token invalid")

    p = r.json()
    email = (p.get("email") or "").lower().strip()
    if not email:
        raise HTTPException(status_code=400, detail="Email не получен от Google")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            name=p.get("name") or p.get("given_name") or "User",
            nick=p.get("given_name") or "User",
            avatar=p.get("picture"),
            provider="google",
            email_verified=True
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.provider = user.provider or "google"
        if not user.email_verified:
            user.email_verified = True
        db.commit()

    access = make_access_token(user.id)
    refresh, exp = make_refresh_token(user.id)
    db.add(RefreshToken(user_id=user.id, token=refresh, expires_at=exp))
    db.commit()

    return {"user": user, "tokens": {"access_token": access, "refresh_token": refresh}}
