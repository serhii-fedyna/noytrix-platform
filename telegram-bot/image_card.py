from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import textwrap

W, H = 1080, 820

BG = "#06080f"
PANEL = "#101826"
PANEL2 = "#151f35"
TEXT = "#f3f6ff"
SUB = "#a8b4cf"
ACCENT = "#ffb020"
GREEN = "#22c55e"
ORANGE = "#f59e0b"
RED = "#ef4444"
BORDER = "#263452"

OUT = Path("data/cards")
OUT.mkdir(parents=True, exist_ok=True)


def font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


TITLE = font("DejaVuSans-Bold.ttf", 46)
BIG = font("DejaVuSans-Bold.ttf", 58)
HEAD = font("DejaVuSans-Bold.ttf", 32)
BODY = font("DejaVuSans.ttf", 27)
SMALL = font("DejaVuSans.ttf", 24)


def level_color(level: str):
    x = (level or "").lower()
    if x in {"danger", "critical"}:
        return RED
    if x == "suspicious":
        return ORANGE
    return GREEN


def wrap(text, width=42, limit=180):
    text = str(text or "").strip()
    if len(text) > limit:
        text = text[:limit - 3] + "..."
    return "\n".join(textwrap.wrap(text, width=width))


def block(draw, x, y, w, h, title, body):
    draw.rounded_rectangle((x, y, x+w, y+h), radius=24, fill=PANEL2, outline=BORDER, width=2)
    draw.text((x+24, y+20), title, fill=TEXT, font=HEAD)
    draw.multiline_text((x+24, y+66), wrap(body, 38, 150), fill=SUB, font=SMALL, spacing=6)


def card_text(lang: str, key: str) -> str:
    d = {
        'en': {
            'risk_card': 'SCAMSHIELD RISK CARD',
            'risk_score': 'Risk Score',
            'type': 'Type',
            'ai': 'AI Analysis',
            'worst': 'Worst Case',
            'details': 'Full source details are available in the Telegram result below.',
            'default_what': 'Noytrix did not find confirmed scam signals in available sources.',
            'default_worst': 'Risk appears only if the site asks for a seed phrase, private key, wallet approval or suspicious signature.',
        },
        'ru': {
            'risk_card': 'SCAMSHIELD КАРТА РИСКА',
            'risk_score': 'Оценка риска',
            'type': 'Тип',
            'ai': 'AI-анализ',
            'worst': 'Худший сценарий',
            'details': 'Полные детали источников доступны ниже в Telegram.',
            'default_what': 'Noytrix не нашёл подтверждённых scam-сигналов в доступных источниках.',
            'default_worst': 'Риск появляется, если сайт просит seed-фразу, приватный ключ, разрешение кошелька или подозрительную подпись.',
        },
        'uk': {
            'risk_card': 'SCAMSHIELD КАРТА РИЗИКУ',
            'risk_score': 'Оцінка ризику',
            'type': 'Тип',
            'ai': 'AI-аналіз',
            'worst': 'Найгірший сценарій',
            'details': 'Повні деталі джерел доступні нижче в Telegram.',
            'default_what': 'Noytrix не знайшов підтверджених scam-сигналів у доступних джерелах.',
            'default_worst': 'Ризик з’являється, якщо сайт просить seed-фразу, приватний ключ, дозвіл гаманця або підозрілий підпис.',
        },
    }
    return d.get(lang, d['en']).get(key, key)


def localize_card_text(lang: str, text: str) -> str:
    text = str(text or '')
    low = text.lower()
    if lang == 'ru':
        if 'trusted-brand impersonation' in low:
            return 'Домен похож на подделку известного бренда. Его цель — заставить вас доверять фейковой странице.'
        if 'entering data, connecting a wallet' in low:
            return 'В худшем сценарии ввод данных, подключение кошелька или подпись могут привести к потере доступа или средств.'
    if lang == 'uk':
        if 'trusted-brand impersonation' in low:
            return 'Домен схожий на підробку відомого бренду. Його мета — змусити вас довіряти фейковій сторінці.'
        if 'entering data, connecting a wallet' in low:
            return 'У найгіршому випадку введення даних, підключення гаманця або підпис можуть призвести до втрати доступу чи коштів.'
    return text


def generate_card(data: dict, filename: str, lang: str = 'en'):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    level = str(data.get("level") or "")
    verdict = str(data.get("verdict_localized") or data.get("ai_verdict_localized") or "Verdict")
    score = int(data.get("score") or 0)
    kind = str(data.get("kind_localized") or data.get("kind") or "")
    target = str(data.get("host") or data.get("normalized_input") or data.get("input") or "")

    accent = level_color(level)

    what = localize_card_text(lang, data.get("what_can_happen")) if data.get("what_can_happen") else card_text(lang, "default_what")
    worst = localize_card_text(lang, data.get("worst_case")) if data.get("worst_case") else card_text(lang, "default_worst")

    draw.rounded_rectangle((36, 36, W-36, H-36), radius=36, fill=PANEL, outline=BORDER, width=2)

    draw.text((76, 72), "NOYTRIX", fill=ACCENT, font=TITLE)
    draw.text((76, 124), card_text(lang, "risk_card"), fill=TEXT, font=HEAD)

    draw.rounded_rectangle((76, 190, W-76, 320), radius=28, fill="#0b1020", outline=accent, width=3)
    draw.ellipse((108, 230, 156, 278), fill=accent)
    draw.text((184, 214), verdict.upper(), fill=TEXT, font=BIG)
    draw.text((184, 278), f"{card_text(lang, 'risk_score')} {score}/100", fill=SUB, font=BODY)

    draw.text((76, 350), f"{card_text(lang, 'type')}: {kind}", fill=SUB, font=BODY)
    draw.text((76, 390), target[:54], fill=ACCENT, font=HEAD)

    block(draw, 76, 460, 440, 190, card_text(lang, "ai"), what)
    block(draw, 564, 460, 440, 190, card_text(lang, "worst"), worst)

    draw.rounded_rectangle((76, 690, W-76, 745), radius=18, fill="#0b1020", outline=BORDER, width=1)
    draw.text((100, 704), card_text(lang, "details"), fill=SUB, font=SMALL)

    path = OUT / filename
    img.save(path, quality=95)
    return str(path)
