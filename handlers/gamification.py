"""
handlers/gamification.py — отображение уровня, достижений и сравнения с прошлым месяцем.
"""

import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.exceptions import TelegramBadRequest

from database.db import get_db
from keyboards.main_menu import main_menu_kb
from services.gamification import (
    get_user_xp, get_level_info, get_earned_achievements,
    ACHIEVEMENTS, LEVELS, fmt_xp_bar, init_gamification_tables,
    check_and_award,
)
from utils.formatters import fmt_amount

logger = logging.getLogger(__name__)
router = Router(name="gamification")



#ПРОФИЛЬ С УРОВНЕМ
@router.message(Command("level"))
@router.callback_query(F.data == "my_level")
async def show_level(event) -> None:
    await init_gamification_tables()
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    xp       = await get_user_xp(user_id)
    info     = get_level_info(xp)
    earned   = await get_earned_achievements(user_id)
    bar      = fmt_xp_bar(info["progress"], info["needed"])

    if info["is_max"]:
        progress_text = f"{bar} <b>MAX</b> 🏆"
    else:
        _, next_lvl, next_name = info["next_level"]
        progress_text = (
            f"{bar} <b>{info['progress']}/{info['needed']} XP</b>\n"
            f"До уровня {next_lvl} ({next_name}): "
            f"<b>{info['needed'] - info['progress']} XP</b>"
        )

    text = (
        f"⭐ <b>Твой уровень</b>\n\n"
        f"{info['name']}\n"
        f"Уровень <b>{info['level']}</b> из {len(LEVELS)}\n\n"
        f"{progress_text}\n\n"
        f"🏅 Достижений: <b>{len(earned)}</b> из {len(ACHIEVEMENTS)}\n"
        f"⚡ Всего XP: <b>{xp}</b>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏅 Мои достижения", callback_data="achievements")],
        [InlineKeyboardButton(text="📊 Сравнение с прошлым", callback_data="compare_months")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])

    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=kb)
            await event.answer()
        else:
            await msg.answer(text, reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer(text, reply_markup=kb)

# ДОСТИЖЕНИЯ
@router.message(Command("achievements"))
@router.callback_query(F.data == "achievements")
async def show_achievements(event) -> None:
    await init_gamification_tables()
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    earned = set(await get_earned_achievements(user_id))
    lines  = [f"🏅 <b>Достижения ({len(earned)}/{len(ACHIEVEMENTS)})</b>\n"]

    # Сначала полученные, потом заблокированные
    for ach_id, ach in ACHIEVEMENTS.items():
        if ach_id in earned:
            lines.append(
                f"{ach['icon']} <b>{ach['title']}</b> +{ach['xp']} XP\n"
                f"   ✅ {ach['desc']}"
            )
        else:
            lines.append(
                f"🔒 <b>{ach['title']}</b>\n"
                f"   <i>{ach['desc']}</i>"
            )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Мой уровень",  callback_data="my_level")],
        [InlineKeyboardButton(text="🏠 Меню",         callback_data="main_menu")],
    ])

    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text("\n".join(lines), reply_markup=kb)
            await event.answer()
        else:
            await msg.answer("\n".join(lines), reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer("\n".join(lines), reply_markup=kb)


# СРАВНЕНИЕ С ПРОШЛЫМ МЕСЯЦЕМ
async def _get_month_data(user_id: int, year: int, month: int) -> dict:
    month_str = f"{year}-{month:02d}"
    async with get_db() as db:
        totals = await (await db.execute(
            """
            SELECT
                SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS expenses,
                SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS income,
                COUNT(CASE WHEN is_income=0 THEN 1 END)           AS expense_count
            FROM transactions
            WHERE user_id=? AND strftime('%Y-%m', txn_date)=?
            """,
            (user_id, month_str)
        )).fetchone()

        # По категориям
        cats = await (await db.execute(
            """
            SELECT c.name, c.icon, SUM(t.amount) AS total
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id=? AND t.is_income=0
              AND strftime('%Y-%m', t.txn_date)=?
            GROUP BY t.category_id
            ORDER BY total DESC
            LIMIT 5
            """,
            (user_id, month_str)
        )).fetchall()

    return {
        "expenses":      totals["expenses"] or 0.0,
        "income":        totals["income"]   or 0.0,
        "expense_count": totals["expense_count"] or 0,
        "balance":       (totals["income"] or 0.0) - (totals["expenses"] or 0.0),
        "categories":    [dict(r) for r in cats],
    }


@router.message(Command("compare"))
@router.callback_query(F.data == "compare_months")
async def show_comparison(event) -> None:
    msg     = event if isinstance(event, Message) else event.message
    user_id = event.from_user.id

    now     = datetime.now()
    cy, cm  = now.year, now.month

    # Прошлый месяц
    if cm == 1:
        py, pm = cy - 1, 12
    else:
        py, pm = cy, cm - 1

    MONTH_NAMES = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]

    curr = await _get_month_data(user_id, cy, cm)
    prev = await _get_month_data(user_id, py, pm)

    if prev["expenses"] == 0 and prev["income"] == 0:
        text = (
            f"📊 <b>Сравнение месяцев</b>\n\n"
            f"За {MONTH_NAMES[pm]} данных нет.\n"
            f"Сравнение будет доступно в следующем месяце!"
        )
        if isinstance(event, CallbackQuery):
            await event.message.edit_text(text, reply_markup=main_menu_kb())
            await event.answer()
        else:
            await msg.answer(text, reply_markup=main_menu_kb())
        return

    def _diff(curr_val: float, prev_val: float) -> str:
        if prev_val == 0:
            return "🆕 новое"
        diff = curr_val - prev_val
        pct  = diff / prev_val * 100
        if diff > 0:
            return f"📈 +{fmt_amount(diff)} (+{pct:.0f}%)"
        elif diff < 0:
            return f"📉 {fmt_amount(diff)} ({pct:.0f}%)"
        else:
            return "➡️ без изменений"

    def _verdict(curr_val: float, prev_val: float, lower_is_better: bool = True) -> str:
        if prev_val == 0:
            return ""
        diff = curr_val - prev_val
        if lower_is_better:
            return "✅" if diff <= 0 else "⚠️"
        else:
            return "✅" if diff >= 0 else "⚠️"

    lines = [
        f"📊 <b>Сравнение: {MONTH_NAMES[pm]} → {MONTH_NAMES[cm]}</b>\n",

        f"<b>💸 Расходы:</b>",
        f"  {MONTH_NAMES[pm]}: <b>{fmt_amount(prev['expenses'])}</b>",
        f"  {MONTH_NAMES[cm]}: <b>{fmt_amount(curr['expenses'])}</b>",
        f"  {_verdict(curr['expenses'], prev['expenses'])} {_diff(curr['expenses'], prev['expenses'])}\n",

        f"<b>💚 Доходы:</b>",
        f"  {MONTH_NAMES[pm]}: <b>{fmt_amount(prev['income'])}</b>",
        f"  {MONTH_NAMES[cm]}: <b>{fmt_amount(curr['income'])}</b>",
        f"  {_verdict(curr['income'], prev['income'], lower_is_better=False)} {_diff(curr['income'], prev['income'])}\n",

        f"<b>📊 Баланс:</b>",
        f"  {MONTH_NAMES[pm]}: <b>{fmt_amount(prev['balance'])}</b>",
        f"  {MONTH_NAMES[cm]}: <b>{fmt_amount(curr['balance'])}</b>",
        f"  {_verdict(curr['balance'], prev['balance'], lower_is_better=False)} {_diff(curr['balance'], prev['balance'])}\n",
    ]

    # Сравнение по категориям
    if curr["categories"] and prev["categories"]:
        lines.append("<b>🗂 Топ расходов по категориям:</b>")
        prev_cat = {r["name"]: r["total"] for r in prev["categories"]}
        for cat in curr["categories"]:
            name   = cat["name"] or "—"
            icon   = cat["icon"] or "💸"
            prev_v = prev_cat.get(name, 0)
            curr_v = cat["total"]
            v      = _verdict(curr_v, prev_v)
            d      = _diff(curr_v, prev_v) if prev_v > 0 else ""
            lines.append(f"  {icon} {name}: <b>{fmt_amount(curr_v)}</b> {v} {d}")

    # Итоговый вывод
    lines.append("")
    if curr["expenses"] < prev["expenses"] and prev["expenses"] > 0:
        saved = prev["expenses"] - curr["expenses"]
        lines.append(f"🎉 <b>Молодец!</b> Потратил на <b>{fmt_amount(saved)}</b> меньше чем в прошлом месяце!")
    elif curr["expenses"] > prev["expenses"] and prev["expenses"] > 0:
        overspent = curr["expenses"] - prev["expenses"]
        lines.append(f"⚠️ Расходы выросли на <b>{fmt_amount(overspent)}</b> по сравнению с прошлым месяцем.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⭐ Мой уровень",   callback_data="my_level")],
        [InlineKeyboardButton(text="📊 Отчёты",         callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Меню",           callback_data="main_menu")],
    ])

    try:
        if isinstance(event, CallbackQuery):
            await event.message.edit_text("\n".join(lines), reply_markup=kb)
            await event.answer()
        else:
            await msg.answer("\n".join(lines), reply_markup=kb)
    except TelegramBadRequest:
        await msg.answer("\n".join(lines), reply_markup=kb)


# УВЕДОМЛЕНИЕ О НОВОМ ДОСТИЖЕНИИ (вызывается из других хэндлеров)
async def notify_achievements(message: Message, new_achievements: list[dict]) -> None:
    """Отправляет красивое уведомление о полученных достижениях."""
    if not new_achievements:
        return
    for ach in new_achievements:
        await message.answer(
            f"🏅 <b>Новое достижение!</b>\n\n"
            f"{ach['icon']} <b>{ach['title']}</b>\n"
            f"📝 {ach['desc']}\n"
            f"⚡ +{ach['xp']} XP"
        )