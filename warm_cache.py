#!/usr/bin/env python
"""Pre-warm Redis/Flask-Caching entries for richlists.

Run this script periodically (e.g. via cron) to fetch the full list of Hive-Engine
tokens and invoke `get_richlist` for each symbol, so that subsequent web
requests are served directly from cache.

Example crontab entry to run every hour (adjust paths):
    0 * * * * /usr/bin/env python /path/to/market-viewr/warm_cache.py >> /var/log/market-viewr/warm_cache.log 2>&1

The script expects the same virtualenv as the main app, with Redis running if
`RedisCache` is configured.
"""

import logging
from typing import List

from app import app, get_tokens, get_richlist
from flask import current_app


def warm_richlists() -> None:
    """Fetch all token symbols and warm their richlist caches."""

    with app.app_context():
        tokens: List[dict] = get_tokens()
        total = len(tokens)
        current_app.logger.info("Warming richlist cache for %s tokens", total)

        for idx, token in enumerate(tokens, start=1):
            symbol = token.get("symbol")
            if not symbol:
                continue

            try:
                get_richlist(symbol)
                current_app.logger.debug(
                    "(%d/%d) Cached richlist for %s", idx, total, symbol
                )
            except Exception as exc:  # pylint: disable=broad-except
                # We swallow individual token failures so the warm-up continues.
                current_app.logger.warning(
                    "Failed to cache richlist for %s: %s", symbol, exc
                )

        current_app.logger.info("Richlist cache warm-up complete.")


if __name__ == "__main__":
    # Ensure logging is visible when run via cron
    logging.basicConfig(level=logging.INFO)
    warm_richlists()
