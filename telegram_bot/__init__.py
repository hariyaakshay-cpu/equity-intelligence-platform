"""Telegram delivery plumbing for equity_intel's daily scanner digest.

Read-only and descriptive: it reports data freshness and market-breadth
statistics already stored by the scanner. It emits no buy/sell signals, no
scores and no trade setups (those stay GATED; see the ML research spec).
"""
