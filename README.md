# Equity Intelligence Platform

## Daily price sync

1. Set `UPSTOX_CLIENT_ID`, `UPSTOX_CLIENT_SECRET`, `UPSTOX_REDIRECT_URI` in `.env`, then log in once per day with `python -m jobs.upstox_auth` (Upstox tokens expire ~03:30 IST and have no refresh token; the token is cached in `.upstox_token.json`). `UPSTOX_ACCESS_TOKEN` in `.env` still works as a fallback.
2. `alembic upgrade head`
3. `python -m jobs.daily_sync [--symbols RELIANCE,TCS] [--days 365] [--schedule 18:30]`

Without `--schedule` it runs once (cron-friendly; exit code 1 if any company failed, 2 if there is no valid token).
