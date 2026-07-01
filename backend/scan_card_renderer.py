from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import textwrap

W, H = 1080, 1080

BG = "#06080f"
PANEL = "#101826"
PANEL2 = "#151f35"
TEXT = "#e9ecff"
DIM = "#A8B4CF"
ACCENT = "#ffb020"
GREEN = "#29d37a"
WARN = "#FFB547"
BAD = "#FF6B6B"
BORDER = "#27344f"


def font(name, size):
    try:
        return ImageFont.truetype(name, size)
    except Exception:
        return ImageFont.load_default()


TITLE = font("DejaVuSans-Bold.ttf", 54)
HEAD = font("DejaVuSans-Bold.ttf", 34)
BIG = font("DejaVuSans-Bold.ttf", 62)
BODY = font("DejaVuSans.ttf", 28)
SMALL = font("DejaVuSans.ttf", 24)


def color(level):
    level = str(level or "").lower()
    if level in ("critical", "danger"):
        return BAD
    if level == "suspicious":
        return WARN
    return GREEN


def wrap(text, width=38, limit=160):
    text = str(text or "").strip()
    if len(text) > limit:
        text = text[: limit - 3] + "..."
    return "\n".join(textwrap.wrap(text, width=width))



def fit_lines(text, font_obj, max_width, max_lines):
    words = str(text or "").replace("\n", " ").split()
    lines = []
    current = ""

    def width(x):
        try:
            return font_obj.getbbox(x)[2] - font_obj.getbbox(x)[0]
        except Exception:
            return len(x) * 10

    for word in words:
        test = (current + " " + word).strip()
        if width(test) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if words and len(" ".join(lines).split()) < len(words) and lines:
        last = lines[-1]
        while width(last + "...") > max_width and len(last) > 3:
            last = last[:-1]
        lines[-1] = last.rstrip() + "..."

    return lines

def draw_block(draw, x, y, w, h, title, body):
    draw.rounded_rectangle((x, y, x+w, y+h), radius=26, fill=PANEL2, outline=BORDER, width=2)
    draw.text((x+24, y+20), title, fill=TEXT, font=HEAD)

    max_width = w - 48
    max_lines = max(1, int((h - 72) / 31))
    lines = fit_lines(body, SMALL, max_width, max_lines)

    yy = y + 68
    for line in lines:
        draw.text((x+24, yy), line, fill=DIM, font=SMALL)
        yy += 31



def card_t(lang: str, key: str) -> str:
    d = {
        "en": {
            "risk_card": "SCAMSHIELD RISK CARD",
            "risk_score": "Risk Score",
            "type": "Type",
            "object": "Object",
            "ai": "AI Analysis",
            "worst": "Worst Case",
            "details": "FULL DETAILS IN TELEGRAM",
            "powered": "Powered by Noytrix Risk Engine",
            "default_what": "Noytrix analyzed this target through the ScamShield Risk Engine.",
            "default_worst": "Risk depends on your next action: connect wallet, sign, or enter sensitive data.",
        },
        "ru": {
            "risk_card": "SCAMSHIELD КАРТА РИСКА",
            "risk_score": "Оценка риска",
            "type": "Тип",
            "object": "Объект",
            "ai": "AI-анализ",
            "worst": "Худший сценарий",
            "details": "ПОЛНЫЕ ДЕТАЛИ В TELEGRAM",
            "powered": "Работает на Noytrix Risk Engine",
            "default_what": "Noytrix проанализировал объект через ScamShield Risk Engine.",
            "default_worst": "Риск зависит от вашего следующего действия: подключение кошелька, подпись или ввод важных данных.",
        },
        "uk": {
            "risk_card": "SCAMSHIELD КАРТА РИЗИКУ",
            "risk_score": "Оцінка ризику",
            "type": "Тип",
            "object": "Об’єкт",
            "ai": "AI-аналіз",
            "worst": "Найгірший сценарій",
            "details": "ПОВНІ ДЕТАЛІ В TELEGRAM",
            "powered": "Працює на Noytrix Risk Engine",
            "default_what": "Noytrix проаналізував об’єкт через ScamShield Risk Engine.",
            "default_worst": "Ризик залежить від вашої наступної дії: підключення гаманця, підпис або введення важливих даних.",
        },
    }
    return d.get(lang, d["en"]).get(key, key)


def localize_card_body(lang: str, text: str) -> str:
    text = str(text or "")
    low = text.lower()

    if lang == "ru":
        if "trusted-brand impersonation" in low:
            return "Домен похож на подделку известного бренда. Его цель — заставить вас доверять фейковой странице."
        if "entering data, connecting a wallet" in low:
            return "В худшем сценарии ввод данных, подключение кошелька или подпись могут привести к потере доступа или средств."
        if "seed phrase" in low or "private key" in low:
            return "Риск появляется, если сайт просит seed-фразу, приватный ключ, разрешение кошелька или подозрительную подпись."

    if lang == "uk":
        if "trusted-brand impersonation" in low:
            return "Домен схожий на підробку відомого бренду. Його мета — змусити вас довіряти фейковій сторінці."
        if "entering data, connecting a wallet" in low:
            return "У найгіршому випадку введення даних, підключення гаманця або підпис можуть призвести до втрати доступу чи коштів."
        if "seed phrase" in low or "private key" in low:
            return "Ризик з’являється, якщо сайт просить seed-фразу, приватний ключ, дозвіл гаманця або підозрілий підпис."

    return text


def render_scan_card(scan: dict) -> bytes:
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    for y in range(H):
        r = 6
        g = 8 + int(y / H * 14)
        b = 15 + int(y / H * 54)
        draw.line((0, y, W, y), fill=(r, g, b))

    level = str(scan.get("level") or "safe")
    lang = str(scan.get("lang") or "en").lower()
    verdict = str(scan.get("verdict_localized") or scan.get("ai_verdict_localized") or level).upper()
    score = int(scan.get("score") or 0)
    kind = str(scan.get("kind_localized") or scan.get("kind") or card_t(lang, "object"))
    target = str(scan.get("host") or scan.get("normalized_input") or scan.get("input") or "")

    c = color(level)

    draw.rounded_rectangle((46, 46, W-46, H-46), radius=42, fill=PANEL, outline=BORDER, width=2)

    draw.text((86, 86), "NOYTRIX", fill=ACCENT, font=TITLE)
    draw.text((86, 148), card_t(lang, "risk_card"), fill=TEXT, font=HEAD)

    draw.rounded_rectangle((86, 230, W-86, 380), radius=32, fill="#0b1020", outline=c, width=3)
    draw.ellipse((120, 280, 170, 330), fill=c)
    draw.text((200, 258), verdict, fill=TEXT, font=BIG)
    draw.text((200, 326), f"{card_t(lang, 'risk_score')} {score}/100", fill=DIM, font=BODY)

    draw.text((86, 420), f"{card_t(lang, 'type')}: {kind}", fill=DIM, font=BODY)
    draw.text((86, 462), target[:58], fill=ACCENT, font=HEAD)

    what = localize_card_body(lang, scan.get("what_can_happen")) if scan.get("what_can_happen") else card_t(lang, "default_what")
    worst = localize_card_body(lang, scan.get("worst_case")) if scan.get("worst_case") else card_t(lang, "default_worst")

    draw_block(draw, 86, 540, 908, 135, card_t(lang, "ai"), what)

    draw_block(draw, 86, 700, 908, 135, card_t(lang, "worst"), worst)

    draw.rounded_rectangle((86, 880, W-86, 950), radius=22, fill=ACCENT)
    draw.text((W//2 - 250, 896), card_t(lang, "details"), fill="#06080f", font=HEAD)

    draw.text((86, 990), card_t(lang, "powered"), fill=DIM, font=SMALL)

    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
