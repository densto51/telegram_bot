"""keyboards/main_menu.py — оптимизированное меню с подменю."""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="➖ Расход",         callback_data="add_expense"),
            InlineKeyboardButton(text="➕ Доход",          callback_data="add_income"),
        ],
        [
            InlineKeyboardButton(text="⚡ Быстрый расход", callback_data="quick_expense"),
        ],
        [
            InlineKeyboardButton(text="📊 Финансы",        callback_data="menu_finance"),
            InlineKeyboardButton(text="🏆 Цели",           callback_data="goals"),
        ],
        [
            InlineKeyboardButton(text="⏰ Платежи",        callback_data="menu_payments"),
            InlineKeyboardButton(text="⚙️ Настройки",     callback_data="menu_settings"),
        ],
    ])


def finance_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Отчёты",         callback_data="reports"),
            InlineKeyboardButton(text="📊 Сравнение",      callback_data="compare_months"),
        ],
        [
            InlineKeyboardButton(text="🎯 Бюджет",         callback_data="budget"),
            InlineKeyboardButton(text="📥 Excel",          callback_data="menu_export"),
        ],
        [
            InlineKeyboardButton(text="👤 Статистика",     callback_data="stats"),
            InlineKeyboardButton(text="🏅 Достижения",     callback_data="achievements"),
        ],
        [InlineKeyboardButton(text="◀ Назад",              callback_data="main_menu")],
    ])


def payments_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏰ Напоминания",    callback_data="reminders"),
            InlineKeyboardButton(text="🔍 Паттерны",       callback_data="patterns"),
        ],
        [InlineKeyboardButton(text="◀ Назад",              callback_data="main_menu")],
    ])


def settings_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🗂 Категории",      callback_data="categories"),
            InlineKeyboardButton(text="❓ Помощь",         callback_data="help"),
        ],
        [InlineKeyboardButton(text="◀ Назад",              callback_data="main_menu")],
    ])


def export_menu_kb() -> InlineKeyboardMarkup:
    from datetime import datetime
    now = datetime.now()
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"📥 За {now.month:02d}.{now.year}",
                callback_data=f"export_month:{now.year}:{now.month}"
            ),
            InlineKeyboardButton(
                text=f"📥 За {now.year} год",
                callback_data=f"export_year:{now.year}"
            ),
        ],
        [InlineKeyboardButton(text="◀ Назад",              callback_data="menu_finance")],
    ])


def help_text() -> str:
    return (
        "❓ <b>Справка по боту</b>\n\n"
        "<b>Быстрый ввод расходов:</b>\n"
        "Просто напиши:\n"
        "  <code>кофе 150</code>\n"
        "  <code>обед 350 в кафе</code>\n\n"
        "<b>Команды:</b>\n"
        "  /start        — главное меню с балансом\n"
        "  /expense      — записать расход\n"
        "  /income       — записать доход\n"
        "  /quick        — быстрый расход\n"
        "  /stats        — статистика\n"
        "  /achievements — достижения\n"
        "  /compare      — сравнение месяцев\n"
        "  /goals        — финансовые цели\n"
        "  /patterns     — регулярные расходы\n"
        "  /budget       — бюджет\n"
        "  /report       — отчёты\n"
        "  /export       — скачать Excel\n"
        "  /reminders    — напоминания\n"
        "  /categories   — категории\n\n"
        "<b>Удаление:</b> <code>/delN</code>"
    )