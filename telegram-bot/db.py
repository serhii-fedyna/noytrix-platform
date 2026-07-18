import aiosqlite

DB_PATH = "data/bot.sqlite3"

CREATE_USERS = """
CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    lang TEXT DEFAULT 'en',
    is_pro INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_USERS)
        await db.commit()

async def upsert_user(
    telegram_id: int,
    username: str | None,
    first_name: str | None,
):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id)
            DO UPDATE SET
                username=excluded.username,
                first_name=excluded.first_name
            """,
            (
                telegram_id,
                username,
                first_name,
            ),
        )
        await db.commit()

async def set_lang(telegram_id: int, lang: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET lang=? WHERE telegram_id=?",
            (lang, telegram_id),
        )
        await db.commit()

async def get_lang(telegram_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT lang FROM users WHERE telegram_id=?",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()

    if row and row[0]:
        return row[0]

    return "en"

CREATE_SCANS = """
CREATE TABLE IF NOT EXISTS scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    input_text TEXT NOT NULL,
    kind TEXT,
    level TEXT,
    score INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

async def init_scan_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(CREATE_SCANS)
        await db.commit()

async def save_scan(
    telegram_id: int,
    input_text: str,
    kind: str | None,
    level: str | None,
    score: int | None,
) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            """
            INSERT INTO scans (telegram_id, input_text, kind, level, score)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, input_text, kind, level, int(score or 0)),
        )
        await db.commit()
        return int(cur.lastrowid)

async def get_scan(scan_id: int, telegram_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT input_text, kind FROM scans
            WHERE id=? AND telegram_id=?
            """,
            (scan_id, telegram_id),
        ) as cur:
            return await cur.fetchone()
