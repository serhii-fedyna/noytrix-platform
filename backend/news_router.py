# news_router.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx, re, time
from bs4 import BeautifulSoup

router = APIRouter(prefix="/api", tags=["news"])

COINTELEGRAPH_RU = "https://ru.cointelegraph.com"

# кэш в памяти
_cache = {}
TTL = 300  # 5 минут

def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()
    txt = soup.get_text("\n")
    txt = re.sub(r"\[[^\]]*\]\([^)]+\)", "", txt)  # убираем [текст](ссылка)
    txt = re.sub(r"https?://\S+", "", txt)        # убираем голые ссылки
    txt = re.sub(r"\s+\n", "\n", txt)
    txt = re.sub(r"\n{3,}", "\n\n", txt).strip()
    return txt

async def _fetch_list(limit=20):
    url = f"{COINTELEGRAPH_RU}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("a[href^='/news/']")[: limit * 2]
        seen = set()
        items = []
        for a in cards:
            href = a.get("href")
            if not href or href in seen: 
                continue
            seen.add(href)
            title = a.get_text(" ", strip=True)
            img = a.find("img")
            image = img.get("src") if img and img.get("src") else None
            items.append({
                "id": href,
                "title": title,
                "image": image,
                "url": f"{COINTELEGRAPH_RU}{href}",
            })
            if len(items) >= limit: 
                break
        return items

async def _fetch_article(href: str):
    url = f"{COINTELEGRAPH_RU}{href}" if href.startswith("/") else href
    async with httpx.AsyncClient(timeout=12) as client:
        r = await client.get(url)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        article = soup.select_one("article") or soup.select_one("div.post__content")
        html = str(article or soup)
        text = _clean_text(html)
        og = soup.select_one("meta[property='og:image']")
        image = og.get("content") if og else None
        title = soup.select_one("meta[property='og:title']")
        title = title.get("content") if title else (soup.title.string if soup.title else "")
        return {"title": title, "image": image, "text": text}

class ExplainReq(BaseModel):
    title: str
    text: str

@router.get("/news")
async def news_list(limit: int = 20):
    key = ("list", limit)
    now = time.time()
    if key in _cache and now - _cache[key]["t"] < TTL:
        return _cache[key]["v"]
    items = await _fetch_list(limit=limit)
    _cache[key] = {"v": items, "t": now}
    return items

@router.get("/news/item")
async def news_item(href: str):
    key = ("item", href)
    now = time.time()
    if key in _cache and now - _cache[key]["t"] < TTL:
        return _cache[key]["v"]
    data = await _fetch_article(href)
    _cache[key] = {"v": data, "t": now}
    return data

@router.post("/news/explain")
async def news_explain(body: ExplainReq):
    # простое объяснение для примера
    text = body.text.lower()
    if "листинг" in text or "listing" in text:
        return {"explanation": "Новость о листинге. Это обычно поднимает интерес и ликвидность монеты."}
    if "партнерств" in text or "integration" in text:
        return {"explanation": "Новость о партнёрстве. Это позитив для долгосрочного развития."}
    return {"explanation": "Новость о крипторынке. Следи за реакцией цены и ликвидностью."}
