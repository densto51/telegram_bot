"""
utils/formatters.py — форматирование чисел, прогресс-баров, дат.
"""

from datetime import datetime
from config import settings

MONTH_NAMES = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

CURRENCY_SYMBOLS = {
    "KGS": "с",
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "KZT": "₸",
}


def fmt_amount(amount: float, currency: str | None = None) -> str:
    """Форматирует сумму: 1 234.50 ₽"""
    cur = currency or settings.DEFAULT_CURRENCY
    symbol = CURRENCY_SYMBOLS.get(cur, cur)
    if amount == int(amount):
        formatted = f"{int(amount):,}".replace(",", " ")
    else:
        formatted = f"{amount:,.2f}".replace(",", " ")
    return f"{formatted} {symbol}"


def fmt_bar(value: float, max_value: float, width: int = 10) -> str:
    """Текстовый бар: ████░░░░░░"""
    if max_value <= 0:
        return "░" * width
    filled = min(int(value / max_value * width), width)
    return "█" * filled + "░" * (width - filled)


def fmt_progress_bar(spent: float, budget: float, width: int = 10) -> str:
    """Цветной прогресс-бар с учётом превышения."""
    if budget <= 0:
        return "░" * width
    pct = spent / budget
    filled = min(int(pct * width), width)
    empty = width - filled
    bar = "█" * filled + "░" * empty
    if pct >= 1.0:
        return f"🔴 {bar}"
    elif pct >= 0.85:
        return f"🟡 {bar}"
    return f"🟢 {bar}"


def fmt_reminder_dt(dt_str: str) -> str:
    """Форматирует дату напоминания: «25 декабря в 09:00»"""
    try:
        dt = datetime.fromisoformat(dt_str)
        month_gen = [
            "января", "февраля", "марта", "апреля", "мая", "июня",
            "июля", "августа", "сентября", "октября", "ноября", "декабря",
        ]
        return f"{dt.day} {month_gen[dt.month - 1]} в {dt.strftime('%H:%M')}"
    except Exception:
        return dt_str
