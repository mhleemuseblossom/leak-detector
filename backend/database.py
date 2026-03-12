"""
database.py - SQLite async database module
"""
import aiosqlite
import json
from datetime import datetime
from pathlib import Path

# 현재 파일 기준 절대 경로
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "data" / "leak_detector.db"


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                keyword TEXT NOT NULL,
                created_at TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS crawled_pages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                source_keyword TEXT,
                title TEXT,
                raw_text TEXT,
                links_found INTEGER DEFAULT 0,
                depth INTEGER DEFAULT 0,
                crawled_at TEXT NOT NULL,
                session_id TEXT NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leak_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id INTEGER,
                url TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                risk_score REAL DEFAULT 0,
                leak_types TEXT,
                summary TEXT,
                detected_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                FOREIGN KEY(page_id) REFERENCES crawled_pages(id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                topic TEXT,
                status TEXT DEFAULT 'running',
                started_at TEXT NOT NULL,
                finished_at TEXT,
                total_keywords INTEGER DEFAULT 0,
                total_pages INTEGER DEFAULT 0,
                total_leaks INTEGER DEFAULT 0
            )
        """)
        await db.commit()


async def create_session(session_id: str, topic: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO sessions (id, topic, status, started_at) VALUES (?, ?, 'running', ?)",
            (session_id, topic, datetime.now().isoformat())
        )
        await db.commit()


async def save_keywords(session_id: str, keywords: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now().isoformat()
        for kw in keywords:
            await db.execute(
                "INSERT INTO keywords (keyword, created_at, session_id) VALUES (?, ?, ?)",
                (kw, now, session_id)
            )
        await db.execute(
            "UPDATE sessions SET total_keywords=? WHERE id=?",
            (len(keywords), session_id)
        )
        await db.commit()


async def save_page(session_id: str, url: str, keyword: str, title: str, text: str, links: int, depth: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            """INSERT INTO crawled_pages (url, source_keyword, title, raw_text, links_found, depth, crawled_at, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (url, keyword, title, text, links, depth, datetime.now().isoformat(), session_id)
        )
        page_id = cursor.lastrowid
        await db.execute(
            "UPDATE sessions SET total_pages = total_pages + 1 WHERE id=?",
            (session_id,)
        )
        await db.commit()
        return page_id


async def save_leak_result(session_id: str, page_id: int, url: str, risk_level: str, risk_score: float, leak_types: list, summary: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO leak_results (page_id, url, risk_level, risk_score, leak_types, summary, detected_at, session_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (page_id, url, risk_level, risk_score, json.dumps(leak_types, ensure_ascii=False), summary, datetime.now().isoformat(), session_id)
        )
        await db.execute(
            "UPDATE sessions SET total_leaks = total_leaks + 1 WHERE id=?",
            (session_id,)
        )
        await db.commit()


async def finish_session(session_id: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE sessions SET status='finished', finished_at=? WHERE id=?",
            (datetime.now().isoformat(), session_id)
        )
        await db.commit()


async def get_session_results(session_id: str) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute("SELECT * FROM sessions WHERE id=?", (session_id,))
        session = await cursor.fetchone()

        cursor = await db.execute(
            "SELECT keyword FROM keywords WHERE session_id=?", (session_id,)
        )
        keywords = [r[0] for r in await cursor.fetchall()]

        cursor = await db.execute(
            """SELECT lr.*, cp.title FROM leak_results lr
               JOIN crawled_pages cp ON lr.page_id = cp.id
               WHERE lr.session_id=? ORDER BY lr.risk_score DESC""",
            (session_id,)
        )
        leaks = [dict(r) for r in await cursor.fetchall()]

        cursor = await db.execute(
            "SELECT url, title, source_keyword, depth, links_found, crawled_at FROM crawled_pages WHERE session_id=? ORDER BY crawled_at DESC LIMIT 50",
            (session_id,)
        )
        pages = [dict(r) for r in await cursor.fetchall()]

        return {
            "session": dict(session) if session else {},
            "keywords": keywords,
            "leaks": leaks,
            "pages": pages
        }


async def get_all_sessions() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM sessions ORDER BY started_at DESC LIMIT 20"
        )
        return [dict(r) for r in await cursor.fetchall()]
