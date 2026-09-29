"""Main entry point for the application.

    python main.py                  # startup banner + usage
    python main.py scan [--symbols RELIANCE,TCS]
    python main.py dashboard [--port 5051] [--demo]
"""

import argparse
import logging
import sys

from config import Settings
from config.logging_config import setup_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Equity Intelligence entry point.")
    sub = parser.add_subparsers(dest="command")

    scan = sub.add_parser("scan", help="Run the Equity Intelligence Scanner V1.")
    scan.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbols for a smoke run. Default: the full universe.",
    )

    dash = sub.add_parser("dashboard", help="Serve the read-only equity_intel dashboard.")
    dash.add_argument("--demo", action="store_true")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", type=int, default=None)
    return parser


def main():
    """
    Main function to initialize and run the application.
    """
    args = _build_parser().parse_args()

    try:
        settings = Settings()
        setup_logging(settings)

        print("=" * 50)
        print(f"  {settings.APP_NAME} - Version {settings.APP_VERSION}")
        print(f"  Environment: {settings.ENVIRONMENT}")
        print("=" * 50)

        logging.info("Application started")
    except Exception as e:
        logging.error(f"An error occurred during application startup: {e}")
        sys.exit(1)

    if args.command == "scan":
        from scripts import equity_scan

        argv = ["--symbols", args.symbols] if args.symbols else []
        sys.exit(equity_scan.main(argv))

    if args.command == "dashboard":
        from dashboard import app as dashboard_app

        argv = ["dashboard", "--host", args.host]
        if args.port is not None:
            argv += ["--port", str(args.port)]
        if args.demo:
            argv.append("--demo")
        sys.argv = argv
        dashboard_app.main()
        return

    _build_parser().print_help()


if __name__ == "__main__":
    main()
