"""keyboards/categories.py"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def categories_kb(categories: list[dict], prefix: str) -> InlineKeyboardMarkup:
    """Inline-клавиатура для выбора категории. 2 кнопки в ряд."""
    buttons = []
    row = []
    for i, cat in enumerate(categories):
        row.append(
            InlineKeyboardButton(
                text=f"{cat['icon']} {cat['name']}",
                callback_data=f"{prefix}:{cat['id']}",
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=f"{prefix}:skip"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def manage_categories_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить категорию", callback_data="add_category")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])
