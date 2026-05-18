import logging

from ..api.hive_engine import he_api
from ..extensions import cache

logger = logging.getLogger(__name__)


@cache.memoize(timeout=600)
def get_lp_pools_for_token(token: str) -> list[dict]:
    """Return all liquidity pools where the given token appears."""
    try:
        # Note: hive-engine API handles the regex query
        import re

        escaped_token = re.escape(token)
        query = {
            "$or": [
                {"tokenPair": {"$regex": f"^{escaped_token}:"}},
                {"tokenPair": {"$regex": f":{escaped_token}$"}},
            ]
        }
        pools = he_api.find("marketpools", "pools", query=query)
        return pools or []
    except Exception as e:
        logger.error(f"Error fetching LP pools for {token}: {e}")
        return []


@cache.memoize(timeout=600)
def get_lp_pool(token_pair: str) -> dict:
    """Return the data for a single liquidity pool."""
    try:
        pool = he_api.find_one("marketpools", "pools", query={"tokenPair": token_pair})
        if isinstance(pool, list):
            pool = pool[0] if pool else None
        return pool or None
    except Exception as e:
        logger.error(f"Error fetching LP pool {token_pair}: {e}")
        return None


@cache.memoize(timeout=600)
def get_lp_positions(token_pair: str, limit: int = 200) -> list[dict]:
    """Return the top liquidity provider positions for a given pool."""
    try:
        positions = he_api.find(
            "marketpools",
            "liquidityPositions",
            query={"tokenPair": token_pair},
            limit=limit,
            indexes=[{"index": "shares", "descending": True}],
        )
        return positions or []
    except Exception as e:
        logger.error(f"Error fetching LP positions for {token_pair}: {e}")
        return []
