# auth/security.py
import bcrypt, jwt, os
from datetime import datetime, timedelta

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret_change_me")
ACCESS_TTL_MIN = int(os.getenv("ACCESS_TTL_MIN", "30"))
REFRESH_TTL_DAYS = int(os.getenv("REFRESH_TTL_DAYS", "30"))

def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode(), hashed.encode())
    except Exception:
        return False

def make_access_token(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TTL_MIN)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def make_refresh_token(user_id: int) -> tuple[str, datetime]:
    exp = datetime.utcnow() + timedelta(days=REFRESH_TTL_DAYS)
    payload = {"sub": str(user_id), "exp": exp, "type": "refresh"}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256"), exp
