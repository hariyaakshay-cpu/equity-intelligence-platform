"""Main entry point for the application."""

import logging
import sys

from config import Settings
from config.logging_config import setup_logging


def main():
    """
    Main function to initialize and run the application.
    """
    try:
        # Load settings
        settings = Settings()

        # Setup logging
        setup_logging(settings)

        # Print startup banner
        print("=" * 50)
        print(f"  {settings.APP_NAME} - Version {settings.APP_VERSION}")
        print(f"  Environment: {settings.ENVIRONMENT}")
        print("=" * 50)

        logging.info("Application started")

        # Your application logic goes here

    except Exception as e:
        logging.error(f"An error occurred during application startup: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()