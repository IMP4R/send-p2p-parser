import sqlite3
import secrets
import time
import json
from contextlib import contextmanager
from config import DB_PATH


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                username TEXT,
                label TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at REAL,
                last_used REAL
            );
            CREATE TABLE IF NOT EXISTS token_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                reason TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                admin_note TEXT DEFAULT '',
                token_id INTEGER,
                created_at REAL,
                resolved_at REAL
            );
            CREATE TABLE IF NOT EXISTS cookie_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL,
                phone TEXT NOT NULL,
                cookies TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL,
                updated_at REAL
            );
        """)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ═══ TOKENS ═══

def generate_token() -> str:
    return f"stg_{secrets.token_urlsafe(32)}"


def create_token(user_id: int, username: str = "", label: str = "") -> dict:
    token = generate_token()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO tokens (token, user_id, username, label, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (token, user_id, username, label, time.time())
        )
        row = conn.execute(
            "SELECT * FROM tokens WHERE token = ?", (token,)
        ).fetchone()
    return dict(row)


def validate_token(token: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM tokens WHERE token = ? AND is_active = 1",
            (token,)
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE tokens SET last_used = ? WHERE id = ?",
                (time.time(), row["id"])
            )
            return dict(row)
    return None


def get_all_tokens() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM tokens ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def toggle_token(token_id: int, active: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE tokens SET is_active = ? WHERE id = ?",
            (1 if active else 0, token_id)
        )


def delete_token(token_id: int):
    with get_db() as conn:
        conn.execute("DELETE FROM tokens WHERE id = ?", (token_id,))


# ═══ TOKEN REQUESTS ═══

def create_request(user_id: int, username: str, reason: str) -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT INTO token_requests (user_id, username, reason, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, username, reason, time.time())
        )
        row = conn.execute(
            "SELECT * FROM token_requests WHERE user_id = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
    return dict(row)


def get_pending_requests() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM token_requests WHERE status = 'pending' "
            "ORDER BY created_at"
        ).fetchall()
    return [dict(r) for r in rows]


def approve_request(request_id: int, admin_note: str = "") -> dict:
    with get_db() as conn:
        req = conn.execute(
            "SELECT * FROM token_requests WHERE id = ?", (request_id,)
        ).fetchone()
        if not req:
            return None

        token_data = create_token(
            req["user_id"], req["username"], f"request #{request_id}"
        )

        conn.execute(
            "UPDATE token_requests SET status='approved', admin_note=?, "
            "token_id=?, resolved_at=? WHERE id=?",
            (admin_note, token_data["id"], time.time(), request_id)
        )
    return token_data


def reject_request(request_id: int, admin_note: str = ""):
    with get_db() as conn:
        conn.execute(
            "UPDATE token_requests SET status='rejected', admin_note=?, "
            "resolved_at=? WHERE id=?",
            (admin_note, time.time(), request_id)
        )


# ═══ COOKIE SESSIONS ═══

def save_cookie_session(token: str, phone: str, cookies: list, status: str):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM cookie_sessions WHERE token = ? AND phone = ?",
            (token, phone)
        ).fetchone()

        now = time.time()
        if existing:
            conn.execute(
                "UPDATE cookie_sessions SET cookies=?, status=?, updated_at=? "
                "WHERE id=?",
                (json.dumps(cookies), status, now, existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO cookie_sessions "
                "(token, phone, cookies, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (token, phone, json.dumps(cookies), status, now, now)
            )


def get_cookie_session(token: str, phone: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM cookie_sessions WHERE token = ? AND phone = ? "
            "ORDER BY updated_at DESC LIMIT 1",
            (token, phone)
        ).fetchone()
    return dict(row) if row else None
