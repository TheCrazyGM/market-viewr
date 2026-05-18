import json
import logging

from requests.exceptions import RequestException

from ..api.hive_engine import he_api
from ..extensions import cache
from ..utils.security import is_valid_image_url

logger = logging.getLogger(__name__)


@cache.memoize(timeout=3600)
def get_tokens():
    """Get list of all tokens from Hive Engine with pagination."""
    tokens = []
    offset = 0
    limit = 1000
    while True:
        batch = he_api.find("tokens", "tokens", limit=limit, offset=offset)
        if not batch:
            break
        for t in batch:
            if isinstance(t, dict):

                def _to_float(v):
                    try:
                        return float(v)
                    except Exception:
                        return 0.0

                if "supply" in t and t.get("supply") is not None:
                    t["supply"] = _to_float(t.get("supply"))
                if "circulatingSupply" in t and t.get("circulatingSupply") is not None:
                    t["circulatingSupply"] = _to_float(t.get("circulatingSupply"))
        tokens.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return tokens


@cache.memoize(timeout=900)
def get_token_info(token):
    """Get token information from Hive-Engine."""
    try:
        token_info = he_api.find_one("tokens", "tokens", query={"symbol": token})
        if isinstance(token_info, list) and token_info:
            token_info = token_info[0]
        if (
            token_info
            and "metadata" in token_info
            and isinstance(token_info["metadata"], str)
        ):
            try:
                token_info["metadata"] = json.loads(token_info["metadata"])
                if token_info["metadata"] and "icon" in token_info["metadata"]:
                    if not is_valid_image_url(token_info["metadata"]["icon"]):
                        token_info["metadata"]["icon"] = None
            except json.JSONDecodeError:
                pass
        if isinstance(token_info, dict):

            def _to_float(v):
                try:
                    return float(v)
                except Exception:
                    return 0.0

            for k in [
                "supply",
                "circulatingSupply",
                "stakingEnabled",
                "unstakingCooldown",
                "precision",
            ]:
                if k in token_info and token_info.get(k) is not None:
                    if k in ("supply", "circulatingSupply"):
                        token_info[k] = _to_float(token_info.get(k))
        return token_info
    except Exception as e:
        logger.error(f"Error getting token info for {token}: {e}")
        return None


@cache.memoize(timeout=900)
def get_richlist(symbol):
    """Return the token rich list and total burned balance for a given symbol."""
    richlist = []
    burned_balance = 0.0
    page_size = 1000
    seen_accounts = set()
    last_username = ""
    try:
        while True:
            query = {
                "symbol": symbol,
                "$or": [
                    {"balance": {"$gt": "0.00000000"}},
                    {"stake": {"$gt": "0.00000000"}},
                ],
            }
            if last_username:
                query["account"] = {"$gt": last_username}
            batch = he_api.find(
                "tokens",
                "balances",
                query=query,
                limit=page_size,
                indexes=[{"index": "account", "descending": False}],
            )
            if not batch:
                break
            for holder in batch:
                acct = holder.get("account")
                if acct == "null":
                    try:
                        burned_balance = float(holder.get("balance", 0))
                    except Exception:
                        burned_balance = 0.0
                    continue
                if acct and acct not in seen_accounts:

                    def _to_float(v):
                        try:
                            return float(v if v is not None else 0)
                        except Exception:
                            return 0.0

                    for num_key in (
                        "balance",
                        "stake",
                        "pendingUnstake",
                        "delegationsIn",
                        "delegationsOut",
                        "pendingUndelegations",
                    ):
                        if num_key in holder:
                            holder[num_key] = _to_float(holder.get(num_key))
                    holder["total"] = float(holder.get("balance", 0.0)) + float(
                        holder.get("stake", 0.0)
                    )
                    richlist.append(holder)
                    seen_accounts.add(acct)
            if batch:
                last_username = batch[-1].get("account", "")
            if len(batch) < page_size:
                break
        richlist.sort(key=lambda h: h.get("total", 0), reverse=True)
        return richlist, burned_balance
    except RequestException as e:
        logger.error(f"Richlist RPC failed for symbol {symbol}: {e}")
        raise RuntimeError("Hive-Engine RPC timeout")
