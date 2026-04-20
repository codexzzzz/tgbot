import aiosqlite
import os
from datetime import date

DB_PATH = os.path.join(os.path.dirname(__file__), "bot.db")

PRESET_FORUMS = [
    ("Black Russia", "https://forum.blackrussia.online"),
    ("Матрёшка РП", "https://matreshkarp.ru/forum"),
    ("Amazing RP", "https://amazingrp.ru/forum"),
    ("MTA Провинция", "https://mtaprovince.ru/forum"),
    ("GTA 5 RP", "https://gta5rp.com/forum"),
    ("Majestic RP", "https://majestic-rp.ru/forum"),
    ("Arizona RP", "https://arizona-rp.com/forum"),
    ("Grand Mobile", "https://grandmobile.ru/forum"),
]


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                is_premium INTEGER DEFAULT 0,
                is_banned INTEGER DEFAULT 0,
                photos_today INTEGER DEFAULT 0,
                last_reset_date TEXT DEFAULT '',
                last_review_date TEXT DEFAULT '',
                last_suggestion_date TEXT DEFAULT ''
            )
        """)
        for col in ("last_review_date", "last_suggestion_date"):
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} TEXT DEFAULT ''")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS photos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                url TEXT,
                delete_url TEXT,
                uploaded_at TEXT DEFAULT (datetime('now')),
                expires_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS forums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                added_by INTEGER,
                added_by_username TEXT,
                is_preset INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                first_name TEXT,
                text TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

        async with db.execute("SELECT COUNT(*) FROM forums WHERE is_preset = 1") as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                for title, url in PRESET_FORUMS:
                    await db.execute(
                        "INSERT INTO forums (title, url, is_preset) VALUES (?, ?, 1)",
                        (title, url)
                    )
        await db.commit()


async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def upsert_user(user_id: int, username: str, first_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name
        """, (user_id, username or "", first_name or ""))
        await db.commit()


async def reset_daily_photos_if_needed(user_id: int):
    today = str(date.today())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT last_reset_date FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
        if row and row[0] != today:
            await db.execute(
                "UPDATE users SET photos_today = 0, last_reset_date = ? WHERE user_id = ?",
                (today, user_id)
            )
            await db.commit()


async def increment_photo_count(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET photos_today = photos_today + 1 WHERE user_id = ?", (user_id,))
        await db.commit()


async def get_photo_count_today(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT photos_today FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def save_photo(user_id: int, username: str, url: str, delete_url: str, expires_at: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO photos (user_id, username, url, delete_url, expires_at)
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, username or "", url, delete_url, expires_at))
        await db.commit()


async def get_last_photos(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM photos ORDER BY id DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_top_users(limit: int = 100):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT u.user_id, u.username, u.first_name, u.is_premium, COUNT(p.id) as photo_count
            FROM users u
            LEFT JOIN photos p ON u.user_id = p.user_id
            GROUP BY u.user_id
            ORDER BY photo_count DESC
            LIMIT ?
        """, (limit,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def ban_user(username: str) -> bool:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET is_banned = 1 WHERE username = ?", (username,))
        await db.commit()
        return cursor.rowcount > 0


async def unban_user(username: str) -> bool:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET is_banned = 0 WHERE username = ?", (username,))
        await db.commit()
        return cursor.rowcount > 0


async def grant_premium(username: str) -> bool:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET is_premium = 1 WHERE username = ?", (username,))
        await db.commit()
        return cursor.rowcount > 0


async def revoke_premium(username: str) -> bool:
    username = username.lstrip("@")
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("UPDATE users SET is_premium = 0 WHERE username = ?", (username,))
        await db.commit()
        return cursor.rowcount > 0


async def is_user_banned(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0])


async def is_user_premium(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT is_premium FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return bool(row and row[0])


async def get_all_forums():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM forums ORDER BY is_preset DESC, id ASC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def add_forum(title: str, url: str, user_id: int, username: str) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO forums (title, url, added_by, added_by_username, is_preset) VALUES (?, ?, ?, ?, 0)",
            (title, url, user_id, username or "")
        )
        await db.commit()
        return cursor.lastrowid


async def delete_forum(forum_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("DELETE FROM forums WHERE id = ? AND is_preset = 0", (forum_id,))
        await db.commit()
        return cursor.rowcount > 0


async def get_user_photos(user_id: int, limit: int = 5, offset: int = 0):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM photos WHERE user_id = ? ORDER BY id DESC LIMIT ? OFFSET ?",
            (user_id, limit, offset)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_user_photo_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM photos WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def delete_user_photo(photo_id: int, user_id: int):
    """Returns delete_url if found, else None. Deletes from DB."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT delete_url FROM photos WHERE id = ? AND user_id = ?", (photo_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        delete_url = row[0]
        await db.execute("DELETE FROM photos WHERE id = ? AND user_id = ?", (photo_id, user_id))
        await db.commit()
        return delete_url


async def can_submit_today(user_id: int, kind: str) -> bool:
    """kind: 'review' or 'suggestion'"""
    col = "last_review_date" if kind == "review" else "last_suggestion_date"
    today = str(date.today())
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(f"SELECT {col} FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return True
            return row[0] != today


async def mark_submitted_today(user_id: int, kind: str):
    col = "last_review_date" if kind == "review" else "last_suggestion_date"
    today = str(date.today())
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {col} = ? WHERE user_id = ?", (today, user_id))
        await db.commit()


async def save_feedback(kind: str, user_id: int, username: str, first_name: str, text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO feedback (kind, user_id, username, first_name, text) VALUES (?, ?, ?, ?, ?)",
            (kind, user_id, username or "", first_name or "", text)
        )
        await db.commit()


async def get_feedback(kind: str, limit: int = 50):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM feedback WHERE kind = ? ORDER BY id DESC LIMIT ?",
            (kind, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def get_user_last_feedback(user_id: int, kind: str):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM feedback WHERE user_id = ? AND kind = ? ORDER BY id DESC LIMIT 1",
            (user_id, kind)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None
