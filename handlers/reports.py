"""
handlers/reports.py — финансовые отчёты + графики matplotlib.
"""

import json
import logging
from datetime import datetime

from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, BufferedInputFile
from aiogram.filters import Command
from redis.asyncio import Redis

from config import settings
from database.queries import (
    get_monthly_summary,
    get_yearly_summary,
    get_last_transactions,
    get_weekly_expenses,
)
from keyboards.main_menu import main_menu_kb
from keyboards.reports import reports_menu_kb, month_nav_kb, month_nav_with_chart_kb, year_nav_kb
from utils.formatters import fmt_amount, fmt_bar, MONTH_NAMES
from services.charts import pie_chart, bar_monthly, line_yearly, hbar_categories

logger = logging.getLogger(__name__)
router = Router(name="reports")


def _cache_key(user_id: int, report_type: str, *args) -> str:
    return f"report:{user_id}:{report_type}:{':'.join(str(a) for a in args)}"


async def _get_cached(redis: Redis, key: str):
    try:
        val = await redis.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def _set_cached(redis: Redis, key: str, data) -> None:
    try:
        await redis.setex(key, settings.REPORT_CACHE_TTL,
                          json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


# ─── Меню отчётов ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "reports")
async def cb_reports(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📊 <b>Финансовые отчёты</b>\n\nВыбери тип отчёта:",
        reply_markup=reports_menu_kb(),
    )
    await callback.answer()


@router.message(Command("report"))
async def cmd_report(message: Message) -> None:
    await message.answer("📊 <b>Отчёты</b>:", reply_markup=reports_menu_kb())


# ─── Месячный отчёт ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("report_month:"))
async def cb_monthly_report(callback: CallbackQuery, redis: Redis) -> None:
    parts      = callback.data.split(":")
    year, month = int(parts[1]), int(parts[2])
    user_id    = callback.from_user.id

    key  = _cache_key(user_id, "month", year, month)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_monthly_summary(user_id, year, month)
        await _set_cached(redis, key, data)

    month_name = MONTH_NAMES[month - 1]
    total_exp  = data["total_expenses"]
    total_inc  = data["total_income"]
    balance    = data["balance"]

    lines = [f"📅 <b>Отчёт за {month_name} {year}</b>\n"]
    lines.append(f"💚 Доходы:  <b>{fmt_amount(total_inc)}</b>")
    lines.append(f"💸 Расходы: <b>{fmt_amount(total_exp)}</b>")
    lines.append(f"{'📈' if balance >= 0 else '📉'} Баланс:   <b>{fmt_amount(balance)}</b>\n")

    if data["expenses_by_category"]:
        lines.append("📊 <b>Расходы по категориям:</b>")
        max_val = max(r["total"] for r in data["expenses_by_category"])
        for row in data["expenses_by_category"]:
            pct  = row["total"] / total_exp * 100 if total_exp else 0
            bar  = fmt_bar(row["total"], max_val, width=8)
            icon = row.get("icon") or "💰"
            lines.append(
                f"  {icon} {row['name']}\n"
                f"  {bar} <b>{fmt_amount(row['total'])}</b> ({pct:.0f}%)"
            )

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=month_nav_with_chart_kb(year, month),
    )
    await callback.answer()


# ─── График за месяц (круговая + столбчатая) ─────────────────────────────────

@router.callback_query(F.data.startswith("chart_month_pie:"))
async def cb_chart_pie(callback: CallbackQuery, redis: Redis) -> None:
    parts       = callback.data.split(":")
    year, month = int(parts[1]), int(parts[2])
    user_id     = callback.from_user.id

    await callback.answer("⏳ Генерирую график...")

    key  = _cache_key(user_id, "month", year, month)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_monthly_summary(user_id, year, month)
        await _set_cached(redis, key, data)

    if not data["expenses_by_category"]:
        await callback.message.answer("📭 Нет данных для графика.")
        return

    from utils.formatters import MONTH_NAMES
    img = pie_chart(
        data["expenses_by_category"],
        title=f"Расходы — {MONTH_NAMES[month-1]} {year}",
    )
    await callback.message.answer_photo(
        BufferedInputFile(img, filename="pie.png"),
        caption=f"🥧 <b>Круговая диаграмма — {MONTH_NAMES[month-1]} {year}</b>",
        reply_markup=month_nav_with_chart_kb(year, month),
    )


@router.callback_query(F.data.startswith("chart_month_bar:"))
async def cb_chart_bar(callback: CallbackQuery, redis: Redis) -> None:
    parts       = callback.data.split(":")
    year, month = int(parts[1]), int(parts[2])
    user_id     = callback.from_user.id

    await callback.answer("⏳ Генерирую график...")

    key  = _cache_key(user_id, "month", year, month)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_monthly_summary(user_id, year, month)
        await _set_cached(redis, key, data)

    if not data["expenses_by_category"]:
        await callback.message.answer("📭 Нет данных для графика.")
        return

    img = bar_monthly(data, year, month)
    from utils.formatters import MONTH_NAMES
    await callback.message.answer_photo(
        BufferedInputFile(img, filename="bar.png"),
        caption=f"📊 <b>Столбчатый график — {MONTH_NAMES[month-1]} {year}</b>",
        reply_markup=month_nav_with_chart_kb(year, month),
    )


# ─── Годовой отчёт + линейный график ─────────────────────────────────────────

@router.callback_query(F.data.startswith("report_year:"))
async def cb_yearly_report(callback: CallbackQuery, redis: Redis) -> None:
    year    = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    key  = _cache_key(user_id, "year", year)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_yearly_summary(user_id, year)
        await _set_cached(redis, key, data)

    if not data:
        await callback.message.edit_text(
            f"📭 За {year} год данных нет.", reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    lines     = [f"📅 <b>Годовой отчёт {year}</b>\n"]
    total_exp = sum(r["expenses"] for r in data)
    total_inc = sum(r["income"]   for r in data)
    max_exp   = max((r["expenses"] for r in data), default=1)

    for row in data:
        m   = int(row["month"])
        bar = fmt_bar(row["expenses"], max_exp, width=10)
        lines.append(
            f"{MONTH_NAMES[m-1][:3]}: {bar} "
            f"<b>{fmt_amount(row['expenses'])}</b> / 💚{fmt_amount(row['income'])}"
        )

    lines.append(f"\n💸 Итого расходов: <b>{fmt_amount(total_exp)}</b>")
    lines.append(f"💚 Итого доходов:  <b>{fmt_amount(total_inc)}</b>")
    lines.append(
        f"{'📈' if total_inc >= total_exp else '📉'} Баланс: <b>{fmt_amount(total_inc - total_exp)}</b>"
    )

    from keyboards.reports import year_nav_with_chart_kb
    await callback.message.edit_text("\n".join(lines), reply_markup=year_nav_with_chart_kb(year))
    await callback.answer()


@router.callback_query(F.data.startswith("chart_year:"))
async def cb_chart_year(callback: CallbackQuery, redis: Redis) -> None:
    year    = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    await callback.answer("⏳ Генерирую график...")

    key  = _cache_key(user_id, "year", year)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_yearly_summary(user_id, year)
        await _set_cached(redis, key, data)

    if not data:
        await callback.message.answer("📭 Нет данных для графика.")
        return

    img = line_yearly(data, year)
    await callback.message.answer_photo(
        BufferedInputFile(img, filename="year.png"),
        caption=f"📈 <b>Доходы и расходы за {year} год</b>",
        reply_markup=year_nav_with_chart_kb(year),
    )


# ─── Топ категорий (горизонтальные бары) ──────────────────────────────────────

@router.callback_query(F.data.startswith("chart_hbar:"))
async def cb_chart_hbar(callback: CallbackQuery, redis: Redis) -> None:
    parts       = callback.data.split(":")
    year, month = int(parts[1]), int(parts[2])
    user_id     = callback.from_user.id

    await callback.answer("⏳ Генерирую график...")

    key  = _cache_key(user_id, "month", year, month)
    data = await _get_cached(redis, key)
    if not data:
        data = await get_monthly_summary(user_id, year, month)
        await _set_cached(redis, key, data)

    if not data["expenses_by_category"]:
        await callback.message.answer("📭 Нет данных для графика.")
        return

    from utils.formatters import MONTH_NAMES
    img = hbar_categories(
        data["expenses_by_category"],
        title=f"Топ категорий — {MONTH_NAMES[month-1]} {year}",
    )
    await callback.message.answer_photo(
        BufferedInputFile(img, filename="hbar.png"),
        caption=f"📉 <b>Топ категорий — {MONTH_NAMES[month-1]} {year}</b>",
        reply_markup=month_nav_with_chart_kb(year, month),
    )


# ─── Последние операции ───────────────────────────────────────────────────────

@router.callback_query(F.data == "report_last")
async def cb_last_txns(callback: CallbackQuery) -> None:
    txns = await get_last_transactions(callback.from_user.id, limit=15)
    if not txns:
        await callback.message.edit_text("📭 Операций пока нет.", reply_markup=main_menu_kb())
        await callback.answer()
        return

    lines = ["📋 <b>Последние 15 операций:</b>\n"]
    for t in txns:
        icon     = t.get("cat_icon") or ("💚" if t["is_income"] else "💸")
        note     = f" — {t['note']}" if t["note"] else ""
        cat      = t.get("category") or "Без категории"
        src_icon = "🎙" if t["source"] == "voice" else ""
        lines.append(
            f"{src_icon}{icon} <b>{fmt_amount(t['amount'])}</b>  {cat}{note}\n"
            f"   <i>{t['txn_date']}</i>  /del{t['id']}"
        )

    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu_kb())
    await callback.answer()


@router.message(F.text.regexp(r"^/del(\d+)$"))
async def cmd_delete_txn(message: Message) -> None:
    import re
    from database.queries import delete_transaction
    m      = re.match(r"^/del(\d+)$", message.text)
    txn_id = int(m.group(1))
    ok     = await delete_transaction(txn_id, message.from_user.id)
    await message.answer(
        "🗑 Удалено!" if ok else "❌ Транзакция не найдена.",
        reply_markup=main_menu_kb(),
    )


# ─── Недельный отчёт ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "report_week")
async def cb_weekly_report(callback: CallbackQuery) -> None:
    rows = await get_weekly_expenses(callback.from_user.id)
    if not rows:
        await callback.message.edit_text(
            "📭 За последние 7 дней расходов нет.", reply_markup=main_menu_kb()
        )
        await callback.answer()
        return

    by_date: dict[str, list] = {}
    for r in rows:
        by_date.setdefault(r["txn_date"], []).append(r)

    lines = ["📅 <b>Расходы за 7 дней:</b>\n"]
    total = sum(r["total"] for r in rows)

    for date_str, items in sorted(by_date.items()):
        day_total = sum(i["total"] for i in items)
        lines.append(f"<b>{date_str}</b>  💸 {fmt_amount(day_total)}")
        for item in items:
            icon = item.get("icon") or "💰"
            lines.append(f"  {icon} {item['category']}: {fmt_amount(item['total'])}")

    lines.append(f"\n<b>Итого: {fmt_amount(total)}</b>")
    await callback.message.edit_text("\n".join(lines), reply_markup=main_menu_kb())
    await callback.answer()
