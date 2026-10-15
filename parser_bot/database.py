import sqlite3
import json
import time
from contextlib import contextmanager
from config import DB_PATH


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                phone TEXT,
                cookies TEXT,
                is_active INTEGER DEFAULT 0,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER UNIQUE NOT NULL,
                is_tracking INTEGER DEFAULT 1,
                last_data TEXT,
                last_status TEXT,
                last_is_visible INTEGER,
                last_price TEXT,
                last_limits_min TEXT,
                last_limits_max TEXT,
                channel_message_id INTEGER,
                is_open INTEGER DEFAULT 0,
                created_at REAL,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS message_template (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                template TEXT,
                button_text TEXT DEFAULT '📋 Открыть оффер',
                button_emoji_id TEXT,
                button_style TEXT,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                offer_id INTEGER NOT NULL,
                price REAL NOT NULL,
                limits_min REAL,
                limits_max REAL,
                period_type TEXT NOT NULL DEFAULT 'day',
                period_start REAL NOT NULL,
                recorded_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS report_template (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                template TEXT,
                send_to_channel INTEGER DEFAULT 0,
                updated_at REAL
            );
            CREATE TABLE IF NOT EXISTS report_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                period_type TEXT NOT NULL,
                period_start REAL NOT NULL,
                period_end REAL NOT NULL,
                order_count INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                avg_price REAL DEFAULT 0,
                sent_at REAL NOT NULL
            );
        """)

        # Дефолтный шаблон сообщений
        existing = conn.execute(
            "SELECT id FROM message_template WHERE id = 1"
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO message_template (id, template, updated_at) "
                "VALUES (1, ?, ?)",
                (
                    "{type_emoji} {type_text} {asset}{fiat_emoji}\n"
                    "💰 Курс: {price}\n\n"
                    "📊 Лимиты: {min} — {max} {fiat}\n\n"
                    "{status_emoji}{status_text}",
                    time.time()
                )
            )

        # Дефолтный шаблон отчёта
        existing_report = conn.execute(
            "SELECT id FROM report_template WHERE id = 1"
        ).fetchone()
        if not existing_report:
            conn.execute(
                "INSERT INTO report_template (id, template, send_to_channel, updated_at) "
                "VALUES (1, ?, 0, ?)",
                (
                    "✉️\n\n"
                    "Статистика за 24ч :\n\n"
                    "⚠️ Кол-во ордеров: <b>{order_count}</b>\n"
                    "⚠️ Сумма средств: <b>{total_volume}</b>\n"
                    "🛍 Средний курс: <b>{avg_price}</b>\n\n"
                    "Увидимся завтра👍",
                    time.time()
                )
            )


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ═══ SETTINGS ═══

def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )


# ═══ ACCOUNT ═══

def get_account() -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM account WHERE id = 1").fetchone()
    return dict(row) if row else None


def save_account(phone: str, cookies: list):
    with get_db() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO account "
            "(id, phone, cookies, is_active, updated_at) "
            "VALUES (1, ?, ?, 1, ?)",
            (phone, json.dumps(cookies), time.time())
        )


def deactivate_account():
    with get_db() as conn:
        conn.execute(
            "UPDATE account SET is_active = 0, updated_at = ? WHERE id = 1",
            (time.time(),)
        )


# ═══ OFFERS ═══

def add_offer(offer_id: int) -> dict:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO offers "
            "(offer_id, is_tracking, created_at, updated_at) "
            "VALUES (?, 1, ?, ?)",
            (offer_id, time.time(), time.time())
        )
        row = conn.execute(
            "SELECT * FROM offers WHERE offer_id = ?", (offer_id,)
        ).fetchone()
    return dict(row)


def remove_offer(offer_id: int):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM offers WHERE offer_id = ?", (offer_id,)
        )


def set_offer_tracking(offer_id: int, tracking: bool):
    with get_db() as conn:
        conn.execute(
            "UPDATE offers SET is_tracking = ?, updated_at = ? "
            "WHERE offer_id = ?",
            (1 if tracking else 0, time.time(), offer_id)
        )


def get_all_offers() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM offers ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_tracking_offers() -> list:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM offers WHERE is_tracking = 1"
        ).fetchall()
    return [dict(r) for r in rows]


def update_offer_state(
    offer_id: int,
    data: dict,
    status: str,
    is_visible: bool,
    price: str,
    limits_min: str,
    limits_max: str,
    is_open: bool,
    message_id: int | None = None
):
    with get_db() as conn:
        updates = {
            "last_data": json.dumps(data),
            "last_status": status,
            "last_is_visible": 1 if is_visible else 0,
            "last_price": price,
            "last_limits_min": limits_min,
            "last_limits_max": limits_max,
            "is_open": 1 if is_open else 0,
            "updated_at": time.time(),
        }
        if message_id is not None:
            updates["channel_message_id"] = message_id

        sets = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values())
        vals.append(offer_id)

        conn.execute(
            f"UPDATE offers SET {sets} WHERE offer_id = ?", vals
        )


def get_offer(offer_id: int) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM offers WHERE offer_id = ?", (offer_id,)
        ).fetchone()
    return dict(row) if row else None


# ═══ TEMPLATE ═══

def get_template() -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM message_template WHERE id = 1"
        ).fetchone()
    return dict(row) if row else {}


def update_template(**kwargs):
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM message_template WHERE id = 1"
        ).fetchone()
        kwargs["updated_at"] = time.time()

        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            conn.execute(
                f"UPDATE message_template SET {sets} WHERE id = 1",
                list(kwargs.values())
            )
        else:
            keys = ", ".join(["id"] + list(kwargs.keys()))
            placeholders = ", ".join(["1"] + ["?"] * len(kwargs))
            conn.execute(
                f"INSERT INTO message_template ({keys}) "
                f"VALUES ({placeholders})",
                list(kwargs.values())
            )


# ═══ DAILY STATS ═══

def record_order(
    offer_id: int, price: float,
    limits_min: float, limits_max: float,
    period_start: float
):
    """Записать новый ордер в статистику текущего периода."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO daily_stats "
            "(offer_id, price, limits_min, limits_max, period_type, period_start, recorded_at) "
            "VALUES (?, ?, ?, ?, 'day', ?, ?)",
            (offer_id, price, limits_min, limits_max, period_start, time.time())
        )


def get_stats_for_period(period_start: float, period_end: float) -> list:
    """Получить все ордера за указанный период."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM daily_stats "
            "WHERE recorded_at >= ? AND recorded_at < ? "
            "ORDER BY recorded_at",
            (period_start, period_end)
        ).fetchall()
    return [dict(r) for r in rows]


def clear_stats_before(before_timestamp: float):
    """Удалить статистику старше указанного времени."""
    with get_db() as conn:
        conn.execute(
            "DELETE FROM daily_stats WHERE recorded_at < ?",
            (before_timestamp,)
        )


def save_report_history(
    period_type: str, period_start: float, period_end: float,
    order_count: int, total_volume: float, avg_price: float
):
    """Сохранить историю отчёта."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO report_history "
            "(period_type, period_start, period_end, order_count, "
            "total_volume, avg_price, sent_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (period_type, period_start, period_end,
             order_count, total_volume, avg_price, time.time())
        )


# ═══ REPORT TEMPLATE ═══

def get_report_template() -> dict:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM report_template WHERE id = 1"
        ).fetchone()
    return dict(row) if row else {}


def update_report_template(**kwargs):
    with get_db() as conn:
        kwargs["updated_at"] = time.time()
        existing = conn.execute(
            "SELECT id FROM report_template WHERE id = 1"
        ).fetchone()

        if existing:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            conn.execute(
                f"UPDATE report_template SET {sets} WHERE id = 1",
                list(kwargs.values())
            )
        else:
            keys = ", ".join(["id"] + list(kwargs.keys()))
            placeholders = ", ".join(["1"] + ["?"] * len(kwargs))
            conn.execute(
                f"INSERT INTO report_template ({keys}) "
                f"VALUES ({placeholders})",
                list(kwargs.values())
            )