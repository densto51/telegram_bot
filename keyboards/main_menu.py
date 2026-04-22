"""
keyboards/main_menu.py — главная inline-клавиатура и текст помощи.
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖ Расход",  callback_data="add_expense"),
            InlineKeyboardButton(text="➕ Доход",   callback_data="add_income"),
        ],
        [
            InlineKeyboardButton(text="📊 Отчёты",  callback_data="reports"),
            InlineKeyboardButton(text="🎯 Бюджет",  callback_data="budget"),
        ],
        [
            InlineKeyboardButton(text="⏰ Напоминания", callback_data="reminders"),
            InlineKeyboardButton(text="🗂 Категории",   callback_data="categories"),
        ],
        [
            InlineKeyboardButton(text="❓ Помощь", callback_data="help"),
        ],
    ])


def help_text() -> str:
    return (
        "❓ <b>Справка по боту</b>\n\n"
        "<b>Быстрый ввод расходов:</b>\n"
        "Просто напиши сообщение вида:\n"
        "  <code>кофе 150</code>\n"
        "  <code>обед 350 в кафе</code>\n"
        "  <code>500 такси</code>\n\n"
        "<b>Голосовые сообщения:</b>\n"
        "Отправь голосовое — бот распознает сумму.\n\n"
        "<b>Команды:</b>\n"
        "  /start — главное меню\n"
        "  /expense — записать расход\n"
        "  /income — записать доход\n"
        "  /budget — управление бюджетом\n"
        "  /report — финансовые отчёты\n"
        "  /reminders — напоминания\n"
        "  /categories — категории\n"
        "  /help — эта справка\n\n"
        "<b>Удаление транзакции:</b>\n"
        "В списке последних операций нажми <code>/delN</code>"
    )
