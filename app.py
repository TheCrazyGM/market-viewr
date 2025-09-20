import csv
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import io
import json
import logging
import re
import random
import string
import time
from urllib.parse import urlparse

from flask import Flask, Response, abort, redirect, render_template, request, url_for
from flask_caching import Cache
from nectarengine.api import Api
from nectarengine.market import Market
import pandas as pd
import plotly
import plotly.graph_objects as go
import requests
from requests.adapters import HTTPAdapter, Retry
from requests.exceptions import RequestException
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
# Cache configuration (prefers Redis, falls back to SimpleCache)
app.config["CACHE_REDIS_URL"] = "redis://localhost:6379/1"
try:
    import redis  # noqa: F401

    # Attempt to connect
    import redis as _redis_module

    _redis_module.from_url(app.config["CACHE_REDIS_URL"]).ping()
    app.config["CACHE_TYPE"] = "RedisCache"
except Exception as e:
    # Redis not available – fallback to in-memory cache
    app.logger.warning(f"Redis cache unavailable, using SimpleCache. ({e})")
    app.config["CACHE_TYPE"] = "SimpleCache"

cache = Cache(app)
# Setup Logger
app.logger = logging.getLogger(__name__)


# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    """Handle 404 errors by showing a custom page."""
    return render_template("error_404.html"), 404


@app.errorhandler(500)
def server_error(e):
    """Handle 500 errors by showing a custom page."""
    return render_template("error_500.html"), 500


@app.errorhandler(Exception)
def handle_exception(e):
    """Handle any unexpected exceptions."""
    # Pass through HTTP errors
    if isinstance(e, HTTPException):
        return e

    # Log the error for debugging
    app.logger.error(f"Unhandled exception: {str(e)}")

    # Show generic error page
    return (
        render_template(
            "error_generic.html",
            code="500 - Server Error",
            message="An unexpected error occurred. Please try again later.",
        ),
        500,
    )


# Custom Jinja2 filter for formatting timestamps
@app.template_filter("timestamp_to_date")
def timestamp_to_date(timestamp):
    """
    Convert a Unix timestamp (seconds since the epoch) to a local time string in the format "YYYY-MM-DD HH:MM:SS".

    Parameters:
        timestamp (int | float): Seconds since the Unix epoch.

    Returns:
        str: Formatted local date/time string "YYYY-MM-DD HH:MM:SS".
    """
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


@app.template_filter("fmt")
def fmt_number(value, spec=",.4f"):
    """
    Format a value as a number using a Python format specification, safely falling back if conversion fails.

    Converts the input to float and applies the given format spec (default: ",.4f"). If the value cannot be converted to a float, the original value is returned unchanged.

    Parameters:
        spec (str): Python format specification to apply (e.g., ",.2f", ".0f"). Default is ",.4f".

    Returns:
        str | Any: The formatted numeric string on success, or the original input if not convertible.
    """
    try:
        fval = Decimal(str(value))
        return format(fval, spec)
    except (InvalidOperation, ValueError, TypeError):
        # Return original if not convertible
        return value


# Hive Engine API endpoints for history API
HE_HISTORY_API = "https://history.hive-engine.com"


def get_engine_nodes(max_nodes: int = 10, timeout: int = 3):
    """Return a list of healthy Hive-Engine RPC nodes.

    The list is fetched from the `flowerengine` account's `json_metadata` field
    on the Hive blockchain.  Each node is then probed with a lightweight RPC
    call and only nodes that respond successfully within *timeout* seconds are
    returned.  Always falls back to ``https://enginerpc.com/`` if no nodes are
    reachable.
    """

    # Step 1. Fetch node list from the Hive blockchain using multiple API endpoints
    payload = {
        "jsonrpc": "2.0",
        "method": "database_api.find_accounts",
        "params": {"accounts": ["flowerengine"]},
        "id": 1,
    }

    # List of public Hive API nodes to try
    hive_api_nodes = [
        "https://api.hive.blog",
        "https://api.syncad.com",
        "https://anyx.io",
    ]

    nodes: list[str] = []
    for hive_node in hive_api_nodes:
        app.logger.debug(f"Attempting to fetch node list from {hive_node}")
        try:
            resp = requests.post(hive_node, json=payload, timeout=5)
            app.logger.debug(
                f"Response status from {hive_node}: {resp.status_code if resp else 'no response'}"
            )
            resp.raise_for_status()
            data = resp.json()
            meta_str = (
                data.get("result", {})
                .get("accounts", [{}])[0]
                .get("json_metadata", "{}")
            )
            app.logger.debug(f"Raw json_metadata from {hive_node}: {meta_str[:200]}")
            meta = json.loads(meta_str) if meta_str else {}
            nodes = meta.get("nodes", [])
            app.logger.debug(f"Extracted {len(nodes)} nodes from {hive_node}")
            if nodes:
                app.logger.info(f"Successfully retrieved node list from {hive_node}")
                break  # Successfully retrieved node list
        except Exception as e:
            app.logger.warning(f"Failed to fetch node list from {hive_node}: {e}")
            continue  # Try the next Hive API node

    # If all attempts failed, nodes will remain an empty list

    # Ensure we have a list to iterate
    if not isinstance(nodes, list):
        nodes = []

    # Step 2. Probe each node to see if it is responding
    healthy_nodes: list[str] = []
    # Use an RPC method that all Hive-Engine nodes support for health checking
    test_payload = {
        "jsonrpc": "2.0",
        "method": "blockchain.getLatestBlockInfo",
        "params": {},
        "id": 1,
    }

    for node in nodes:
        if len(healthy_nodes) >= max_nodes:
            break
        try:
            r = requests.post(node, json=test_payload, timeout=timeout)
            if r.ok:
                res = r.json().get("result")
                # A valid response should contain a block number field
                if isinstance(res, dict) and res.get("blockNumber"):
                    healthy_nodes.append(node)
        except Exception:
            continue

    # Always include the public fallback node
    fallback = "https://enginerpc.com/"
    if fallback not in healthy_nodes:
        healthy_nodes.append(fallback)

    return healthy_nodes


# Initialize hiveengine API
# Configure requests session with retries to make Hive-Engine calls more resilient
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)
nodes = get_engine_nodes()

# Helper factories that pick a fresh random node each time


def get_he_api():
    """Return a new Api instance pointing at a random healthy Hive-Engine node."""
    return Api(
        url=random.choice(nodes) if nodes else "https://enginerpc.com/",
        timeout=30,
        session=session,
    )


def get_he_market():
    """Return a new Market instance bound to a fresh Api."""
    return Market(api=get_he_api())


class _LazyProxy:
    """Delegate attribute access to a freshly-constructed object from *factory*."""

    def __init__(self, factory):
        self._factory = factory

    def __getattr__(self, item):
        # Create a new underlying object on every attribute access
        return getattr(self._factory(), item)


# These proxies keep existing code unchanged while distributing calls across nodes
he_api = _LazyProxy(get_he_api)
he_market = _LazyProxy(get_he_market)


# Validate if URL is an image
def is_valid_image_url(url):
    """Lightweight validation that the URL looks safe for an image fetch.

    Many Hive/remote icon URLs omit file extensions or use CDN paths with query
    params. We only enforce scheme+host and block obvious script/data URIs.
    """
    if not url:
        return False

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        lowered = url.lower()
        # Block obvious script injection vectors
        if lowered.startswith("javascript:") or lowered.startswith("data:"):
            return False
        if "<script" in lowered or "onerror=" in lowered:
            return False

        # Allow without enforcing a file extension; browsers will handle errors
        return True
    except Exception:
        return False


@cache.memoize(timeout=3600)
def get_tokens():
    """Get list of all tokens from Hive Engine with pagination."""
    tokens = []
    offset = 0
    limit = 1000  # Maximum limit per request

    while True:
        # Fetch a batch of tokens
        batch = he_api.find("tokens", "tokens", limit=limit, offset=offset)
        if not batch:
            break

        tokens.extend(batch)

        # If we got fewer tokens than the limit, we have reached the end
        if len(batch) < limit:
            break

        # Move to the next batch
        offset += limit

    return tokens


# Get token info
@cache.memoize(timeout=900)
def get_token_info(token):
    """Get token information from Hive-Engine."""
    try:
        # Use the correct API to get token info
        token_info = he_api.find_one("tokens", "tokens", query={"symbol": token})

        # If token_info is a list, get the first item
        if isinstance(token_info, list) and token_info:
            token_info = token_info[0]

        # Parse metadata if it's a string
        if (
            token_info
            and "metadata" in token_info
            and isinstance(token_info["metadata"], str)
        ):
            try:
                token_info["metadata"] = json.loads(token_info["metadata"])

                # Validate icon URL if present
                if token_info["metadata"] and "icon" in token_info["metadata"]:
                    if not is_valid_image_url(token_info["metadata"]["icon"]):
                        # Remove or replace invalid icon
                        token_info["metadata"]["icon"] = None

            except json.JSONDecodeError:
                # If metadata is not valid JSON, keep it as is
                pass

        # Normalize common numeric fields to floats for consistent template formatting
        if isinstance(token_info, dict):

            def _to_float(v):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return 0.0

            for k in [
                "supply",
                "circulatingSupply",
                "stakingEnabled",
                "unstakingCooldown",
                "precision",
            ]:
                if k in token_info and token_info.get(k) is not None:
                    # precision and stakingEnabled may be non-float types; keep original if appropriate
                    if k in ("supply", "circulatingSupply"):
                        token_info[k] = _to_float(token_info.get(k))
        return token_info
    except Exception:
        return None


# Get token market data
def get_market_data(symbol, days=30):
    # Calculate timestamp in milliseconds
    """
    Fetch recent market history for a token symbol from the Hive Engine history API.

    Calculates a start timestamp `days` days before now (in milliseconds) and requests
    market history for `symbol` from the configured HE_HISTORY_API endpoint. On a
    successful HTTP 200 response returns the parsed JSON data; on any other status
    returns an empty list.

    Parameters:
        symbol (str): Token symbol to query (e.g., "TOK").
        days (int): Number of days of history to request (default: 30).

    Returns:
        list|dict: Parsed JSON response from the history API on success, otherwise an empty list.
    """
    timestamp_start = int((datetime.now().timestamp() - days * 24 * 60 * 60) * 1000)
    url = f"{HE_HISTORY_API}/marketHistory?symbol={symbol}&timestampStart={timestamp_start}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data
    return []


# ============================
# Liquidity Pools (Marketpools)
# ============================


@cache.memoize(timeout=600)
def get_lp_pools_for_token(token: str) -> list[dict]:
    """
    Return all liquidity pools where the given token appears as either the base or the quote asset.

    Searches the marketpools.pools table for tokenPair values that start with "TOKEN:" or end with ":TOKEN" and returns the matching pool records (each record is a dict with fields such as tokenPair, baseQuantity, quoteQuantity, basePrice, quotePrice, totalShares, etc.). Returns an empty list if no pools are found or on error.

    Notes:
    - Token matching is literal and case-sensitive.
    - The function returns a list of dicts; callers should handle an empty list as "no pools".
    """
    try:
        # Escape special regex characters in the token
        escaped_token = re.escape(token)
        # Match either "TOKEN:*" or "*:TOKEN" on tokenPair
        query = {
            "$or": [
                {"tokenPair": {"$regex": f"^{escaped_token}:"}},
                {"tokenPair": {"$regex": f":{escaped_token}$"}},
            ]
        }
        pools = he_api.find("marketpools", "pools", query=query, limit=1000)
        return pools or []
    except Exception as e:
        app.logger.error(f"Error fetching LP pools for {token}: {e}")
        return []


@cache.memoize(timeout=600)
def get_lp_pool(token_pair: str) -> dict | None:
    """
    Return the liquidity pool record for a given token pair (e.g. "TOKEN:SWAP.HIVE") or None if not found.

    This normalizes RPC responses that sometimes return a list for a single result (the first item is used).
    Returns None if the pool does not exist or if an error occurs while fetching.
    """
    try:
        pool = he_api.find_one("marketpools", "pools", query={"tokenPair": token_pair})
        # Some RPCs may return list for find_one, normalize
        if isinstance(pool, list):
            pool = pool[0] if pool else None
        return pool or None
    except Exception as e:
        app.logger.error(f"Error fetching LP pool {token_pair}: {e}")
        return None


@cache.memoize(timeout=600)
def get_lp_positions(token_pair: str, limit: int = 200) -> list[dict]:
    """
    Return the top liquidity provider positions for a given liquidity pool token pair.

    Retrieves entries from the `marketpools.liquidityPositions` table for `token_pair` and returns them sorted by `shares` in descending order. Returns an empty list if no positions are found or on error (errors are logged).

    Parameters:
        token_pair (str): Token pair identifier in the form "BASE:QUOTE".
        limit (int): Maximum number of positions to return (default 200).

    Returns:
        list[dict]: A list of position records (possibly empty).
    """
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
        app.logger.error(f"Error fetching LP positions for {token_pair}: {e}")
        return []


# Get token richlist
@cache.memoize(timeout=900)
def get_richlist(symbol):
    """
    Return the token rich list and total burned balance for a given symbol.

    Builds a list of holders for `symbol`, where each holder dict is augmented with a numeric
    `total` field equal to the sum of their `balance` and `stake`. Accounts are deduplicated
    (by account name, keeping the first seen), and the final list is sorted by `total`
    descending. Entries with account == "null" are treated as the burned balance (returned
    separately as a float). Numeric parsing is tolerant of missing or malformed values.

    Parameters:
        symbol (str): Token symbol to query.

    Returns:
        tuple[list[dict], float]: (richlist, burned_balance) where `richlist` is a list of
        holder records (each includes a computed `total`) and `burned_balance` is the
        burned token amount for the queried symbol.

    Raises:
        RuntimeError: If the underlying Hive-Engine RPC requests time out or fail.
    """
    richlist: list[dict] = []
    burned_balance = 0.0
    page_size = 1000  # Hive-Engine max per request
    prefixes = list(string.ascii_lowercase)
    seen_accounts: set[str] = set()

    try:
        for prefix in prefixes:
            offset = 0
            while True:
                batch = he_api.find(
                    "tokens",
                    "balances",
                    query={
                        "symbol": symbol,
                        "account": {"$regex": f"^{prefix}"},
                        "$or": [
                            {"balance": {"$gt": "0.00000000"}},
                            {"stake": {"$gt": "0.00000000"}},
                        ],
                    },
                    limit=page_size,
                    offset=offset,
                    indexes=[{"index": "balance", "descending": True}],
                )
                if not batch:
                    break

                for holder in batch:
                    acct = holder.get("account")
                    if acct == "null":
                        # burned tokens
                        try:
                            burned_balance = float(holder.get("balance", 0))
                        except (ValueError, TypeError):
                            burned_balance = 0.0
                        continue

                    if acct and acct not in seen_accounts:
                        # Normalize common numeric fields to floats for consistent downstream formatting
                        def _to_float(v):
                            try:
                                return float(v if v is not None else 0)
                            except (ValueError, TypeError):
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

                        balance_val = holder.get("balance", 0.0)
                        stake_val = holder.get("stake", 0.0)
                        holder["total"] = float(balance_val) + float(stake_val)
                        richlist.append(holder)
                        seen_accounts.add(acct)

                if len(batch) < page_size:
                    break
                offset += page_size

        # After looping through all prefixes, sort and return
        richlist.sort(key=lambda h: h.get("total", 0), reverse=True)
        return richlist, burned_balance

    except RequestException as e:
        app.logger.error(f"Richlist RPC failed: {e}")
        raise RuntimeError("Hive-Engine RPC timeout")


# Get token market history
@cache.memoize(timeout=300)
def get_trade_history(symbol, limit=100, days=30):
    try:
        all_trades = []
        batch_size = 1000  # Maximum batch size for each API call
        total_needed = limit  # How many trades we want to return in total

        # If days is specified, we'll try to get trades from the last X days
        if days > 0:
            # Calculate how many trades we might need to fetch to cover the time period
            # This is an estimate - we'll keep fetching until we have enough or hit the time limit
            total_needed = batch_size * 10  # Start with a reasonable number

        # We'll make multiple API calls with pagination to get more history
        offset = 0
        oldest_timestamp = None

        # Get current timestamp for comparison (to filter by days)
        current_time = time.time()
        cutoff_time = current_time - (days * 24 * 60 * 60)  # X days ago in seconds

        while len(all_trades) < total_needed:
            # Get a batch of trades
            batch = he_market.get_trades_history(
                symbol=symbol, limit=batch_size, offset=offset
            )

            # If no more trades, break the loop
            if not batch:
                break

            # Process this batch
            for trade in batch:
                # If we're filtering by days and this trade is older than our cutoff, stop
                if days > 0 and int(trade.get("timestamp", 0)) < cutoff_time:
                    oldest_timestamp = trade.get("timestamp")
                    break

                all_trades.append(trade)

            # If we found a trade older than our cutoff, stop fetching
            if oldest_timestamp and int(oldest_timestamp) < cutoff_time:
                break

            # Move to the next batch
            offset += batch_size

            # Safety check - if we've made too many API calls, stop
            if offset > batch_size * 10:
                break

        # Return only the requested number of trades
        return all_trades[:limit]
    except Exception as e:
        print(f"Error fetching trade history: {e}")
        return []


# Routes


@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint to verify the application and its dependencies are running."""
    status = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {},
    }

    # Check Redis connection
    try:
        cache.set("healthcheck", "ok", timeout=5)
        status["dependencies"]["redis"] = "ok"
    except Exception as e:
        status["status"] = "error"
        status["dependencies"]["redis"] = f"error: {str(e)}"

    # Check Hive-Engine API connection using a simple and valid token query
    try:
        # Fetch the first token as a health test
        he_api.find_one("tokens", "tokens", query={})
        status["dependencies"]["hive_engine"] = "ok"
    except Exception as e:
        status["status"] = "error"
        status["dependencies"]["hive_engine"] = f"error: {str(e)}"

    return status, 200 if status["status"] == "ok" else 503


@app.route("/robots.txt")
def robots_txt():
    return app.send_static_file("robots.txt")


@app.route("/")
@app.route("/page/<int:page>")
@cache.cached(timeout=3600, query_string=True)
def index(page=1):
    """
    Render the homepage with token listings, optional search, and pagination.

    Reads the optional query parameter "q" (case-insensitive) from the request to filter tokens by symbol or name.
    Parses each token's JSON `metadata` string (if present) and nulls any invalid `icon` URLs via `is_valid_image_url`.
    Paginates results at 100 tokens per page and renders "index.html" with the following context:
    `tokens`, `page`, `per_page`, `total`, `total_pages`, and `search_query`.

    Parameters:
        page (int): 1-based page number to display (defaults to 1).

    Returns:
        A Flask response rendering the "index.html" template with the paginated token data.
    """
    # Get search query from request args
    search_query = request.args.get("q", "").lower()

    # Get all tokens
    all_tokens = get_tokens()

    # Parse metadata for each token
    for token in all_tokens:
        if token and "metadata" in token and isinstance(token["metadata"], str):
            try:
                token["metadata"] = json.loads(token["metadata"])

                # Validate icon URL if present
                if token["metadata"] and "icon" in token["metadata"]:
                    if not is_valid_image_url(token["metadata"]["icon"]):
                        # Remove invalid icon
                        token["metadata"]["icon"] = None

            except json.JSONDecodeError:
                # If metadata is not valid JSON, keep it as is
                pass

    # Filter tokens if search query is provided
    if search_query:
        filtered_tokens = []
        for token in all_tokens:
            # Search in symbol and name
            if (
                search_query in token.get("symbol", "").lower()
                or search_query in token.get("name", "").lower()
            ):
                filtered_tokens.append(token)
        all_tokens = filtered_tokens

    # Pagination logic
    per_page = 100
    total = len(all_tokens)
    offset = (page - 1) * per_page
    tokens = all_tokens[offset : offset + per_page]

    # Calculate total pages
    total_pages = (total + per_page - 1) // per_page if total > 0 else 1

    return render_template(
        "index.html",
        tokens=tokens,
        page=page,
        per_page=per_page,
        total=total,
        total_pages=total_pages,
        search_query=search_query,
    )


@app.route("/lp/<token>")
@cache.cached(timeout=300)
def lp_list(token: str):
    """
    Render a page listing liquidity pools that include the given token as base or quote.

    Looks up token metadata and fetches matching liquidity pools, enriches each pool dict with `base` and `quote`
    derived from the pool's `tokenPair`, and returns a rendered 'lp_list.html' template with `token`, `token_info`,
    and the enriched `pools`.

    Parameters:
        token (str): Token symbol to display pools for.

    Returns:
        A Flask response rendering 'lp_list.html'.

    Raises:
        Aborts with HTTP 404 if the token is not found.
    """
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    pools = get_lp_pools_for_token(token)

    # Derive a friendlier structure including base/quote split
    enriched: list[dict] = []
    for p in pools:
        tp = p.get("tokenPair", "")
        base, sep, quote = tp.partition(":")
        enriched.append(
            {
                **p,
                "base": base,
                "quote": quote,
            }
        )
    # Show deepest pools first
    try:
        enriched.sort(
            key=lambda x: float(x.get("totalShares", 0) or 0),
            reverse=True,
        )
    except (ValueError, TypeError):
        pass

    return render_template(
        "lp_list.html",
        token=token,
        token_info=token_info,
        pools=enriched,
    )


@app.route("/lp/<base>/<quote>")
@cache.cached(timeout=300)
def lp_detail(base: str, quote: str):
    """
    Render the liquidity pool detail page for a given BASE:QUOTE pool.

    Looks up the pool for the provided base and quote symbols. If the exact
    pair is not found, the reversed pair (QUOTE:BASE) is tried; if neither
    exists the request is aborted with a 404. Retrieves up to 200 top LP
    positions for the resolved pair and renders the "lp_detail.html" template
    with `token_pair`, `pool`, and `positions`.

    Parameters:
        base (str): Base token symbol from the URL.
        quote (str): Quote token symbol from the URL.

    Returns:
        A Flask response rendering the pool detail template (HTTP 200) or aborts with 404 if the pool is not found.
    """
    base_u = base.upper().strip()
    quote_u = quote.upper().strip()
    token_pair = f"{base_u}:{quote_u}"
    pool = get_lp_pool(token_pair)
    if not pool:
        # Try reversed pair if user swapped order in URL
        rev_pair = f"{quote_u}:{base_u}"
        pool = get_lp_pool(rev_pair)
        if pool:
            token_pair = rev_pair
        else:
            abort(404)

    # Fetch LP positions
    positions = get_lp_positions(token_pair, limit=200)

    # Normalize pool numeric fields to floats so Jinja formatting works consistently
    def _to_float(val):
        try:
            return float(val if val is not None else 0)
        except (ValueError, TypeError):
            return 0.0

    pool_numeric = dict(pool) if isinstance(pool, dict) else {}
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
        "lp_detail.html",
        token_pair=token_pair,
        pool=pool_numeric,
        positions=positions,
    )


@app.route("/api/chart/<token>/<timeframe>")
def api_chart(token, timeframe):
    """
    Return chart data (Plotly JSON) for a token's market history for a given timeframe.

    Parameters:
        token (str): Token symbol to fetch market data for.
        timeframe (str): Either "all" to request the full history or an integer number of days
            (as a string). Non-integer values default to 30 days.

    Returns:
        tuple[str, int, dict]: A 3-tuple compatible with Flask responses:
            - body: JSON string containing a Plotly Figure (generated with PlotlyJSONEncoder).
            - status: HTTP status code (200 on success, 404 if the token is invalid).
            - headers: Response headers (includes "Content-Type": "application/json").

    Behavior:
        - Validates the token via get_token_info; returns a 404 JSON error if the token is invalid.
        - Interprets `timeframe` ("all" => full history; integer => last N days; invalid => 30).
        - Fetches market data and builds a candlestick Plotly figure; if no market data exists,
          returns a placeholder figure indicating "No Data Available".
        - On unexpected errors returns a Plotly figure containing an error annotation (HTTP 200).
    """
    try:
        # Validate token first
        token_info = get_token_info(token)
        if not token_info:
            return (
                json.dumps({"error": "Invalid token"}),
                404,
                {"Content-Type": "application/json"},
            )

        # Determine days based on timeframe
        if timeframe == "all":
            days = None
        else:
            try:
                days = int(timeframe)
            except ValueError:
                days = 30  # Default to 30 days

        # Get market data
        market_data = get_market_data(
            token, days=days if days else 365 * 5
        )  # Use large number for "all"

        if not market_data:
            # Create a simple empty chart so the frontend can still display something
            fig = go.Figure()
            fig.update_layout(
                title=f"{token}/SWAP.HIVE Market Data - No Data Available",
                xaxis_title="Date",
                yaxis_title="Price (HIVE)",
                annotations=[
                    dict(
                        text="No market data available for this timeframe",
                        showarrow=False,
                        xref="paper",
                        yref="paper",
                        x=0.5,
                        y=0.5,
                    )
                ],
            )
            chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
            return chart_json, 200, {"Content-Type": "application/json"}

        # Process data and create chart
        df = pd.DataFrame(market_data)

        # Convert timestamp to datetime
        if df["timestamp"].max() > 1000000000000:  # Likely milliseconds if > 2001-09-09
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")

        # Filter the dataframe if not all time
        if days is not None:
            start_date = pd.Timestamp.now() - pd.Timedelta(days=days)
            df = df[df["timestamp"] >= start_date]

        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df["timestamp"],
                    open=df["openPrice"],
                    high=df["highestPrice"],
                    low=df["lowestPrice"],
                    close=df["closePrice"],
                    increasing_line=dict(color="#26a69a", width=2),
                    decreasing_line=dict(color="#ef5350", width=2),
                    increasing_fillcolor="#26a69a",
                    decreasing_fillcolor="#ef5350",
                )
            ]
        )

        fig.update_layout(
            title=f"{token}/SWAP.HIVE Market Data",
            xaxis_title="Date",
            yaxis_title="Price (HIVE)",
            xaxis_rangeslider_visible=False,
            margin=dict(l=50, r=50, t=50, b=50),
            height=500,
            hovermode="x unified",
            xaxis=dict(
                showgrid=True,
                gridcolor="#e9ecef",
                linecolor="#ced4da",
                tickcolor="#ced4da",
            ),
            yaxis=dict(
                showgrid=True,
                gridcolor="#e9ecef",
                linecolor="#ced4da",
                tickcolor="#ced4da",
            ),
        )

        chart_json = json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder)
        return chart_json, 200, {"Content-Type": "application/json"}

    except Exception as e:
        app.logger.error(f"Error generating chart: {str(e)}")
        # Return a valid JSON with error message
        error_fig = go.Figure()
        error_fig.update_layout(
            title="Error Loading Chart",
            annotations=[
                dict(
                    text="An error occurred while loading the chart data",
                    showarrow=False,
                    xref="paper",
                    yref="paper",
                    x=0.5,
                    y=0.5,
                )
            ],
        )
        error_json = json.dumps(error_fig, cls=plotly.utils.PlotlyJSONEncoder)
        return error_json, 200, {"Content-Type": "application/json"}


@app.route("/api/orderbook/<token>")
def api_orderbook(token):
    """API endpoint that returns complete order book data for a specific token."""
    try:
        # Get filter parameters
        excluded_accounts = request.args.get("exclude", "").split(",")
        excluded_accounts = [
            account.strip() for account in excluded_accounts if account.strip()
        ]

        # Initialize empty lists for buy and sell orders
        buy_orders = []
        sell_orders = []

        # Start with a reasonable page size
        limit = 100
        offset = 0

        # Get the first page of orders
        buy_page = he_market.get_buy_book(symbol=token, limit=limit)

        # Loop to get all buy orders
        while buy_page and len(buy_page) > 0:
            # Filter out excluded accounts if specified
            if excluded_accounts:
                filtered_orders = [
                    order
                    for order in buy_page
                    if order.get("account") not in excluded_accounts
                ]
                buy_orders.extend(filtered_orders)
            else:
                buy_orders.extend(buy_page)

            offset += len(buy_page)
            # Break if we got fewer than requested (last page)
            if len(buy_page) < limit:
                break
            # Get next page
            buy_page = he_market.get_buy_book(symbol=token, limit=limit, offset=offset)

        # Reset offset for sell orders
        offset = 0

        # Get the first page of sell orders
        sell_page = he_market.get_sell_book(symbol=token, limit=limit)

        # Loop to get all sell orders
        while sell_page and len(sell_page) > 0:
            # Filter out excluded accounts if specified
            if excluded_accounts:
                filtered_orders = [
                    order
                    for order in sell_page
                    if order.get("account") not in excluded_accounts
                ]
                sell_orders.extend(filtered_orders)
            else:
                sell_orders.extend(sell_page)

            offset += len(sell_page)
            # Break if we got fewer than requested (last page)
            if len(sell_page) < limit:
                break
            # Get next page
            sell_page = he_market.get_sell_book(
                symbol=token, limit=limit, offset=offset
            )

        # Get a list of most active accounts to help with filtering
        all_accounts = {}
        for order in buy_orders + sell_orders:
            account = order.get("account")
            if account:
                all_accounts[account] = all_accounts.get(account, 0) + 1

        # Sort accounts by order count
        most_active = [
            {"account": account, "count": count}
            for account, count in sorted(
                all_accounts.items(), key=lambda x: x[1], reverse=True
            )[:10]
        ]

        return (
            {
                "buy_book": buy_orders,
                "sell_book": sell_orders,
                "most_active_accounts": most_active,
                "excluded_accounts": excluded_accounts,
            },
            200,
            {"Content-Type": "application/json"},
        )

    except Exception as e:
        app.logger.error(f"Error getting order book: {str(e)}")
        return {"error": "Error retrieving order book"}, 500


@app.route("/market/<token>")
@cache.cached(timeout=300)
def market(token):
    """Display market data for a specific token."""
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    # Get buy and sell book for rendering - API will fetch complete books
    try:
        buy_book = he_market.get_buy_book(symbol=token)
    except Exception as e:
        app.logger.error(f"Error getting buy book for {token}: {str(e)}")
        buy_book = []

    try:
        sell_book = he_market.get_sell_book(symbol=token)
    except Exception as e:
        app.logger.error(f"Error getting sell book for {token}: {str(e)}")
        sell_book = []

    # Get trade history for the last 30 days, with a larger limit
    trade_history = get_trade_history(token, limit=500, days=30)

    return render_template(
        "market.html",
        token=token,
        token_info=token_info,
        buy_book=buy_book,
        sell_book=sell_book,
        trade_history=trade_history,
    )


@app.route("/view/<token>")
@cache.cached(timeout=900)
def view(token):
    """Display token information and richlist."""
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    try:
        richlist, burned_balance = get_richlist(token)
    except RuntimeError:
        # Be resilient: show the page without richlist instead of failing with 503
        app.logger.warning(
            f"Richlist temporarily unavailable for {token}; rendering page without it.",
        )
        richlist = []
        burned_balance = 0.0

    # Calculate burned percentage if supply is available
    burned_percentage = 0.0
    if token_info.get("supply"):
        try:
            supply = float(token_info["supply"])
            if supply > 0:
                burned_percentage = (burned_balance / supply) * 100
        except (ValueError, TypeError):
            pass

    # Show only top 100 holders by default
    top_richlist = richlist[:100]
    return render_template(
        "view.html",
        token=token,
        token_info=token_info,
        richlist=top_richlist,
        burned_balance=burned_balance,
        burned_percentage=burned_percentage,
    )


@app.route("/favicon.ico")
def favicon():
    """Serve the favicon."""
    return redirect(url_for("static", filename="images/favicon.ico"))


@app.route("/richlist/<token>")
@cache.cached(timeout=900)
def full_richlist(token):
    token_info = get_token_info(token)
    if not token_info:
        abort(404)
    try:
        richlist, burned_balance = get_richlist(token)
    except RuntimeError:
        return render_template(
            "error_generic.html",
            code="503 - Service Unavailable",
            message="Richlist temporarily unavailable. Please try again later.",
        ), 503

    return render_template(
        "richlist_full.html",
        token=token,
        token_info=token_info,
        richlist=richlist,
        burned_balance=burned_balance,
    )


@app.route("/richlist/<token>/csv")
@cache.cached(timeout=900)
def export_richlist_csv(token):
    try:
        richlist, _ = get_richlist(token)
    except RuntimeError:
        abort(503)

    def generate():
        # Get token_info for percentage calculation
        token_info = get_token_info(token)
        try:
            total_supply = float(token_info.get("supply", 1))
        except Exception:
            total_supply = 1
        data = [
            [
                "Rank",
                "Account",
                "Balance",
                "Stake",
                "Pending Unstake",
                "Delegations In",
                "Delegations Out",
                "Pending Undelegation",
                "Total",
                "Percentage",
            ]
        ]
        for idx, holder in enumerate(richlist, 1):
            balance = float(holder.get("balance", 0) or 0)
            stake = float(holder.get("stake", 0) or 0)
            pending_unstake = float(holder.get("pendingUnstake", 0) or 0)
            delegations_in = float(holder.get("delegationsIn", 0) or 0)
            delegations_out = float(holder.get("delegationsOut", 0) or 0)
            pending_undelegation = float(holder.get("pendingUndelegations", 0) or 0)
            total = balance + stake
            percentage = (total / total_supply * 100) if total_supply else 0
            data.append(
                [
                    idx,
                    holder.get("account", ""),
                    f"{balance:.8f}",
                    f"{stake:.8f}",
                    f"{pending_unstake:.8f}",
                    f"{delegations_in:.8f}",
                    f"{delegations_out:.8f}",
                    f"{pending_undelegation:.8f}",
                    f"{total:.8f}",
                    f"{percentage:.2f}",
                ]
            )
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(data)
        return output.getvalue()

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={token}_richlist.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True, port=9000)
