"""
services/pattern_detector.py — анализ паттернов регулярных расходов.

Алгоритм:
  1. Берём транзакции за последние 3 месяца
  2. Группируем по описанию (note) или категории
  3. Если расход повторяется >= 2 раз — паттерн найден (без требования разных месяцев)
  4. Проверяем что на этот паттерн ещё нет напоминания
  5. Возвращаем список паттернов для предложения
"""

from __future__ import annotations
from dataclasses import dataclass
from database.db import get_db


@dataclass
class SpendingPattern:
    key: str
    category: str | None
    category_id: int | None
    icon: str
    avg_amount: float
    count: int
    last_date: str


async def detect_patterns(user_id: int) -> list[SpendingPattern]:
    async with get_db() as db:
        # По описанию (note)
        rows_by_note = await (await db.execute(
            """
            SELECT
                LOWER(TRIM(t.note))  AS grp_key,
                t.note               AS display_note,
                c.name               AS category,
                c.icon               AS cat_icon,
                c.id                 AS category_id,
                ROUND(AVG(t.amount)) AS avg_amount,
                COUNT(*)             AS cnt,
                MAX(t.txn_date)      AS last_date
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.is_income = 0
              AND t.note IS NOT NULL AND TRIM(t.note) != ''
              AND t.txn_date >= date('now', '-3 months')
            GROUP BY LOWER(TRIM(t.note))
            HAVING cnt >= 2
            ORDER BY cnt DESC, avg_amount DESC
            LIMIT 10
            """,
            (user_id,),
        )).fetchall()

        # По категории (без описания)
        rows_by_cat = await (await db.execute(
            """
            SELECT
                'cat_' || c.id       AS grp_key,
                c.name               AS display_note,
                c.name               AS category,
                c.icon               AS cat_icon,
                c.id                 AS category_id,
                ROUND(AVG(t.amount)) AS avg_amount,
                COUNT(*)             AS cnt,
                MAX(t.txn_date)      AS last_date
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = ?
              AND t.is_income = 0
              AND (t.note IS NULL OR TRIM(t.note) = '')
              AND t.txn_date >= date('now', '-3 months')
              AND c.id IS NOT NULL
            GROUP BY c.id
            HAVING cnt >= 2
            ORDER BY cnt DESC
            LIMIT 5
            """,
            (user_id,),
        )).fetchall()

        # Существующие напоминания — чтобы не дублировать
        existing = await (await db.execute(
            "SELECT LOWER(title) FROM reminders WHERE user_id=? AND is_active=1",
            (user_id,),
        )).fetchall()
        existing_titles = {r[0] for r in existing}

    patterns = []
    seen_keys = set()

    for row in list(rows_by_note) + list(rows_by_cat):
        r = dict(row)
        key = r["grp_key"]
        if key in seen_keys:
            continue
        seen_keys.add(key)

        display = r["display_note"] or r["category"] or "Расход"

        # Пропускаем если уже есть похожее напоминание
        if any(
            _similarity(display.lower(), title) > 0.6
            for title in existing_titles
        ):
            continue

        patterns.append(SpendingPattern(
            key=key,
            category=r["category"],
            category_id=r["category_id"],
            icon=r["cat_icon"] or "💸",
            avg_amount=float(r["avg_amount"]),
            count=int(r["cnt"]),
            last_date=r["last_date"],
        ))

    return patterns[:5]


def _similarity(a: str, b: str) -> float:
    words_a = set(a.split())
    words_b = set(b.split())
    if not words_a or not words_b:
        return 0.0
    common = words_a & words_b
    return len(common) / max(len(words_a), len(words_b))