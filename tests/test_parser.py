"""
tests/test_parser.py — юнит-тесты для парсера свободного текста.

Запуск:
    pip install pytest
    pytest tests/ -v
"""

import pytest
from utils.parser import parse_expense_text


# ─── Позитивные тесты ────────────────────────────────────────────────────────

@pytest.mark.parametrize("text, expected_amount, expected_note", [
    # Базовые форматы
    ("кофе 150",           150.0,    "кофе"),
    ("150 кофе",           150.0,    "кофе"),
    ("обед 350.50",        350.5,    "обед"),
    ("350,50 обед",        350.5,    "обед"),
    # Разделители тысяч
    ("1500 такси",         1500.0,   "такси"),
    ("1 500 такси",        1500.0,   "такси"),
    ("1 500,50 такси",     1500.5,   "такси"),
    # Слова-стоп
    ("потратил 500 руб",   500.0,    None),
    ("купил 250 рублей",   250.0,    None),
    ("заплатил 3000 сом",  3000.0,   None),
    # Длинные описания
    ("обед в кафе 550",    550.0,    "обед в кафе"),
    ("поездка на такси 200 рублей", 200.0, "поездка на такси"),
    # Только число
    ("1000",               1000.0,   None),
])
def test_parse_valid(text, expected_amount, expected_note):
    result = parse_expense_text(text)
    assert result is not None, f"Ожидался результат для: {text!r}"
    assert result["amount"] == expected_amount, (
        f"Для {text!r}: ожидалось {expected_amount}, получено {result['amount']}"
    )
    assert result["note"] == expected_note, (
        f"Для {text!r}: ожидалась заметка {expected_note!r}, получено {result['note']!r}"
    )


# ─── Негативные тесты

@pytest.mark.parametrize("text", [
    "",
    "   ",
    "кофе",
    "купил что-то",
    "привет как дела",
    "-150",           # отрицательное число
    "0",              # ноль
])
def test_parse_invalid(text):
    result = parse_expense_text(text)
    assert result is None, f"Ожидался None для: {text!r}, получено: {result}"


# ─── Тесты форматирования ────────────────────────────────────────────────────

def test_fmt_amount():
    from utils.formatters import fmt_amount
    assert fmt_amount(1500.0, "RUB") == "1 500 ₽"
    assert fmt_amount(1500.5, "RUB") == "1 500.50 ₽"
    assert fmt_amount(0.0, "KGS") == "0 с"


def test_fmt_bar():
    from utils.formatters import fmt_bar
    assert fmt_bar(5, 10, 10) == "█████░░░░░"
    assert fmt_bar(10, 10, 10) == "██████████"
    assert fmt_bar(0, 10, 10) == "░░░░░░░░░░"


def test_fmt_progress_bar():
    from utils.formatters import fmt_progress_bar
    result_green  = fmt_progress_bar(500, 1000)
    result_yellow = fmt_progress_bar(900, 1000)
    result_red    = fmt_progress_bar(1100, 1000)
    assert "🟢" in result_green
    assert "🟡" in result_yellow
    assert "🔴" in result_red
