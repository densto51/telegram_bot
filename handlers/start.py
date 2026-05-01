"""
handlers/start.py — /start, /help, главное меню.
"""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.markdown import hbold
from aiogram.exceptions import TelegramBadRequest

from database.db import ensure_user
from keyboards.main_menu import main_menu_kb, help_text

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await ensure_user(
        user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
    )
    name = message.from_user.first_name or "друг"
    text = (
        f"👋 Привет, {hbold(name)}!\n\n"
        "Я — твой <b>личный финансовый ассистент</b>. 💰\n\n"
        "Умею:\n"
        "• 📝 Записывать расходы и доходы текстом\n"
        "• 🎙 Принимать голосовые сообщения\n"
        "• 📊 Строить отчёты по месяцам и годам\n"
        "• 🎯 Следить за бюджетом по категориям\n"
        "• ⏰ Напоминать о предстоящих платежах\n\n"
        "Выбери действие 👇"
    )
    await message.answer(text, reply_markup=main_menu_kb())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(help_text(), reply_markup=main_menu_kb())


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("🏠 Главное меню:", reply_markup=main_menu_kb())


async def _safe_edit_or_send(callback: CallbackQuery, text: str) -> None:
    """
    Пытается отредактировать сообщение.
    Если не получается (фото, стикер, голосовое) — отправляет новое.
    """
    try:
        await callback.message.edit_text(text, reply_markup=main_menu_kb())
    except TelegramBadRequest:
        # Сообщение — фото или медиа, нельзя редактировать текст
        await callback.message.answer(text, reply_markup=main_menu_kb())


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery) -> None:
    await _safe_edit_or_send(callback, "🏠 Главное меню:")
    await callback.answer()


@router.callback_query(F.data == "help")
async def cb_help(callback: CallbackQuery) -> None:
    await _safe_edit_or_send(callback, help_text())
    await callback.answer()


@router.callback_query(F.data == "cancel_fsm")
async def cb_cancel_global(callback: CallbackQuery) -> None:
    """Глобальный обработчик отмены — на случай если локальный не поймал."""
    await _safe_edit_or_send(callback, "🏠 Главное меню:")
    await callback.answer()

