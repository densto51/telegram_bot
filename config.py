"""
Конфигурация бота — загружается из .env файла через pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    #  Telegram
    BOT_TOKEN: str

    #Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    #  SQLite
    DATABASE_PATH: str = "finance.db"

    # OpenAI (Whisper) — для голосового ввода
    OPENAI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    #  Настройки бота
    DEFAULT_CURRENCY: str = "KGS"   # Сом (Кыргызстан), меняйте по необходимости
    DEFAULT_TIMEZONE: str = "Asia/Bishkek"
    MAX_BUDGET_CATEGORIES: int = 20
    REPORT_CACHE_TTL: int = 300      # секунд


settings = Settings()
