"""
services/gamification.py — система достижений, уровней и опыта.

Уровни:
  1  — Новичок         (0 XP)
  2  — Копилка         (100 XP)
  3  — Экономист       (300 XP)
  4  — Финансист       (600 XP)
  5  — Инвестор        (1000 XP)
  6  — Богач           (1500 XP)
  7  — Финансовый гуру (2500 XP)
  8  — Магнат          (4000 XP)
  9  — Олигарх         (6000 XP)
  10 — Финансовый джедай (10000 XP)

Достижения дают XP и разблокируются по условиям.
"""

from __future__ import annotations
from dataclasses import dataclass
from database.db import get_db


# Уровни

LEVELS = [
    (0,     1,  "🌱 Новичок"),
    (100,   2,  "🐣 Копилка"),
    (300,   3,  "📊 Экономист"),
    (600,   4,  "💼 Финансист"),
    (1000,  5,  "📈 Инвестор"),
    (1500,  6,  "💰 Богач"),
    (2500,  7,  "🎓 Финансовый гуру"),
    (4000,  8,  "🏦 Магнат"),
    (6000,  9,  "👑 Олигарх"),
    (10000, 10, "⚡ Финансовый джедай"),
]


def get_level_info(xp: int) -> dict:
    """Возвращает текущий уровень, название и прогресс до следующего."""
    current_level = LEVELS[0]
    next_level    = LEVELS[1] if len(LEVELS) > 1 else None

    for i, (min_xp, lvl, name) in enumerate(LEVELS):
        if xp >= min_xp:
            current_level = (min_xp, lvl, name)
            next_level    = LEVELS[i + 1] if i + 1 < len(LEVELS) else None

    min_xp, lvl, name = current_level
    if next_level:
        next_xp, _, _ = next_level
        progress = xp - min_xp
        needed   = next_xp - min_xp
    else:
        progress = xp - min_xp
        needed   = progress  # макс уровень

    return {
        "level": lvl,
        "name": name,
        "xp": xp,
        "progress": progress,
        "needed": needed,
        "next_level": next_level,
        "is_max": next_level is None,
    }


# Достижения

ACHIEVEMENTS = {
    "first_expense": {
        "title": "Первый шаг",
        "icon": "👶",
        "desc": "Записал первый расход",
        "xp": 10,
    },
    "first_income": {
        "title": "Первый доход",
        "icon": "💚",
        "desc": "Записал первый доход",
        "xp": 10,
    },
    "streak_7": {
        "title": "Неделя без пропусков",
        "icon": "🔥",
        "desc": "7 дней подряд вёл учёт",
        "xp": 50,
    },
    "streak_30": {
        "title": "Марафонец",
        "icon": "🏃",
        "desc": "30 дней подряд вёл учёт",
        "xp": 200,
    },
    "txn_10": {
        "title": "Начинающий",
        "icon": "📝",
        "desc": "10 транзакций записано",
        "xp": 20,
    },
    "txn_50": {
        "title": "Активный",
        "icon": "⚡",
        "desc": "50 транзакций записано",
        "xp": 50,
    },
    "txn_100": {
        "title": "Опытный",
        "icon": "🎯",
        "desc": "100 транзакций записано",
        "xp": 100,
    },
    "txn_500": {
        "title": "Ветеран",
        "icon": "🏆",
        "desc": "500 транзакций записано",
        "xp": 300,
    },
    "goal_created": {
        "title": "Мечтатель",
        "icon": "🌟",
        "desc": "Создал первую финансовую цель",
        "xp": 30,
    },
    "goal_done": {
        "title": "Целеустремлённый",
        "icon": "🎉",
        "desc": "Достиг финансовой цели",
        "xp": 150,
    },
    "budget_set": {
        "title": "Плановик",
        "icon": "📋",
        "desc": "Установил первый бюджет",
        "xp": 25,
    },
    "voice_used": {
        "title": "Голосовой",
        "icon": "🎙",
        "desc": "Записал расход голосом",
        "xp": 15,
    },
    "saved_1000": {
        "title": "Первая тысяча",
        "icon": "💵",
        "desc": "Сэкономил 1 000 с (баланс +1 000)",
        "xp": 30,
    },
    "saved_10000": {
        "title": "Десятка",
        "icon": "💰",
        "desc": "Сэкономил 10 000 с",
        "xp": 100,
    },
    "reminder_set": {
        "title": "Пунктуальный",
        "icon": "⏰",
        "desc": "Создал первое напоминание",
        "xp": 20,
    },
    "categories_custom": {
        "title": "Организатор",
        "icon": "🗂",
        "desc": "Создал свою категорию",
        "xp": 15,
    },
}


# БД для геймификации

async def init_gamification_tables() -> None:
    async with get_db() as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS user_xp (
                user_id    INTEGER PRIMARY KEY,
                xp         INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id        INTEGER NOT NULL,
                achievement_id TEXT    NOT NULL,
                earned_at      TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, achievement_id)
            );
        """)
        await db.commit()


async def get_user_xp(user_id: int) -> int:
    async with get_db() as db:
        row = await (await db.execute(
            "SELECT xp FROM user_xp WHERE user_id=?", (user_id,)
        )).fetchone()
    return row["xp"] if row else 0


async def add_xp(user_id: int, amount: int) -> int:
    """Добавляет XP и возвращает новое значение."""
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO user_xp(user_id, xp) VALUES(?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                xp = xp + excluded.xp,
                updated_at = datetime('now')
            """,
            (user_id, amount)
        )
        await db.commit()
        row = await (await db.execute(
            "SELECT xp FROM user_xp WHERE user_id=?", (user_id,)
        )).fetchone()
    return row["xp"] if row else amount


async def get_earned_achievements(user_id: int) -> list[str]:
    async with get_db() as db:
        rows = await (await db.execute(
            "SELECT achievement_id FROM user_achievements WHERE user_id=? ORDER BY earned_at DESC",
            (user_id,)
        )).fetchall()
    return [r["achievement_id"] for r in rows]


async def award_achievement(user_id: int, achievement_id: str) -> bool:
    """
    Выдаёт достижение если ещё не получено.
    Возвращает True если достижение новое.
    """
    if achievement_id not in ACHIEVEMENTS:
        return False
    async with get_db() as db:
        try:
            await db.execute(
                "INSERT INTO user_achievements(user_id, achievement_id) VALUES(?,?)",
                (user_id, achievement_id)
            )
            await db.commit()
            # Добавляем XP за достижение
            xp = ACHIEVEMENTS[achievement_id]["xp"]
            await add_xp(user_id, xp)
            return True
        except Exception:
            return False  # уже есть


async def check_and_award(user_id: int, event: str, value: int = 0) -> list[dict]:
    """
    Проверяет условия достижений по событию и выдаёт новые.
    Возвращает список новых достижений.
    """
    await init_gamification_tables()
    earned   = await get_earned_achievements(user_id)
    new_ones = []

    async def _try(ach_id: str):
        if ach_id not in earned:
            is_new = await award_achievement(user_id, ach_id)
            if is_new:
                new_ones.append({**ACHIEVEMENTS[ach_id], "id": ach_id})

    if event == "expense_added":
        await _try("first_expense")
        if value >= 10:   await _try("txn_10")
        if value >= 50:   await _try("txn_50")
        if value >= 100:  await _try("txn_100")
        if value >= 500:  await _try("txn_500")
        # +5 XP за каждую транзакцию
        await add_xp(user_id, 5)

    elif event == "income_added":
        await _try("first_income")
        await add_xp(user_id, 5)

    elif event == "goal_created":
        await _try("goal_created")

    elif event == "goal_done":
        await _try("goal_done")

    elif event == "budget_set":
        await _try("budget_set")

    elif event == "voice_used":
        await _try("voice_used")

    elif event == "reminder_set":
        await _try("reminder_set")

    elif event == "category_created":
        await _try("categories_custom")

    elif event == "balance_check":
        if value >= 1000:   await _try("saved_1000")
        if value >= 10000:  await _try("saved_10000")

    return new_ones


def fmt_xp_bar(progress: int, needed: int, width: int = 10) -> str:
    """Прогресс-бар опыта."""
    if needed <= 0:
        return "█" * width
    filled = min(int(progress / needed * width), width)
    return "█" * filled + "░" * (width - filled)