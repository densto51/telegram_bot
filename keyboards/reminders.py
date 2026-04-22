"""keyboards/reminders.py"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def reminders_list_kb(reminders: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for r in reminders:
        rows.append([
            InlineKeyboardButton(
                text=f"🗑 {r['title']}",
                callback_data=f"del_reminder:{r['id']}",
            )
        ])
    rows += [
        [InlineKeyboardButton(text="➕ Добавить напоминание", callback_data="add_reminder")],
        [InlineKeyboardButton(text="🏠 Главное меню",         callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def repeat_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Разово",    callback_data="repeat:none"),
            InlineKeyboardButton(text="Ежедневно", callback_data="repeat:daily"),
        ],
        [
            InlineKeyboardButton(text="Еженедельно",  callback_data="repeat:weekly"),
            InlineKeyboardButton(text="Ежемесячно",   callback_data="repeat:monthly"),
        ],
    ])
