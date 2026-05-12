"""keyboards/reports.py — с кнопками экспорта в Excel"""

from datetime import datetime
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils.formatters import MONTH_NAMES


def reports_menu_kb() -> InlineKeyboardMarkup:
    now   = datetime.now()
    y, m  = now.year, now.month
    prev_m = m - 1 if m > 1 else 12
    prev_y = y if m > 1 else y - 1
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"📅 {MONTH_NAMES[m-1]} {y}",  callback_data=f"report_month:{y}:{m}"),
            InlineKeyboardButton(text=f"📅 {MONTH_NAMES[prev_m-1]}", callback_data=f"report_month:{prev_y}:{prev_m}"),
        ],
        [
            InlineKeyboardButton(text="📅 7 дней",   callback_data="report_week"),
            InlineKeyboardButton(text=f"📅 Год {y}", callback_data=f"report_year:{y}"),
        ],
        [
            InlineKeyboardButton(text="📋 Последние операции", callback_data="report_last"),
        ],
        [
            InlineKeyboardButton(text=f"📥 Excel за {m:02d}.{y}", callback_data=f"export_month:{y}:{m}"),
            InlineKeyboardButton(text=f"📥 Excel за {y} год",     callback_data=f"export_year:{y}"),
        ],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu")],
    ])


def month_nav_kb(year: int, month: int) -> InlineKeyboardMarkup:
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"◀ {MONTH_NAMES[prev_m-1]}", callback_data=f"report_month:{prev_y}:{prev_m}"),
            InlineKeyboardButton(text=f"{MONTH_NAMES[next_m-1]} ▶", callback_data=f"report_month:{next_y}:{next_m}"),
        ],
        [InlineKeyboardButton(text="📊 Все отчёты", callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])


def month_nav_with_chart_kb(year: int, month: int) -> InlineKeyboardMarkup:
    prev_m = month - 1 if month > 1 else 12
    prev_y = year if month > 1 else year - 1
    next_m = month + 1 if month < 12 else 1
    next_y = year if month < 12 else year + 1
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"◀ {MONTH_NAMES[prev_m-1]}", callback_data=f"report_month:{prev_y}:{prev_m}"),
            InlineKeyboardButton(text=f"{MONTH_NAMES[next_m-1]} ▶", callback_data=f"report_month:{next_y}:{next_m}"),
        ],
        [
            InlineKeyboardButton(text="🥧 Круговая",   callback_data=f"chart_month_pie:{year}:{month}"),
            InlineKeyboardButton(text="📊 Столбчатая", callback_data=f"chart_month_bar:{year}:{month}"),
            InlineKeyboardButton(text="📉 Топ катег.", callback_data=f"chart_hbar:{year}:{month}"),
        ],
        [
            InlineKeyboardButton(text=f"📥 Скачать Excel", callback_data=f"export_month:{year}:{month}"),
        ],
        [InlineKeyboardButton(text="📊 Все отчёты", callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])


def year_nav_kb(year: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"◀ {year-1}", callback_data=f"report_year:{year-1}"),
            InlineKeyboardButton(text=f"{year+1} ▶", callback_data=f"report_year:{year+1}"),
        ],
        [InlineKeyboardButton(text="📊 Все отчёты", callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])


def year_nav_with_chart_kb(year: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"◀ {year-1}", callback_data=f"report_year:{year-1}"),
            InlineKeyboardButton(text=f"{year+1} ▶", callback_data=f"report_year:{year+1}"),
        ],
        [
            InlineKeyboardButton(text="📈 График за год",   callback_data=f"chart_year:{year}"),
            InlineKeyboardButton(text="📥 Скачать Excel",   callback_data=f"export_year:{year}"),
        ],
        [InlineKeyboardButton(text="📊 Все отчёты", callback_data="reports")],
        [InlineKeyboardButton(text="🏠 Меню",        callback_data="main_menu")],
    ])
