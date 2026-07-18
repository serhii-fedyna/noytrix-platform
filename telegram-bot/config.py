import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
API_BASE = (os.getenv("NOYTRIX_API_BASE") or "http://127.0.0.1:8000").strip().rstrip("/")
APP_KEY = (os.getenv("NOYTRIX_APP_KEY") or "").strip()
APP_URL = (os.getenv("NOYTRIX_APP_URL") or "https://noytrix.com").strip().rstrip("/")
DEFAULT_LANG = (os.getenv("DEFAULT_LANG") or "en").strip().lower()

SUPPORTED_LANGS = {"en", "ru", "uk"}

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing in .env")

if not APP_KEY:
    raise RuntimeError("NOYTRIX_APP_KEY is missing in .env")

if DEFAULT_LANG not in SUPPORTED_LANGS:
    DEFAULT_LANG = "en"

ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "0") or 0)
