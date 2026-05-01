"""keyboards/reminders.py"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def reminders_list_kb(reminders: list[dict]) -> InlineKeyboardMarkup:
    """
    Список напоминаний.
    Каждое напоминание — две кнопки: просмотр и удаление.
    """
    rows = []
    for r in reminders:
        rows.append([
            InlineKeyboardButton(
                text=f"🔔 {r['title']}",
                callback_data=f"view_reminder:{r['id']}",
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"del_reminder:{r['id']}",
            ),
        ])
    rows += [
        [InlineKeyboardButton(text="➕ Добавить напоминание", callback_data="add_reminder")],
        [InlineKeyboardButton(text="🏠 Главное меню",         callback_data="main_menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reminder_detail_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """Кнопки при просмотре одного напоминания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить",           callback_data=f"del_reminder:{reminder_id}")],
        [InlineKeyboardButton(text="◀ Назад к списку",     callback_data="reminders")],
        [InlineKeyboardButton(text="🏠 Главное меню",      callback_data="main_menu")],
    ])


def repeat_kb() -> InlineKeyboardMarkup:
    """Выбор типа повтора + отмена."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Разово",       callback_data="repeat:none"),
            InlineKeyboardButton(text="Ежедневно",    callback_data="repeat:daily"),
        ],
        [
            InlineKeyboardButton(text="Еженедельно",  callback_data="repeat:weekly"),
            InlineKeyboardButton(text="Ежемесячно",   callback_data="repeat:monthly"),
        ],
        [InlineKeyboardButton(text="🏠 Отмена — вернуться в меню", callback_data="cancel_fsm")],
    ])


def after_create_kb(reminder_id: int) -> InlineKeyboardMarkup:
    """Кнопки после успешного создания напоминания."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить это напоминание", callback_data=f"del_reminder:{reminder_id}")],
        [InlineKeyboardButton(text="⏰ Все напоминания",         callback_data="reminders")],
        [InlineKeyboardButton(text="🏠 Главное меню",            callback_data="main_menu")],
    ])