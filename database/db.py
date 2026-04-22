"""
database/db.py — инициализация SQLite3.
Правильное использование aiosqlite: через asynccontextmanager, новое соединение на каждый запрос.
"""

import aiosqlite
import logging
from contextlib import asynccontextmanager
from config import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.DATABASE_PATH

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY,
    username      TEXT,
    full_name     TEXT,
    currency      TEXT    NOT NULL DEFAULT 'KGS',
    timezone      TEXT    NOT NULL DEFAULT 'Asia/Bishkek',
    monthly_limit REAL    DEFAULT NULL,
    created_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS categories (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name       TEXT    NOT NULL,
    icon       TEXT    NOT NULL DEFAULT '💰',
    color      TEXT    NOT NULL DEFAULT '#3498db',
    is_income  INTEGER NOT NULL DEFAULT 0,
    is_system  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(user_id, name, is_income)
);

CREATE TABLE IF NOT EXISTS transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    amount      REAL    NOT NULL CHECK(amount > 0),
    is_income   INTEGER NOT NULL DEFAULT 0,
    note        TEXT,
    source      TEXT    NOT NULL DEFAULT 'text',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    txn_date    TEXT    NOT NULL DEFAULT (date('now'))
);

CREATE TABLE IF NOT EXISTS budgets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount      REAL    NOT NULL CHECK(amount > 0),
    period      TEXT    NOT NULL DEFAULT 'month',
    UNIQUE(user_id, category_id, period)
);

CREATE TABLE IF NOT EXISTS reminders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title        TEXT    NOT NULL,
    amount       REAL,
    remind_at    TEXT    NOT NULL,
    repeat_type  TEXT    NOT NULL DEFAULT 'none',
    repeat_day   INTEGER,
    is_active    INTEGER NOT NULL DEFAULT 1,
    note         TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_txn_user_date    ON transactions(user_id, txn_date);
CREATE INDEX IF NOT EXISTS idx_txn_category     ON transactions(user_id, category_id);
CREATE INDEX IF NOT EXISTS idx_reminders_active ON reminders(user_id, is_active, remind_at);
CREATE INDEX IF NOT EXISTS idx_budgets_user     ON budgets(user_id);
"""

DEFAULT_EXPENSE_CATEGORIES = [
    ("🍔 Еда",         "🍔", "#e74c3c"),
    ("🚗 Транспорт",   "🚗", "#e67e22"),
    ("🏠 Жильё",       "🏠", "#8e44ad"),
    ("💊 Здоровье",    "💊", "#27ae60"),
    ("🎮 Развлечения", "🎮", "#2980b9"),
    ("👗 Одежда",      "👗", "#e91e63"),
    ("📚 Образование", "📚", "#16a085"),
    ("🛒 Продукты",    "🛒", "#d35400"),
    ("☕ Кафе",        "☕", "#795548"),
    ("📱 Связь",       "📱", "#607d8b"),
    ("💡 Коммуналка",  "💡", "#f39c12"),
    ("🎁 Подарки",     "🎁", "#9c27b0"),
    ("✈️ Путешествия", "✈️", "#00bcd4"),
    ("🐾 Питомцы",     "🐾", "#8bc34a"),
    ("❓ Прочее",      "❓", "#95a5a6"),
]

DEFAULT_INCOME_CATEGORIES = [
    ("💼 Зарплата",    "💼", "#2ecc71"),
    ("📈 Инвестиции",  "📈", "#1abc9c"),
    ("🎰 Подработка",  "🎰", "#3498db"),
    ("🎁 Подарок",     "🎁", "#9b59b6"),
    ("💸 Другой доход","💸", "#f1c40f"),
]


async def init_db() -> None:
    """Создаёт таблицы при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
    logger.info("DB schema applied: %s", DB_PATH)


@asynccontextmanager
async def get_db():
    """
    Async context manager — открывает новое соединение на каждый вызов.

    Использование:
        async with get_db() as db:
            await db.execute(...)
    """
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def ensure_user(user_id: int, username, full_name: str) -> None:
    """Регистрирует пользователя если его ещё нет, иначе обновляет имя."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users(id, username, full_name) VALUES(?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                username  = excluded.username,
                full_name = excluded.full_name,
                updated_at = datetime('now')
            """,
            (user_id, username, full_name),
        )
        cursor = await db.execute(
            "SELECT COUNT(*) FROM categories WHERE user_id=? AND is_system=1",
            (user_id,),
        )
        row = await cursor.fetchone()
        if row[0] == 0:
            await db.executemany(
                "INSERT OR IGNORE INTO categories(user_id,name,icon,color,is_income,is_system) VALUES(?,?,?,?,0,1)",
                [(user_id, name, icon, color) for name, icon, color in DEFAULT_EXPENSE_CATEGORIES],
            )
            await db.executemany(
                "INSERT OR IGNORE INTO categories(user_id,name,icon,color,is_income,is_system) VALUES(?,?,?,?,1,1)",
                [(user_id, name, icon, color) for name, icon, color in DEFAULT_INCOME_CATEGORIES],
            )
        await db.commit()