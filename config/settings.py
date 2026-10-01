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
        UPSTOX_ACCESS_TOKEN (str): Upstox OAuth access token (expires daily).
        UPSTOX_CLIENT_ID / UPSTOX_CLIENT_SECRET / UPSTOX_REDIRECT_URI (str): Upstox app credentials for the OAuth login.
        UPSTOX_BASE_URL (str): Base URL of the Upstox REST API.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    APP_NAME: str = "My Awesome App"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    DATABASE_URL: str = "sqlite:///./test.db"
    LOG_LEVEL: str = "INFO"
    UPSTOX_ACCESS_TOKEN: str = ""
    UPSTOX_BASE_URL: str = "https://api.upstox.com"
    UPSTOX_CLIENT_ID: str = ""
    UPSTOX_CLIENT_SECRET: str = ""
    UPSTOX_REDIRECT_URI: str = ""
