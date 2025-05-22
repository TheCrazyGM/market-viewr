import json
import logging
import re
import string
import time
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import plotly
import plotly.graph_objects as go
import requests
from flask import Flask, abort, redirect, render_template, request, url_for
from nectarengine.api import Api
from nectarengine.market import Market
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
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
    """Convert a Unix timestamp to a formatted date string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


# Hive Engine API endpoints for history API
HE_HISTORY_API = "https://history.hive-engine.com"

# Initialize hiveengine API
he_api = Api(url="https://enginerpc.com/")
he_market = Market(api=he_api)


# Validate if URL is an image
def is_valid_image_url(url):
    """Check if a URL points to a valid image."""
    if not url:
        return False

    # Basic URL validation
    try:
        result = urlparse(url)
        if not all([result.scheme, result.netloc]):
            return False

        # Check for common image extensions
        if not re.search(r"\.(jpg|jpeg|png|gif|svg|webp)$", url.lower()):
            return False

        # Check for potential script injection
        if re.search(r"<script|javascript:|data:|onerror=", url.lower()):
            return False

        return True
    except Exception:
        return False


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

        return token_info
    except Exception:
        return None


# Get token market data
def get_market_data(symbol, days=30):
    # Calculate timestamp in milliseconds
    timestamp_start = int((datetime.now().timestamp() - days * 24 * 60 * 60) * 1000)
    url = f"{HE_HISTORY_API}/marketHistory?symbol={symbol}&timestampStart={timestamp_start}"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        return data
    return []


# Get token richlist
def get_richlist(symbol):
    richlist = []
    burned_balance = 0.0
    page_size = 1000  # Use the maximum per-request limit
    prefixes = list(string.ascii_lowercase) + list(string.digits) + ["_"]
    seen_accounts = set()

    for prefix in prefixes:
        offset = 0
        while True:
            batch = he_api.find(
                "tokens",
                "balances",
                query={"symbol": symbol, "account": {"$regex": f"^{prefix}"}},
                limit=page_size,
                offset=offset,
                indexes=[{"index": "balance", "descending": True}],
            )
            if not batch:
                break
            for holder in batch:
                acct = holder.get("account")
                if acct == "null":
                    try:
                        burned_balance = float(holder.get("balance", 0))
                    except (ValueError, TypeError):
                        burned_balance = 0.0
                elif acct and acct not in seen_accounts:
                    richlist.append(holder)
                    seen_accounts.add(acct)
            if len(batch) < page_size:
                break
            offset += page_size

    # Filter and sort richlist by balance descending (as in the template)
    def get_balance(holder):
        try:
            return float(holder.get("balance", 0))
        except (ValueError, TypeError):
            return 0.0

    richlist.sort(key=get_balance, reverse=True)
    return richlist, burned_balance


# Get token market history
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
@app.route("/")
@app.route("/page/<int:page>")
def index(page=1):
    """Display the homepage with a list of all tokens with pagination and search."""
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


@app.route("/api/chart/<token>/<timeframe>")
def api_chart(token, timeframe):
    """API endpoint that returns chart data for a specific token with given timeframe."""
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
def view(token):
    """Display token information and richlist."""
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    richlist, burned_balance = get_richlist(token)

    # Calculate burned percentage if supply is available
    burned_percentage = 0.0
    if token_info.get("supply"):
        try:
            supply = float(token_info["supply"])
            if supply > 0:
                burned_percentage = (burned_balance / supply) * 100
        except (ValueError, TypeError):
            pass

    return render_template(
        "view.html",
        token=token,
        token_info=token_info,
        richlist=richlist,
        burned_balance=burned_balance,
        burned_percentage=burned_percentage,
    )


@app.route("/favicon.ico")
def favicon():
    """Serve the favicon."""
    return redirect(url_for("static", filename="images/favicon.ico"))


if __name__ == "__main__":
    app.run(debug=True, port=9000)
