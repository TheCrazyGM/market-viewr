import logging
import time
from datetime import datetime

import requests

from ..api.hive_engine import he_market
from ..extensions import cache

logger = logging.getLogger(__name__)

HE_HISTORY_API = "https://history.hive-engine.com"


@cache.memoize(timeout=300)
def get_trade_history(symbol, limit=100, days=30):
    try:
        all_trades = []
        batch_size = 1000
        total_needed = limit
        if days > 0:
            total_needed = batch_size * 10
        offset = 0
        oldest_timestamp = None
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)
        while len(all_trades) < total_needed:
            batch = he_market.get_trades_history(
                symbol=symbol, limit=batch_size, offset=offset
            )
            if not batch:
                break
            for trade in batch:
                if days > 0 and int(trade.get("timestamp", 0)) < cutoff_time:
                    oldest_timestamp = trade.get("timestamp")
                    break
                all_trades.append(trade)
            if oldest_timestamp and int(oldest_timestamp) < cutoff_time:
                break
            offset += batch_size
            if offset > batch_size * 10:
                break
        return all_trades[:limit]
    except Exception as e:
        logger.error(f"Error fetching trade history for {symbol}: {e}")
        return []


def get_market_data(symbol, days=30):
    timestamp_start = int((datetime.now().timestamp() - days * 24 * 60 * 60) * 1000)
    params = {"symbol": symbol, "timestampStart": timestamp_start}
    url = f"{HE_HISTORY_API}/marketHistory"
    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            cutoff = datetime.now().timestamp() - days * 24 * 60 * 60
            return [d for d in data if d.get("timestamp", 0) >= cutoff]
    except Exception as e:
        logger.error(f"Error fetching market data for {symbol}: {e}")
    return []
