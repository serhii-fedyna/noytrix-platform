# trader_app.py
import os, time, math, sqlite3, asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Body, Depends, Header, Query
from fastapi.middleware.cors import CORSMiddleware
import httpx
import ccxt

APP_SECRET = os.getenv("APP_SECRET", "dev-secret")   # простой Bearer токен для клиента
BINANCE_KEY = os.getenv("BINANCE_API_KEY", "")
BINANCE_SEC = os.getenv("BINANCE_API_SECRET", "")

# ----- ccxt binance futures -----
binance = ccxt.binance({
    "apiKey": BINANCE_KEY,
    "secret": BINANCE_SEC,
    "enableRateLimit": True,
    "options": {"defaultType": "future"}
})

app = FastAPI(title="Noytrix Trader")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

DB_PATH = os.path.join(os.path.dirname(__file__), "trader.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS positions(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  pair TEXT NOT NULL,
  side TEXT NOT NULL,        -- LONG/SHORT
  leverage INTEGER NOT NULL,
  margin_usd REAL NOT NULL,
  qty REAL NOT NULL,
  entry REAL NOT NULL,
  stop REAL,
  take REAL,
  opened_at INTEGER NOT NULL,
  closed_at INTEGER,
  exit_price REAL,
  pnl_usd REAL,
  pnl_pct REAL,
  last_advice_at INTEGER DEFAULT 0
);
""")
conn.commit()

FUTURES_PAIRS = [
  "BTC/USDT","ETH/USDT","SOL/USDT","BNB/USDT","XRP/USDT",
  "ADA/USDT","DOGE/USDT","LINK/USDT","AVAX/USDT","MATIC/USDT",
  "SHIB/USDT","DOT/USDT","OP/USDT","TON/USDT","ARB/USDT",
  "SEI/USDT","SUI/USDT","LTC/USDT","BCH/USDT","INJ/USDT",
]
COMMENT_PERIOD_MS = 180000  # 3 минуты

# --------- auth (простой bearer) ----------
def auth(authorization: Optional[str] = Header(None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Auth required")
    token = authorization.split(" ",1)[1].strip()
    if token != APP_SECRET:
        raise HTTPException(401, "Invalid token")
    # в демо user_id = "u1"
    return "u1"

# --------- utils ----------
def to_symbol(pair: str) -> str:
    return pair.replace("/", "").upper()

async def price_binance(symbol: str) -> float:
    url = "https://api.binance.com/api/v3/ticker/price"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, params={"symbol": symbol})
        r.raise_for_status()
        return float(r.json()["price"])

async def ticker24h(symbol: str) -> Dict[str, Any]:
    url = "https://api.binance.com/api/v3/ticker/24hr"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, params={"symbol": symbol})
        r.raise_for_status()
        return r.json()

async def klines(symbol: str, interval="1m", limit=60) -> List[List[Any]]:
    url = "https://api.binance.com/api/v3/klines"
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url, params={"symbol":symbol,"interval":interval,"limit":limit})
        r.raise_for_status()
        return r.json()

def rsi14(closes: List[float]) -> Optional[float]:
    n = len(closes)
    p = 14
    if n < p+1: return None
    gains, losses = [], []
    for i in range(1,n):
        ch = closes[i] - closes[i-1]
        gains.append(max(ch,0.0)); losses.append(max(-ch,0.0))
    avg_gain = sum(gains[:p])/p; avg_loss = sum(losses[:p])/p
    for i in range(p, len(gains)):
        avg_gain = (avg_gain*(p-1) + gains[i]) / p
        avg_loss = (avg_loss*(p-1) + losses[i]) / p
    if avg_loss == 0: return 100.0
    rs = avg_gain/avg_loss
    return 100 - (100/(1+rs))

def rule_comment(side:str, entry:float, current:float, stop:float, take:float,
                 leverage:int, margin:float, quality:float,
                 last_advice_at:int, rsi:Optional[float]) -> str:
    sign = 1 if side=="LONG" else -1
    risk = max(1e-9, (entry - stop)*sign)
    reward = max(1e-9, (take - entry)*sign)
    rr = reward / risk
    move = (current - entry)*sign
    dist_stop = (current - stop)*sign
    dist_take = (take - current)*sign
    near_stop = dist_stop <= 0 or dist_stop/abs(entry) < 0.005
    near_take = dist_take <= 0 or dist_take/abs(entry) < 0.005
    parts = []
    if near_take: parts.append("Цена возле цели — зафиксируй 25–50% и подтяни стоп.")
    elif near_stop: parts.append("Цена у стопа — не добавляй объём, держи дисциплину.")
    else:
        if move>0: parts.append("Импульс в нашу сторону — держим.")
        else: parts.append("Пока против нас — без паники, ждём реакцию уровня.")
    if rr>=1.8 and quality>=6: parts.append("R/R ок, сигнал рабочий.")
    elif rr<1.2: parts.append("Слабый R/R — будь осторожнее с объёмом.")
    if rsi is not None:
        if (side=="LONG" and rsi>=75) or (side=="SHORT" and rsi<=25):
            parts.append("RSI перегрет — частичная фиксация уместна.")
        elif (side=="LONG" and rsi<=35) or (side=="SHORT" and rsi>=65):
            parts.append("RSI поддерживает сценарий.")
    return " ".join(parts)

def pnl(entry:float, current:float, side:str, leverage:int, margin:float) -> Dict[str,float]:
    notional = margin * leverage
    ret = (current/entry - 1.0) if side=="LONG" else (entry/current - 1.0)
    return {"pnlUsd": notional*ret, "pnlPct": ret*100.0}

# --------- endpoints ----------
@app.get("/health")
def health(): return {"ok": True}

@app.get("/pairs")
def pairs(): return {"items": FUTURES_PAIRS}

@app.get("/price")
async def get_price(symbol:str = Query(...)): 
    return {"price": await price_binance(symbol)}

@app.post("/signal")
async def signal(body: Dict[str,Any] = Body(...), user_id: str = Depends(auth)):
    pair = body.get("pair","BTC/USDT")
    sym = to_symbol(pair)
    t = await ticker24h(sym)
    last = float(t["lastPrice"]); open_ = float(t["openPrice"])
    spread = abs(last - open_)
    direction = "LONG" if last>=open_ else "SHORT"
    leverage = 5 if pair.startswith(("BTC","ETH")) else 10
    stop = round(last*(0.96 if direction=="LONG" else 1.04), 4)
    take = round(last*(1.03 if direction=="LONG" else 0.97), 4)
    quality = max(0.0, min(10.0, (spread/last)*120))
    return {
        "pair": pair, "price": round(last,4),
        "direction": direction, "leverage": leverage,
        "stop": stop, "take": take, "quality": quality
    }

@app.post("/position/open")
async def position_open(body: Dict[str,Any] = Body(...), user_id: str = Depends(auth)):
    """
    body: {pair, direction, leverage, marginUsd, entry, stop, take}
    Создаёт реальный рыночный ордер на Binance Futures и ставит стоп/тейк (STOP_MARKET/TAKE_PROFIT_MARKET).
    """
    if not BINANCE_KEY or not BINANCE_SEC:
        raise HTTPException(400, "Binance API keys not configured on server")
    pair = body["pair"]; direction = body["direction"].upper()
    leverage = int(body["leverage"]); margin = float(body["marginUsd"])
    entry = float(body["entry"]); stop = float(body["stop"]); take = float(body["take"])
    sym = to_symbol(pair)

    # настроить плечо на бирже
    mkt = binance.market(pair)
    try:
        binance.fapiPrivate_post_leverage({"symbol": sym, "leverage": leverage})
    except Exception:
        pass

    # количество (в базовой)
    notional = margin * leverage
    qty = max(mkt.get("limits",{}).get("amount",{}).get("min", 0.001),
              round(notional/entry, mkt.get("precision",{}).get("amount", 3)))

    side_ccxt = "buy" if direction=="LONG" else "sell"
    # рыночный вход
    try:
        order = binance.create_order(symbol=pair, type="market", side=side_ccxt, amount=qty)
        fill_price = float(order.get("price") or entry)
    except Exception as e:
        raise HTTPException(502, f"Create market order failed: {e}")

    # стоп/тейк (защита): стоп-маркет и тейк-профит-маркет
    try:
        # стоп
        binance.fapiPrivate_post_order({
            "symbol": sym, "side": "SELL" if direction=="LONG" else "BUY",
            "type": "STOP_MARKET",
            "stopPrice": f"{stop}",
            "closePosition": True,  # close all
            "timeInForce": "GTC",
            "workingType": "MARK_PRICE"
        })
        # тейк
        binance.fapiPrivate_post_order({
            "symbol": sym, "side": "SELL" if direction=="LONG" else "BUY",
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": f"{take}",
            "closePosition": True,
            "timeInForce": "GTC",
            "workingType": "MARK_PRICE"
        })
    except Exception:
        # не критично для демо; пользователь может закрыть вручную
        pass

    now = int(time.time()*1000)
    cur.execute("""INSERT INTO positions
      (user_id,pair,side,leverage,margin_usd,qty,entry,stop,take,opened_at,last_advice_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
      (user_id, pair, direction, leverage, margin, qty, fill_price, stop, take, now, 0))
    conn.commit()
    pid = cur.lastrowid
    return {"ok": True, "position_id": pid, "entry": fill_price, "qty": qty}

@app.post("/position/close")
async def position_close(body: Dict[str,Any] = Body(...), user_id: str = Depends(auth)):
    pid = int(body["position_id"])
    row = cur.execute("SELECT id,pair,side,leverage,margin_usd,qty,entry FROM positions WHERE id=? AND user_id=? AND closed_at IS NULL",
                      (pid, user_id)).fetchone()
    if not row: raise HTTPException(404, "Position not found or closed")
    _, pair, side, lev, margin, qty, entry = row
    sym = to_symbol(pair)
    # отменим защитные и закроем рыночным
    try:
        binance.fapiPrivate_delete_allopenorders({"symbol": sym})
    except Exception:
        pass
    side_close = "sell" if side=="LONG" else "buy"
    try:
        order = binance.create_order(symbol=pair, type="market", side=side_close, amount=qty)
        exit_price = float(order.get("price") or await price_binance(sym))
    except Exception as e:
        raise HTTPException(502, f"Close order failed: {e}")
    stats = pnl(entry, exit_price, side, int(lev), float(margin))
    now = int(time.time()*1000)
    cur.execute("""UPDATE positions SET closed_at=?, exit_price=?, pnl_usd=?, pnl_pct=? WHERE id=?""",
                (now, exit_price, stats["pnlUsd"], stats["pnlPct"], pid))
    conn.commit()
    return {"ok": True, "exit": exit_price, **stats}

@app.get("/position/status")
async def position_status(position_id:int, user_id: str = Depends(auth)):
    row = cur.execute("""SELECT id,pair,side,leverage,margin_usd,qty,entry,stop,take,opened_at,last_advice_at
                         FROM positions WHERE id=? AND user_id=?""",(position_id,user_id)).fetchone()
    if not row: raise HTTPException(404,"Position not found")
    pid,pair,side,lev,margin,qty,entry,stop,take,opened_at,last_advice_at = row
    sym = to_symbol(pair)
    price = await price_binance(sym)
    stats = pnl(entry, price, side, int(lev), float(margin))

    # rsi для комментария
    try:
        k = await klines(sym, "1m", 60)
        closes = [float(c[4]) for c in k]
        rsi = rsi14(closes)
    except Exception:
        rsi = None

    now = int(time.time()*1000)
    adv = None
    if (now - (last_advice_at or 0)) >= COMMENT_PERIOD_MS:
        # качество — простая оценка по волатильности
        quality = min(10.0, max(0.0, abs(price-entry)/entry*120))
        adv = rule_comment(side, entry, price, stop, take, lev, margin, quality, last_advice_at or 0, rsi)
        cur.execute("UPDATE positions SET last_advice_at=? WHERE id=?", (now, pid))
        conn.commit()

    return {
        "price": price, **stats,
        "advice": adv, "rsi": None if rsi is None else round(rsi,1),
        "position": {
            "id": pid, "pair": pair, "side": side, "leverage": lev, "margin_usd": margin,
            "qty": qty, "entry": entry, "stop": stop, "take": take, "opened_at": opened_at
        }
    }
