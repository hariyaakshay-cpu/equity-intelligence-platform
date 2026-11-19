"""Application configuration settings."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Represents the application settings.

    Attributes:
        APP_NAME (str): The name of the application.
        APP_VERSION (str): The version of the application.
        ENVIRONMENT (str): The environment where the application is running.
        DEBUG (bool): A flag indicating whether debug mode is enabled.
        DATABASE_URL (str): The URL for connecting to the database.
        LOG_LEVEL (str): The logging level for the application.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "My Awesome App"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///./test.db"
    LOG_LEVEL: str = "INFO"

    UPSTOX_ACCESS_TOKEN: str | None = None
    # Read-only Upstox Analytics Token (Developer Apps > Analytics tab, valid one year, cannot place orders).
    # Used by the paper board for live quotes so no daily login is needed; falls back to UPSTOX_ACCESS_TOKEN.
    UPSTOX_ANALYTICS_TOKEN: str | None = None
    # Telegram bot for the paper board's signal messages (text only, never orders); set both or neither.
    TELEGRAM_BOT_TOKEN: str | None = None
    TELEGRAM_CHAT_ID: str | None = None
