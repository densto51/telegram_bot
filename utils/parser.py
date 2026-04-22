"""
utils/parser.py — парсинг свободного текста для извлечения суммы и заметки.

Поддерживаемые форматы:
  «кофе 150»          → amount=150, note='кофе'
  «150 кофе»          → amount=150, note='кофе'
  «потратил 350 руб на обед» → amount=350, note='потратил на обед'
  «1 500,50»          → amount=1500.5
  «1500.50 такси»     → amount=1500.5, note='такси'
"""

import re
from typing import TypedDict


class ParsedExpense(TypedDict):
    amount: float
    note: str | None


# Число: 1500 | 1500.50 | 1 500 | 1,500.50 | 1500,50
_NUM_RE = re.compile(
    r"""
    (?<!\d)                       # не предшествует цифра
    (?P<amount>
        \d{1,3}(?:[\s\u00a0]\d{3})*   # 1 500  или  1 500 000
        (?:[.,]\d{1,2})?              # опциональная дробная часть
        |
        \d+(?:[.,]\d{1,2})?           # простое число
    )
    (?!\d)                        # не следует цифра
    """,
    re.VERBOSE,
)

# Слова-заглушки которые не нужны в заметке
_STOP_WORDS = frozenset(
    "руб рублей руб. сом сомов тг тенге $ € usd eur kgs kzt "
    "потратил потратила купил купила заплатил заплатила".split()
)


def _clean_note(text: str) -> str | None:
    words = [w for w in text.split() if w.lower() not in _STOP_WORDS]
    note = " ".join(words).strip(" ,-.")
    return note if note else None


def parse_expense_text(text: str) -> ParsedExpense | None:
    """
    Извлекает сумму и заметку из произвольного текста.
    Возвращает None если сумма не найдена.
    """
    text = text.strip()
    if not text:
        return None

    match = _NUM_RE.search(text)
    if not match:
        return None

    raw_amount = match.group("amount")
    # Нормализуем: убираем пробелы-разделители, меняем запятую на точку
    raw_amount = re.sub(r"[\s\u00a0]", "", raw_amount)
    # Если есть запятая — это десятичный разделитель
    if "," in raw_amount and "." not in raw_amount:
        raw_amount = raw_amount.replace(",", ".")
    elif "," in raw_amount:
        raw_amount = raw_amount.replace(",", "")

    try:
        amount = float(raw_amount)
    except ValueError:
        return None

    if amount <= 0:
        return None

    # Вырезаем число из текста — остаток = заметка
    remainder = (text[: match.start()] + text[match.end() :]).strip()
    note = _clean_note(remainder)

    return ParsedExpense(amount=amount, note=note)
