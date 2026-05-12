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


# Структура результата: сумма + заметка
class ParsedExpense(TypedDict):
    amount: float
    note: str | None


# Регулярка для поиска чисел (1500, 1 500, 1500.50, 1,500.50 и т.д.)
_NUM_RE = re.compile(
    r"""
    (?<!\d)                       # перед числом не должно быть цифры
    (?P<amount>
        \d{1,3}(?:[\s\u00a0]\d{3})*   # числа с пробелами: 1 500, 12 000
        (?:[.,]\d{1,2})?              # дробная часть: .50 или ,50
        |
        \d+(?:[.,]\d{1,2})?           # обычные числа: 1500, 1500.50
    )
    (?!\d)                        # после числа не должно быть цифры
    (?:\s*(руб|руб\.|сом|сомов|тг|тенге|usd|eur|\$|€))?  # валюта (опционально)
    """,
    re.VERBOSE | re.IGNORECASE,
)


# Слова, которые не должны попадать в заметку
_STOP_WORDS = frozenset(
    "руб рублей руб. сом сомов тг тенге $ € usd eur kgs kzt "
    "потратил потратила купил купила заплатил заплатила".split()
)


def _normalize_number(num: str) -> str:
    """
    Приводит число к нормальному виду:
    - убирает пробелы
    - приводит запятую к точке (если это десятичный разделитель)
    """
    num = re.sub(r"[\s\u00a0]", "", num)

    # если есть и точка и запятая → запятая это разделитель тысяч
    if "." in num and "," in num:
        num = num.replace(",", "")
    # если только запятая → считаем её десятичной
    elif "," in num:
        num = num.replace(",", ".")

    return num


def _clean_note(text: str) -> str | None:
    """
    Очищает текст от мусора:
    - убирает лишние пробелы
    - удаляет стоп-слова (руб, купил и т.д.)
    """
    text = re.sub(r"\s+", " ", text)  # нормализация пробелов

    words = [
        w for w in text.split()
        if w.lower() not in _STOP_WORDS
    ]

    note = " ".join(words).strip(" ,-.")
    return note or None


def parse_expense_text(text: str) -> ParsedExpense | None:
    """
    Главная функция парсинга:
    - ищет сумму в тексте
    - извлекает её
    - очищает текст → получает заметку
    - возвращает structured данные
    """
    text = text.strip()
    if not text:
        return None

    # ищем все числа в тексте
    matches = list(_NUM_RE.finditer(text))
    if not matches:
        return None

    # берём первое найденное число
    match = matches[0]

    # нормализуем число (убираем пробелы, запятые и т.д.)
    raw_amount = _normalize_number(match.group("amount"))

    try:
        amount = float(raw_amount)
    except ValueError:
        return None

    # защита от нулевых и слишком больших значений
    if amount <= 0 or amount > 1_000_000:
        return None

    # удаляем найденное число из текста
    text_wo_amount = _NUM_RE.sub("", text, count=1)

    # чистим оставшийся текст → получаем заметку
    note = _clean_note(text_wo_amount)

    return ParsedExpense(amount=amount, note=note)
