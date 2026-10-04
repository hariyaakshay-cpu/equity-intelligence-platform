# Telegram digest (plumbing phase)

Date: 2026-10-04. Status: implemented, dry-run by default.

## Scope

Delivery path only: read the stored scanner data, build a short plain-text
digest, send it to one Telegram chat. The digest reports data freshness,
universe size, market breadth (share of symbols above EMA 200/50/20,
positive 10-day ROC) and the five symbols closest to their 252-bar high,
labelled descriptive. It contains **no buy/sell signals, scores, targets or
stop-losses**; B2 scoring and Trade Research remain `GATED`. Every message
ends with a research-only disclaimer.

## Not in scope (deliberately)

Intraday data, signal logic, interactive bot commands, scheduling. Intraday
signals wait for the ML evidence gate (see the ML research specification,
section 12) and need their own specification.

## Design

- `telegram_bot/digest.py`: reads through `dashboard.queries` on a read-only
  connection (`get_read_only_connection`); never writes.
- `telegram_bot/sender.py`: Telegram Bot API `sendMessage` via `requests`
  (already a dependency), plain text, token never logged or put in errors.
- `scripts/telegram_digest.py`: prints the digest; sends only with `--send`.
- Credentials: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` from `.env`
  (gitignored; `.env.example` has empty placeholders).
- `telegram_bot/` is under the same forbidden-import boundary as
  `dashboard/` (`test_import_boundaries.py`).

## Using it

1. Create a bot with @BotFather, put the token in `.env`; send the bot a
   message, then put your chat id in `.env`.
2. `python scripts/telegram_digest.py` (dry run), then `--send`.
