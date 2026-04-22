"""
database/queries.py — все SQL-запросы к базе данных.
Разделены по доменам: транзакции, категории, бюджеты, напоминания.
"""

from __future__ import annotations
import logging
from datetime import date, datetime
from typing import Any

import aiosqlite
from .db import get_db

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# ТРАНЗАКЦИИ
# ═══════════════════════════════════════════════════════════════════════════════

async def add_transaction(
    user_id: int,
    amount: float,
    category_id: int | None,
    note: str | None,
    is_income: bool = False,
    source: str = "text",
    txn_date: str | None = None,
) -> int:
    if txn_date is None:
        txn_date = date.today().isoformat()
    async with get_db() as db:
        cursor = await db.execute(
            """
            INSERT INTO transactions(user_id,category_id,amount,is_income,note,source,txn_date)
            VALUES(?,?,?,?,?,?,?)
            """,
            (user_id, category_id, amount, int(is_income), note, source, txn_date),
        )
        await db.commit()
        return cursor.lastrowid


async def delete_transaction(txn_id: int, user_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM transactions WHERE id=? AND user_id=?", (txn_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_last_transactions(user_id: int, limit: int = 10) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT t.id, t.amount, t.is_income, t.note, t.source, t.txn_date,
                       c.name AS category, c.icon AS cat_icon
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ?
                ORDER BY t.created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def get_monthly_summary(user_id: int, year: int, month: int) -> dict:
    """Итоги за месяц: расходы по категориям + доходы + баланс."""
    month_str = f"{year}-{month:02d}"
    async with get_db() as db:
        # Расходы по категориям
        expense_rows = await (
            await db.execute(
                """
                SELECT c.name, c.icon, SUM(t.amount) AS total
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id=? AND t.is_income=0
                  AND strftime('%Y-%m', t.txn_date)=?
                GROUP BY t.category_id
                ORDER BY total DESC
                """,
                (user_id, month_str),
            )
        ).fetchall()

        # Общие суммы
        totals = await (
            await db.execute(
                """
                SELECT
                  SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS expenses,
                  SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS income
                FROM transactions
                WHERE user_id=? AND strftime('%Y-%m', txn_date)=?
                """,
                (user_id, month_str),
            )
        ).fetchone()

    return {
        "expenses_by_category": [dict(r) for r in expense_rows],
        "total_expenses": totals["expenses"] or 0.0,
        "total_income": totals["income"] or 0.0,
        "balance": (totals["income"] or 0.0) - (totals["expenses"] or 0.0),
    }


async def get_yearly_summary(user_id: int, year: int) -> list[dict]:
    """Помесячная разбивка доходов и расходов за год."""
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT
                  strftime('%m', txn_date) AS month,
                  SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS expenses,
                  SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS income
                FROM transactions
                WHERE user_id=? AND strftime('%Y', txn_date)=?
                GROUP BY month
                ORDER BY month
                """,
                (user_id, str(year)),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def get_weekly_expenses(user_id: int) -> list[dict]:
    """Расходы за последние 7 дней."""
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT
                  t.txn_date,
                  c.name AS category, c.icon,
                  SUM(t.amount) AS total
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id=? AND t.is_income=0
                  AND t.txn_date >= date('now', '-6 days')
                GROUP BY t.txn_date, t.category_id
                ORDER BY t.txn_date
                """,
                (user_id,),
            )
        ).fetchall()
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# КАТЕГОРИИ
# ═══════════════════════════════════════════════════════════════════════════════

async def get_categories(user_id: int, is_income: bool = False) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                "SELECT id, name, icon, color FROM categories WHERE user_id=? AND is_income=? ORDER BY is_system DESC, name",
                (user_id, int(is_income)),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def add_category(
    user_id: int, name: str, icon: str, color: str, is_income: bool
) -> int | None:
    try:
        async with get_db() as db:
            cur = await db.execute(
                "INSERT INTO categories(user_id,name,icon,color,is_income) VALUES(?,?,?,?,?)",
                (user_id, name, icon, color, int(is_income)),
            )
            await db.commit()
            return cur.lastrowid
    except aiosqlite.IntegrityError:
        return None  # уже существует


async def delete_category(cat_id: int, user_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM categories WHERE id=? AND user_id=? AND is_system=0",
            (cat_id, user_id),
        )
        await db.commit()
        return cur.rowcount > 0


# ═══════════════════════════════════════════════════════════════════════════════
# БЮДЖЕТЫ
# ═══════════════════════════════════════════════════════════════════════════════

async def set_budget(user_id: int, category_id: int, amount: float, period: str = "month") -> None:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO budgets(user_id,category_id,amount,period) VALUES(?,?,?,?)
            ON CONFLICT(user_id,category_id,period) DO UPDATE SET amount=excluded.amount
            """,
            (user_id, category_id, amount, period),
        )
        await db.commit()


async def get_budgets_with_spent(user_id: int) -> list[dict]:
    """Все бюджеты с суммой потраченного в текущем месяце."""
    month_str = datetime.now().strftime("%Y-%m")
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT
                  b.id, c.name, c.icon, b.amount AS budget,
                  COALESCE(
                    (SELECT SUM(t.amount) FROM transactions t
                     WHERE t.user_id=b.user_id AND t.category_id=b.category_id
                       AND t.is_income=0 AND strftime('%Y-%m', t.txn_date)=?),
                    0
                  ) AS spent,
                  b.period
                FROM budgets b
                JOIN categories c ON b.category_id = c.id
                WHERE b.user_id=?
                ORDER BY (spent*1.0/b.amount) DESC
                """,
                (month_str, user_id),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def delete_budget(budget_id: int, user_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM budgets WHERE id=? AND user_id=?", (budget_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def set_monthly_limit(user_id: int, limit: float | None) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET monthly_limit=?, updated_at=datetime('now') WHERE id=?",
            (limit, user_id),
        )
        await db.commit()


async def get_user_settings(user_id: int) -> dict | None:
    async with get_db() as db:
        row = await (
            await db.execute(
                "SELECT currency, timezone, monthly_limit FROM users WHERE id=?",
                (user_id,),
            )
        ).fetchone()
    return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════════════════════
# НАПОМИНАНИЯ
# ═══════════════════════════════════════════════════════════════════════════════

async def add_reminder(
    user_id: int,
    title: str,
    remind_at: str,
    amount: float | None = None,
    repeat_type: str = "none",
    repeat_day: int | None = None,
    note: str | None = None,
) -> int:
    async with get_db() as db:
        cur = await db.execute(
            """
            INSERT INTO reminders(user_id,title,amount,remind_at,repeat_type,repeat_day,note)
            VALUES(?,?,?,?,?,?,?)
            """,
            (user_id, title, amount, remind_at, repeat_type, repeat_day, note),
        )
        await db.commit()
        return cur.lastrowid


async def get_active_reminders(user_id: int) -> list[dict]:
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT id, title, amount, remind_at, repeat_type, note
                FROM reminders
                WHERE user_id=? AND is_active=1
                ORDER BY remind_at
                """,
                (user_id,),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def get_due_reminders(until_dt: str) -> list[dict]:
    """Напоминания, у которых remind_at <= until_dt."""
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT r.id, r.user_id, r.title, r.amount, r.remind_at,
                       r.repeat_type, r.repeat_day, r.note
                FROM reminders r
                WHERE r.is_active=1 AND r.remind_at <= ?
                ORDER BY r.remind_at
                """,
                (until_dt,),
            )
        ).fetchall()
    return [dict(r) for r in rows]


async def update_reminder_time(reminder_id: int, new_dt: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE reminders SET remind_at=? WHERE id=?", (new_dt, reminder_id)
        )
        await db.commit()


async def deactivate_reminder(reminder_id: int) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE reminders SET is_active=0 WHERE id=?", (reminder_id,)
        )
        await db.commit()


async def delete_reminder(reminder_id: int, user_id: int) -> bool:
    async with get_db() as db:
        cur = await db.execute(
            "DELETE FROM reminders WHERE id=? AND user_id=?", (reminder_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0