"""Logging configuration for the application."""

import logging
from logging.handlers import RotatingFileHandler
import os

from config.settings import Settings


def setup_logging(settings: Settings):
    """
    Set up logging for the application.

    This function configures logging to both the console and a rotating file.
    The log format includes a timestamp, log level, filename, and line number.

    Args:
        settings: The application settings.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    log_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
    )

    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # File handler
    file_handler = RotatingFileHandler(
        "logs/application.log", maxBytes=1024 * 1024 * 5, backupCount=5
    )
    file_handler.setFormatter(log_formatter)

    # Console handler
    console_handler.setFormatter(log_formatter)

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)