#!/usr/bin/env python
"""Pre-warm Redis/Flask-Caching entries for richlists."""

import logging

from flask import current_app

from viewr import create_app
from viewr.services.tokens import get_richlist, get_tokens


def warm_richlists() -> None:
    """Fetch all token symbols and warm their richlist caches."""
    app = create_app()
    with app.app_context():
        tokens = get_tokens()
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
            except Exception as exc:
                current_app.logger.warning(
                    "Failed to cache richlist for %s: %s", symbol, exc
                )
        current_app.logger.info("Richlist cache warm-up complete.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    warm_richlists()
