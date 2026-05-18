#!/usr/bin/env python
"""Utility script to purge all Flask-Caching entries."""

import logging

from viewr import cache, create_app


def drop_all_caches() -> None:
    """Remove all keys in the configured cache backend."""
    app = create_app()
    with app.app_context():
        cache.clear()
        app.logger.info("All caches cleared.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    drop_all_caches()
