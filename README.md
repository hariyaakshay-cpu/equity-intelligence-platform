# Equity Intelligence Platform

## Daily price sync

1. Set `UPSTOX_ACCESS_TOKEN` in `.env` (the token expires daily).
2. `alembic upgrade head`
3. `python -m jobs.daily_sync [--symbols RELIANCE,TCS] [--days 365] [--schedule 18:30]`

Without `--schedule` it runs once (cron-friendly; exit code 1 if any company failed, 2 if the token is missing).
