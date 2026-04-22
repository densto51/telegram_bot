# 💰 Telegram-бот «Личный финансовый ассистент»

> Умный бот для ведения личных финансов прямо в Telegram.  
> Записывает траты голосом и текстом, строит отчёты, следит за бюджетом и напоминает о платежах.

---

## 📋 Содержание
- [Возможности](#-возможности)
- [Технологии](#-технологии)
- [Архитектура](#-архитектура)
- [Установка](#-установка)
- [Docker-деплой](#-docker-деплой)
- [Структура проекта](#-структура-проекта)
- [Схема базы данных](#-схема-базы-данных)
- [Команды бота](#-команды-бота)
- [Примеры использования](#-примеры-использования)

---

## ✨ Возможности

| Функция | Описание |
|---------|----------|
| 📝 Ввод текстом | «кофе 150», «350 обед», «потратил 1500 на продукты» |
| 🎙 Голосовой ввод | Голосовое → Whisper API → парсинг суммы |
| 📊 Отчёты | По неделям, месяцам, годам с визуализацией |
| 🎯 Бюджет | Лимиты по категориям + общий лимит расходов |
| ⏰ Напоминания | Разовые и повторяющиеся (день/неделя/месяц) |
| 🗂 Категории | 15+ системных + создание своих |
| 💚 Доходы | Учёт доходов по категориям |
| ⚡ Кэш | Redis кэширует отчёты (TTL 5 мин) |
| 🛡 Anti-flood | Throttling middleware (0.5 сек) |

---

## 🛠 Технологии

```
Python 3.12
├── aiogram 3.13        — асинхронный Telegram Bot Framework
├── aiosqlite 0.20      — async обёртка над SQLite3
├── redis-py 5.2        — Redis клиент (FSM storage + кэш)
├── APScheduler 3.10    — планировщик задач (напоминания)
├── pydantic-settings   — конфигурация из .env
├── openai (Whisper)    — распознавание голосовых сообщений
└── pytz / dateutil     — работа с часовыми поясами
```

---

## 🏗 Архитектура

```
┌─────────────────────────────────────────────────────┐
│                  Telegram Bot API                    │
└───────────────────────┬─────────────────────────────┘
                        │ polling / webhook
┌───────────────────────▼─────────────────────────────┐
│              aiogram Dispatcher                      │
│  ┌──────────┐  ┌────────────┐  ┌─────────────────┐  │
│  │Middleware│  │   Routers  │  │  FSM Storage    │  │
│  │Throttling│  │  handlers/ │  │  (Redis)        │  │
│  │UserTrack │  │            │  └─────────────────┘  │
│  └──────────┘  └─────┬──────┘                       │
└────────────────────── │ ────────────────────────────┘
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
  ┌──────────┐   ┌───────────┐   ┌─────────────┐
  │ SQLite3  │   │   Redis   │   │  Scheduler  │
  │(transactions│ │(cache/FSM)│   │(APScheduler)│
  │ budgets  │   │           │   │  reminders  │
  │reminders)│   └───────────┘   └─────────────┘
  └──────────┘
        │
  ┌─────▼──────┐
  │ OpenAI API │
  │ (Whisper)  │
  └────────────┘
```

### Поток сообщения (расход текстом)

```
Пользователь: «кофе 150»
    │
    ▼
ThrottlingMiddleware → проверка rate limit
    │
    ▼
UserTrackerMiddleware → ensure_user() в БД
    │
    ▼
expenses.router → parse_expense_text("кофе 150")
    │             → {amount: 150, note: "кофе"}
    ▼
FSM: ExpenseStates.waiting_category
    │
    ▼
Inline KB: выбор категории
    │
    ▼
add_transaction() → SQLite
    │
    ▼
Проверка бюджета → предупреждение если > 85%
    │
    ▼
Ответ пользователю ✅
```

### Поток голосового сообщения

```
Голосовое OGG
    │
    ▼
voice.handler → bot.download_file()
    │
    ▼
OpenAI Whisper API → текст на русском
    │
    ▼
parse_expense_text() → amount + note
    │
    ▼
→ передача в ExpenseStates FSM (как текстовый ввод)
```

---

## 🚀 Установка

### Требования
- Python 3.12+
- Redis 7+
- ffmpeg (для голосовых сообщений)

### Шаги

```bash
# 1. Клонировать репозиторий
git clone https://github.com/yourname/finance-bot.git
cd finance-bot

# 2. Создать виртуальное окружение
python -m venv .venv
source .venv/bin/activate        # Linux/macOS
# .venv\Scripts\activate         # Windows

# 3. Установить зависимости
pip install -r requirements.txt

# 4. Настроить конфигурацию
cp .env.example .env
nano .env                        # заполнить BOT_TOKEN, OPENAI_API_KEY

# 5. Запустить Redis (если локально)
redis-server --daemonize yes

# 6. Запустить бота
python main.py
```

---

## 🐳 Docker-деплой

```bash
# Скопировать и заполнить .env
cp .env.example .env

# Собрать и запустить
docker-compose up -d --build

# Логи
docker-compose logs -f bot

# Остановить
docker-compose down
```

---

## 📁 Структура проекта

```
finance_bot/
├── main.py                  # Точка входа
├── config.py                # Конфигурация (pydantic-settings)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
│
├── database/
│   ├── db.py                # init_db, get_db, ensure_user
│   └── queries.py           # Все SQL-запросы
│
├── handlers/
│   ├── start.py             # /start, /help, главное меню
│   ├── expenses.py          # Запись расходов (FSM)
│   ├── income.py            # Запись доходов (FSM)
│   ├── voice.py             # Голосовые сообщения → Whisper
│   ├── budget.py            # Управление бюджетами
│   ├── reports.py           # Финансовые отчёты
│   ├── reminders.py         # Напоминания (FSM)
│   └── categories.py        # Управление категориями
│
├── keyboards/
│   ├── main_menu.py         # Главное меню
│   ├── categories.py        # Клавиатура категорий
│   ├── reports.py           # Навигация по отчётам
│   ├── budget.py            # Меню бюджета
│   └── reminders.py         # Список/повтор напоминаний
│
├── middlewares/
│   ├── throttling.py        # Anti-flood (rate limit)
│   └── user_tracker.py      # Авто-регистрация пользователей
│
├── scheduler/
│   └── tasks.py             # APScheduler: проверка напоминаний
│
└── utils/
    ├── parser.py            # Парсинг свободного текста
    └── formatters.py        # Форматирование чисел, баров, дат
```

---

## 🗄 Схема базы данных

```sql
users            categories        transactions
─────────        ──────────        ────────────
id (PK)          id (PK)           id (PK)
username         user_id (FK)      user_id (FK)
full_name        name              category_id (FK)
currency         icon              amount
timezone         color             is_income
monthly_limit    is_income         note
created_at       is_system         source
updated_at                         txn_date
                                   created_at

budgets          reminders
───────          ─────────
id (PK)          id (PK)
user_id (FK)     user_id (FK)
category_id (FK) title
amount           amount
period           remind_at
                 repeat_type
                 repeat_day
                 is_active
                 note
```

---

## 🤖 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/help` | Справка |
| `/expense` | Записать расход |
| `/income` | Записать доход |
| `/budget` | Управление бюджетами |
| `/report` | Финансовые отчёты |
| `/reminders` | Напоминания |
| `/categories` | Управление категориями |
| `/delN` | Удалить транзакцию #N |

---

## 💡 Примеры использования

### Быстрый ввод расходов
```
Пользователь → кофе 150
Бот → 💰 Сумма: 150 с | Выбери категорию: [☕ Кафе] [🍔 Еда] ...

Пользователь → 350 обед в столовой
Бот → ✅ Расход записан! 💸 350 с — обед в столовой
```

### Голосовой ввод
```
[голосовое: «потратил пятьсот сом на такси»]
Бот → 🎙 Распознано: «потратил пятьсот сом на такси»
      ✅ Сумма: 500 с | Описание: такси
      Выбери категорию: [🚗 Транспорт] ...
```

### Напоминание о платеже
```
Пользователь → [кнопка ⏰ Напоминания → Добавить]
Бот → Введи название: Аренда квартиры
Пользователь → Аренда квартиры
Бот → Введи сумму:
Пользователь → 15000
Бот → Когда напомнить? (ДД.ММ.ГГГГ ЧЧ:ММ)
Пользователь → 01.02.2026 09:00
Бот → Повторять? [Разово] [Ежемесячно] ...
Пользователь → [Ежемесячно]
Бот → ✅ Напоминание создано! Каждое 1-е числа в 09:00
```

### Отчёт за месяц
```
📅 Отчёт за Январь 2026

💚 Доходы:  85 000 с
💸 Расходы: 62 350 с
📈 Баланс:  22 650 с

📊 Расходы по категориям:
  🍔 Еда
  ████████░░ 18 500 с (30%)
  🚗 Транспорт
  ████░░░░░░  8 200 с (13%)
  🏠 Жильё
  ██████░░░░ 15 000 с (24%)
```

---

## 📄 Лицензия

MIT — используй свободно для учёбы и личных проектов.
