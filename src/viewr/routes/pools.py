import logging

from flask import Blueprint, abort, render_template

from ..extensions import cache
from ..services.pools import get_lp_pool, get_lp_pools_for_token, get_lp_positions
from ..services.tokens import get_token_info
from ..utils.security import sanitize_symbol

logger = logging.getLogger(__name__)

pools_bp = Blueprint("pools", __name__)


@pools_bp.route("/lp/<token>")
@cache.cached(timeout=300)
def lp_list(token: str):
    token = sanitize_symbol(token)
    token_info = get_token_info(token)
    if not token_info:
        abort(404)
    pools = get_lp_pools_for_token(token)
    enriched = []
    for p in pools:
        tp = p.get("tokenPair", "")
        base, sep, quote = tp.partition(":")
        enriched.append({**p, "base": base, "quote": quote})
    try:
        enriched.sort(key=lambda x: float(x.get("totalShares", 0) or 0), reverse=True)
    except Exception:
        pass
    return render_template(
        "lp_list.html", token=token, token_info=token_info, pools=enriched
    )


@pools_bp.route("/lp/<base>/<quote>")
@cache.cached(timeout=300)
def lp_detail(base: str, quote: str):
    base = sanitize_symbol(base)
    quote = sanitize_symbol(quote)
    token_pair = f"{base.upper()}:{quote.upper()}"
    pool = get_lp_pool(token_pair)
    if not pool:
        rev_pair = f"{quote.upper()}:{base.upper()}"
        pool = get_lp_pool(rev_pair)
        if pool:
            token_pair = rev_pair
        else:
            abort(404)
    positions = get_lp_positions(token_pair, limit=200)

    def _to_float(val):
        try:
            return float(val if val is not None else 0)
        except Exception:
            return 0.0

    pool_numeric = dict(pool)
    for key in [
        "baseQuantity",
        "quoteQuantity",
        "basePrice",
        "quotePrice",
        "totalShares",
        "baseVolume",
        "quoteVolume",
    ]:
        if key in pool_numeric:
            pool_numeric[key] = _to_float(pool_numeric.get(key))
    return render_template(
        "lp_detail.html", token_pair=token_pair, pool=pool_numeric, positions=positions
    )
