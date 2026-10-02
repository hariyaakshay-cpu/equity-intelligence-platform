# Equity Intelligence Platform

## Daily price sync

1. Set `UPSTOX_CLIENT_ID`, `UPSTOX_CLIENT_SECRET`, `UPSTOX_REDIRECT_URI` in `.env`, then log in once per day with `python -m jobs.upstox_auth` (Upstox tokens expire ~03:30 IST and have no refresh token; the token is cached in `.upstox_token.json`). `UPSTOX_ACCESS_TOKEN` in `.env` still works as a fallback.
2. `alembic upgrade head`
3. `python -m jobs.daily_sync [--symbols RELIANCE,TCS] [--days 365] [--schedule 18:30]`

Without `--schedule` it runs once (cron-friendly; exit code 1 if any company failed, 2 if there is no valid token).

## API

`uvicorn api.app:app --reload` — interactive docs at `/docs`.

All endpoints except `/health` require an `X-API-Key` header. Generate a key with `python -m jobs.api_key` and put it in `API_KEYS` in `.env` (comma-separated for several). If `API_KEYS` is empty the API returns 503 rather than running open.

| Endpoint | Description |
|---|---|
| `GET /health` | Liveness check |
| `GET /companies?q=&exchange=&sector=&limit=&offset=` | Search/list active companies |
| `GET /companies/{symbol}` | Company detail |
| `GET /companies/{symbol}/prices?start=&end=&limit=` | Daily prices, newest first |
| `GET /companies/{symbol}/prices/latest` | Latest price |
| `GET /companies/{symbol}/financials?period_type=annual\|quarterly` | Financial statements |
| `GET /companies/{symbol}/indicators` | Returns (1w–1y), SMA 20/50/200, EMA 20, RSI 14, 30d volatility, 52-week range |
