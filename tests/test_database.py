"""
tests/test_database.py — интеграционные тесты для БД (in-memory SQLite).
"""

import asyncio
# Переопределяем путь к БД на in-memory для тестов
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("BOT_TOKEN", "0:test")

from database.db import init_db, ensure_user
from database import queries


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Инициализируем тестовую БД один раз для всей сессии."""
    # Используем временный файл
    import tempfile
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()

    import config
    config.settings.DATABASE_PATH = tmp.name
    import database.db as db_module
    db_module.DB_PATH = tmp.name

    await init_db()
    yield
    os.unlink(tmp.name)


@pytest_asyncio.fixture
async def user_id() -> int:
    uid = 100001
    await ensure_user(uid, "testuser", "Test User")
    return uid


# ─── Транзакции ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_get_transactions(user_id):
    cats = await queries.get_categories(user_id, is_income=False)
    cat_id = cats[0]["id"] if cats else None

    txn_id = await queries.add_transaction(
        user_id=user_id,
        amount=500.0,
        category_id=cat_id,
        note="тест",
        is_income=False,
        source="text",
    )
    assert txn_id > 0

    txns = await queries.get_last_transactions(user_id, limit=5)
    assert any(t["id"] == txn_id for t in txns)


@pytest.mark.asyncio
async def test_delete_transaction(user_id):
    txn_id = await queries.add_transaction(
        user_id=user_id, amount=100.0, category_id=None,
        note="удаляю", is_income=False
    )
    ok = await queries.delete_transaction(txn_id, user_id)
    assert ok is True

    # Повторное удаление
    ok2 = await queries.delete_transaction(txn_id, user_id)
    assert ok2 is False


# ─── Отчёты ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_monthly_summary(user_id):
    from datetime import date
    now = date.today()
    await queries.add_transaction(user_id, 1000.0, None, "доход тест", is_income=True)
    await queries.add_transaction(user_id, 300.0,  None, "расход тест", is_income=False)

    summary = await queries.get_monthly_summary(user_id, now.year, now.month)
    assert summary["total_income"] >= 1000.0
    assert summary["total_expenses"] >= 300.0


# ─── Бюджеты ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_and_get_budget(user_id):
    cats = await queries.get_categories(user_id, is_income=False)
    assert cats, "Должны быть системные категории"
    cat_id = cats[0]["id"]

    await queries.set_budget(user_id, cat_id, 5000.0)
    budgets = await queries.get_budgets_with_spent(user_id)
    assert any(b["budget"] == 5000.0 for b in budgets)


# ─── Напоминания ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_and_delete_reminder(user_id):
    rid = await queries.add_reminder(
        user_id=user_id,
        title="Аренда",
        remind_at="2099-12-01T09:00:00",
        amount=15000.0,
        repeat_type="monthly",
    )
    assert rid > 0

    reminders = await queries.get_active_reminders(user_id)
    assert any(r["id"] == rid for r in reminders)

    ok = await queries.delete_reminder(rid, user_id)
    assert ok is True


@pytest.mark.asyncio
async def test_get_due_reminders(user_id):
    rid = await queries.add_reminder(
        user_id=user_id,
        title="Просроченное",
        remind_at="2000-01-01T00:00:00",
    )
    due = await queries.get_due_reminders("2001-01-01T00:00:00")
    assert any(r["id"] == rid for r in due)
    await queries.deactivate_reminder(rid)
