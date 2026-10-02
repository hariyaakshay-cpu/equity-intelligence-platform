"""Generate a new API key: python -m jobs.api_key

Add the printed value to API_KEYS in .env (comma-separate to allow several).
"""

import secrets

if __name__ == "__main__":
    print(secrets.token_urlsafe(32))
