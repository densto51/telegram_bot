"""
handlers/quick.py — быстрые кнопки частых трат + статистика профиля /stats

Быстрые кнопки:
  - Бот анализирует топ-5 частых расходов пользователя
  - Показывает их как inline-кнопки: [☕ Кофе 150] [🚗 Такси 300]
  - Одно нажатие → расход записан без лишних шагов

/stats — статистика профиля:
  - Всего транзакций
  - Потрачено/получено за всё время
  - Любимая категория
  - В системе с...
  - Среднедневной расход
"""

import logging
from datetime import datetime, date

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)

from database.queries import add_transaction
from keyboards.main_menu import main_menu_kb
from utils.formatters import fmt_amount

logger = logging.getLogger(__name__)
router = Router(name="quick")

# SQL-запросы (встроены прямо здесь для простоты)
async def _get_top_expenses(user_id: int, limit: int = 5) -> list[dict]:
    """Топ-N часто повторяющихся расходов пользователя."""
    from database.db import get_db
    async with get_db() as db:
        rows = await (
            await db.execute(
                """
                SELECT
                    c.name      AS category,
                    c.icon      AS cat_icon,
                    c.id        AS category_id,
                    t.note,
                    ROUND(AVG(t.amount)) AS avg_amount,
                    COUNT(*)             AS cnt
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.is_income = 0
                  AND t.note IS NOT NULL AND t.note != ''
                GROUP BY LOWER(t.note)
                HAVING cnt >= 2
                ORDER BY cnt DESC, avg_amount DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
        ).fetchall()

        # Если не хватает с заметками - добираем по категориям
        if len(rows) < limit:
            extra = await (
                await db.execute(
                    """
                    SELECT
                        c.name AS category,
                        c.icon AS cat_icon,
                        c.id   AS category_id,
                        NULL   AS note,
                        ROUND(AVG(t.amount)) AS avg_amount,
                        COUNT(*) AS cnt
                    FROM transactions t
                    LEFT JOIN categories c ON t.category_id = c.id
                    WHERE t.user_id = ? AND t.is_income = 0
                      AND t.category_id IS NOT NULL
                    GROUP BY t.category_id
                    ORDER BY cnt DESC
                    LIMIT ?
                    """,
                    (user_id, limit - len(rows)),
                )
            ).fetchall()
            rows = list(rows) + list(extra)

    return [dict(r) for r in rows]


async def _get_user_stats(user_id: int) -> dict:
    """Полная статистика пользователя."""
    from database.db import get_db
    async with get_db() as db:
        # Общие суммы
        totals = await (
            await db.execute(
                """
                SELECT
                    COUNT(*) AS total_txns,
                    SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS total_expense,
                    SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS total_income,
                    MIN(txn_date) AS first_date,
                    MAX(txn_date) AS last_date
                FROM transactions
                WHERE user_id = ?
                """,
                (user_id,),
            )
        ).fetchone()

        # Любимая категория
        fav_cat = await (
            await db.execute(
                """
                SELECT c.name, c.icon, COUNT(*) AS cnt
                FROM transactions t
                LEFT JOIN categories c ON t.category_id = c.id
                WHERE t.user_id = ? AND t.is_income = 0
                  AND c.name IS NOT NULL
                GROUP BY t.category_id
                ORDER BY cnt DESC
                LIMIT 1
                """,
                (user_id,),
            )
        ).fetchone()

        # Текущий месяц
        month_str = datetime.now().strftime("%Y-%m")
        month_data = await (
            await db.execute(
                """
                SELECT
                    SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS month_expense,
                    SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS month_income,
                    COUNT(*) AS month_txns
                FROM transactions
                WHERE user_id = ? AND strftime('%Y-%m', txn_date) = ?
                """,
                (user_id, month_str),
            )
        ).fetchone()

        # Дата регистрации
        user_info = await (
            await db.execute(
                "SELECT created_at FROM users WHERE id = ?",
                (user_id,),
            )
        ).fetchone()

    return {
        "total_txns":    totals["total_txns"]    or 0,
        "total_expense": totals["total_expense"] or 0.0,
        "total_income":  totals["total_income"]  or 0.0,
        "first_date":    totals["first_date"],
        "last_date":     totals["last_date"],
        "fav_cat_name":  fav_cat["name"]  if fav_cat else None,
        "fav_cat_icon":  fav_cat["icon"]  if fav_cat else "❓",
        "fav_cat_cnt":   fav_cat["cnt"]   if fav_cat else 0,
        "month_expense": month_data["month_expense"] or 0.0,
        "month_income":  month_data["month_income"]  or 0.0,
        "month_txns":    month_data["month_txns"]    or 0,
        "registered_at": user_info["created_at"] if user_info else None,
    }

# БЫСТРЫЕ КНОПКИ
def _quick_kb(top: list[dict]) -> InlineKeyboardMarkup:
    """Строит клавиатуру из топ расходов."""
    buttons = []
    row = []
    for i, item in enumerate(top):
        icon    = item.get("cat_icon") or "💸"
        label   = item.get("note") or item.get("category") or "Расход"
        amount  = item["avg_amount"]
        cat_id  = item.get("category_id") or 0
        # callback: quick:{category_id}:{amount}:{label}
        cb_data = f"quick:{cat_id}:{int(amount)}:{label[:15]}"
        row.append(InlineKeyboardButton(
            text=f"{icon} {label[:12]} {int(amount)}",
            callback_data=cb_data,
        ))
        if len(row) == 2 or i == len(top) - 1:
            buttons.append(row)
            row = []

    buttons.append([
        InlineKeyboardButton(text="➕ Другой расход", callback_data="add_expense"),
        InlineKeyboardButton(text="🏠 Меню",          callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "quick_expense")
async def cb_quick_expense(callback: CallbackQuery) -> None:
    """Показывает быстрые кнопки частых трат."""
    top = await _get_top_expenses(callback.from_user.id)

    if not top:
        # Нет истории — обычный ввод
        from aiogram.fsm.context import FSMContext
        await callback.message.edit_text(
            "⚡ <b>Быстрый расход</b>\n\n"
            "Пока не накопилось истории трат.\n"
            "Введи первый расход вручную:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ Ввести расход", callback_data="add_expense")],
                [InlineKeyboardButton(text="🏠 Меню",          callback_data="main_menu")],
            ])
        )
        await callback.answer()
        return

    lines = ["⚡ <b>Быстрый расход</b>\n\nВыбери из частых трат:"]
    for i, item in enumerate(top, 1):
        icon  = item.get("cat_icon") or "💸"
        label = item.get("note") or item.get("category") or "Расход"
        lines.append(f"  {i}. {icon} {label} — <b>{fmt_amount(item['avg_amount'])}</b> (×{item['cnt']})")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=_quick_kb(top),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("quick:"))
async def cb_quick_save(callback: CallbackQuery) -> None:
    """Сохраняет быстрый расход одним нажатием."""
    parts    = callback.data.split(":", 3)
    cat_id   = int(parts[1]) if parts[1] != "0" else None
    amount   = float(parts[2])
    note     = parts[3] if len(parts) > 3 else None

    txn_id = await add_transaction(
        user_id=callback.from_user.id,
        amount=amount,
        category_id=cat_id,
        note=note,
        is_income=False,
        source="quick",
    )

    await callback.message.edit_text(
        f"✅ <b>Записано!</b>\n\n"
        f"💸 <b>{fmt_amount(amount)}</b>"
        + (f"\n📝 {note}" if note else "")
        + f"\n🆔 #{txn_id}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚡ Ещё быстрый расход", callback_data="quick_expense")],
            [InlineKeyboardButton(text="🏠 Главное меню",        callback_data="main_menu")],
        ])
    )
    await callback.answer("✅ Сохранено!")

    from services.gamification import check_and_award
    from handlers.gamification import notify_achievements
    from database.queries import get_last_transactions

    all_txns = await get_last_transactions(callback.from_user.id, limit=1000)
    new_achievements = await check_and_award(
        user_id=callback.from_user.id,
        event="expense_added",
        value=len(all_txns),
    )
    if new_achievements:
        await notify_achievements(callback.message, new_achievements)


@router.message(Command("quick"))
async def cmd_quick(message: Message) -> None:
    top = await _get_top_expenses(message.from_user.id)
    if not top:
        await message.answer(
            "⚡ Пока нет истории трат. Введи несколько расходов и попробуй снова.",
            reply_markup=main_menu_kb()
        )
        return
    lines = ["⚡ <b>Быстрый расход</b>\n\nВыбери из частых трат:"]
    for i, item in enumerate(top, 1):
        icon  = item.get("cat_icon") or "💸"
        label = item.get("note") or item.get("category") or "Расход"
        lines.append(f"  {i}. {icon} {label} — <b>{fmt_amount(item['avg_amount'])}</b> (×{item['cnt']})")
    await message.answer("\n".join(lines), reply_markup=_quick_kb(top))



# СТАТИСТИКА ПРОФИЛЯ /stats


@router.message(Command("stats"))
@router.callback_query(F.data == "stats")
async def show_stats(event) -> None:
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    s = await _get_user_stats(user_id)

    # Дата регистрации
    reg_str = "—"
    if s["registered_at"]:
        try:
            reg_dt  = datetime.fromisoformat(s["registered_at"])
            reg_str = reg_dt.strftime("%d.%m.%Y")
        except Exception:
            reg_str = s["registered_at"][:10]

    # Среднедневной расход
    avg_daily = 0.0
    if s["first_date"] and s["last_date"] and s["total_expense"] > 0:
        try:
            d1   = date.fromisoformat(s["first_date"])
            d2   = date.today()
            days = max((d2 - d1).days, 1)
            avg_daily = s["total_expense"] / days
        except Exception:
            pass

    # Баланс
    balance = s["total_income"] - s["total_expense"]

    # Текущий месяц
    now       = datetime.now()
    month_names = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]

    fav = (
        f"{s['fav_cat_icon']} {s['fav_cat_name']} ({s['fav_cat_cnt']} раз)"
        if s["fav_cat_name"] else "—"
    )

    text = (
        f"👤 <b>Статистика профиля</b>\n"
        f"{'─' * 28}\n\n"

        f"📅 <b>В системе с:</b> {reg_str}\n"
        f"📊 <b>Всего операций:</b> {s['total_txns']}\n\n"

        f"{'─' * 28}\n"
        f"<b>За всё время:</b>\n"
        f"💚 Доходы:  <b>{fmt_amount(s['total_income'])}</b>\n"
        f"💸 Расходы: <b>{fmt_amount(s['total_expense'])}</b>\n"
        f"{'📈' if balance >= 0 else '📉'} Баланс:   <b>{fmt_amount(balance)}</b>\n\n"

        f"{'─' * 28}\n"
        f"<b>{month_names[now.month]} {now.year}:</b>\n"
        f"💚 Доходы:  <b>{fmt_amount(s['month_income'])}</b>\n"
        f"💸 Расходы: <b>{fmt_amount(s['month_expense'])}</b>\n"
        f"📋 Операций: <b>{s['month_txns']}</b>\n\n"

        f"{'─' * 28}\n"
        f"🏆 <b>Любимая категория:</b>\n"
        f"   {fav}\n\n"
        f"📆 <b>Средний расход в день:</b>\n"
        f"   <b>{fmt_amount(avg_daily)}</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Быстрый расход", callback_data="quick_expense")],
        [InlineKeyboardButton(text="📊 Отчёты",         callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Главное меню",   callback_data="main_menu")],
    ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb)
        await event.answer()
    else:
        await msg.answer(text, reply_markup=kb)