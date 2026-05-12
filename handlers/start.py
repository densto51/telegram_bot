"""handlers/start.py — главное меню с балансом и подменю."""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.exceptions import TelegramBadRequest

from database.db import ensure_user, get_db
from keyboards.main_menu import (
    main_menu_kb, help_text,
    finance_menu_kb, payments_menu_kb,
    settings_menu_kb, export_menu_kb,
)
from utils.formatters import fmt_amount

router = Router(name="start")


# Баланс

async def _get_balance(user_id: int) -> dict:
    from datetime import datetime
    month_str = datetime.now().strftime("%Y-%m")
    async with get_db() as db:
        total = await (await db.execute(
            """
            SELECT
                SUM(CASE WHEN is_income=1 THEN amount ELSE -amount END) AS balance,
                SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END)       AS total_expense,
                SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END)       AS total_income
            FROM transactions WHERE user_id=?
            """, (user_id,)
        )).fetchone()
        month = await (await db.execute(
            """
            SELECT
                SUM(CASE WHEN is_income=0 THEN amount ELSE 0 END) AS month_expense,
                SUM(CASE WHEN is_income=1 THEN amount ELSE 0 END) AS month_income
            FROM transactions
            WHERE user_id=? AND strftime('%Y-%m', txn_date)=?
            """, (user_id, month_str)
        )).fetchone()
    return {
        "balance":       total["balance"]       or 0.0,
        "total_income":  total["total_income"]  or 0.0,
        "total_expense": total["total_expense"] or 0.0,
        "month_expense": month["month_expense"] or 0.0,
        "month_income":  month["month_income"]  or 0.0,
    }


async def _main_menu_text(user_id: int, name: str) -> str:
    b = await _get_balance(user_id)
    balance  = b["balance"]
    bal_icon = "📈" if balance >= 0 else "📉"
    bal_sign = "+" if balance >= 0 else ""
    from datetime import datetime
    month_names = ["","Январь","Февраль","Март","Апрель","Май","Июнь",
                   "Июль","Август","Сентябрь","Октябрь","Ноябрь","Декабрь"]
    now = datetime.now()
    return (
        f"Привет,👋 <b>{name}</b>\n\n"
        f"{'─' * 26}\n"
        f"{bal_icon} <b>Баланс: {bal_sign}{fmt_amount(balance)}</b>\n"
        f"{'─' * 26}\n\n"
        f"<b>{month_names[now.month]} {now.year}:</b>\n"
        f"  💚 Доходы:  <b>{fmt_amount(b['month_income'])}</b>\n"
        f"  💸 Расходы: <b>{fmt_amount(b['month_expense'])}</b>\n\n"
        f"Выбери действие 👇"
    )


async def _safe_to_main(callback: CallbackQuery, text: str) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb())
    except TelegramBadRequest:
        await callback.message.answer(text, reply_markup=main_menu_kb())


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await ensure_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    name = message.from_user.first_name or "друг"
    text = await _main_menu_text(message.from_user.id, name)
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(help_text(), reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    name = message.from_user.first_name or "друг"
    text = await _main_menu_text(message.from_user.id, name)
    await message.answer(text, reply_markup=main_menu_kb())


# ── Главное меню (callback) ───────────────────────────────────────────────────

@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    name = callback.from_user.first_name or "друг"
    text = await _main_menu_text(callback.from_user.id, name)
    await _safe_to_main(callback, text)
    await callback.answer()


@router.callback_query(F.data == "cancel_fsm")
async def cb_cancel(callback: CallbackQuery) -> None:
    name = callback.from_user.first_name or "друг"
    text = await _main_menu_text(callback.from_user.id, name)
    await _safe_to_main(callback, text)
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(help_text(), reply_markup=main_menu_kb())
    except TelegramBadRequest:
        await callback.message.answer(help_text(), reply_markup=main_menu_kb())
    await callback.answer()


#  Подменю

@router.callback_query(F.data == "menu_finance")
async def cb_menu_finance(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            "📊 <b>Финансы</b>\n\nВыбери раздел:",
            reply_markup=finance_menu_kb()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "📊 <b>Финансы</b>\n\nВыбери раздел:",
            reply_markup=finance_menu_kb()
        )
    await callback.answer()


@router.callback_query(F.data == "menu_payments")
async def cb_menu_payments(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            "⏰ <b>Платежи</b>\n\nВыбери раздел:",
            reply_markup=payments_menu_kb()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "⏰ <b>Платежи</b>\n\nВыбери раздел:",
            reply_markup=payments_menu_kb()
        )
    await callback.answer()


@router.callback_query(F.data == "menu_settings")
async def cb_menu_settings(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            "⚙️ <b>Настройки</b>\n\nВыбери раздел:",
            reply_markup=settings_menu_kb()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "⚙️ <b>Настройки</b>\n\nВыбери раздел:",
            reply_markup=settings_menu_kb()
        )
    await callback.answer()


@router.callback_query(F.data == "menu_export")
async def cb_menu_export(callback: CallbackQuery) -> None:
    try:
        await callback.message.edit_text(
            "📥 <b>Экспорт в Excel</b>\n\nВыбери период:",
            reply_markup=export_menu_kb()
        )
    except TelegramBadRequest:
        await callback.message.answer(
            "📥 <b>Экспорт в Excel</b>\n\nВыбери период:",
            reply_markup=export_menu_kb()
        )
    await callback.answer()
