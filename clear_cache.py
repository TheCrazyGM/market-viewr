#!/usr/bin/env python
"""Utility script to purge all Flask-Caching entries.

Run this via cron (or manually) when you want to invalidate every cached
value, forcing them to rebuild on next access.

Example crontab entry to run nightly at 03:00 (adjust paths):
    0 3 * * * /usr/bin/env python /path/to/market-viewr/clear_cache.py >> /var/log/market-viewr/clear_cache.log 2>&1
"""

import logging

from app import app, cache  # type: ignore


def drop_all_caches() -> None:
    """Remove all keys in the configured cache backend."""
    with app.app_context():
        cache.clear()
        app.logger.info("All caches cleared.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    drop_all_caches()
