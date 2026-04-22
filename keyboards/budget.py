"""keyboards/budget.py"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def budget_list_kb(budgets: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for b in budgets:
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 {b['icon']} {b['name']}",
                callback_data=f"budget_del:{b['id']}",
            )
        ])
    rows += [
        [InlineKeyboardButton(text="➕ Добавить бюджет",    callback_data="budget_add")],
        [InlineKeyboardButton(text="🌍 Общий лимит",        callback_data="set_global_limit")],
        [InlineKeyboardButton(text="🏠 Главное меню",       callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
