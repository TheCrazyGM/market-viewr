import json
import re
from datetime import datetime
from urllib.parse import urlparse

import pandas as pd
import plotly
import plotly.graph_objects as go
import requests
from flask import Flask, abort, redirect, render_template, request, url_for
from hiveengine.api import Api
from hiveengine.market import Market
from werkzeug.exceptions import HTTPException

app = Flask(__name__)


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
he_api = Api(url="https://engine.thecrazygm.com/")
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


# Get list of tokens
def get_tokens():
    tokens = he_api.find("tokens", "tokens")
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
    richlist = he_api.find(
        "tokens",
        "balances",
        query={"symbol": symbol},
        limit=100,
        indexes=[{"index": "balance", "descending": True}],
    )
    return richlist


# Get token market history
def get_trade_history(symbol, limit=20):
    try:
        # Use the Hive-Engine API to get trade history
        trades = he_market.get_trades_history(symbol=symbol, limit=limit)
        return trades
    except Exception:
        return []


# Routes
@app.route("/")
def index():
    """Display the homepage with a list of all tokens."""
    # Get all tokens
    tokens = get_tokens()

    # Parse metadata for each token
    for token in tokens:
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

    return render_template("index.html", tokens=tokens)


@app.route("/market/<token>/all")
@app.route("/market/<token>/<int:days>")
@app.route("/market/<token>")
def market(token, days=30):
    """Display market data for a specific token."""
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    # Get market data with the specified timeframe
    market_data = get_market_data(token, days=days)

    # Get buy and sell book
    buy_book = he_market.get_buy_book(symbol=token)
    sell_book = he_market.get_sell_book(symbol=token)

    # Get trade history
    trade_history = get_trade_history(token)

    # Create candlestick chart
    if market_data:
        try:
            df = pd.DataFrame(market_data)
            # Convert timestamp to datetime
            # Check if timestamp appears to be in milliseconds
            if (
                df["timestamp"].max() > 1000000000000
            ):  # Likely milliseconds if > 2001-09-09
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            else:
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")

            # Check if we should show all data or filter by days
            is_all_time = request.path.endswith("/all")

            if not is_all_time:
                # Filter the dataframe to only show the requested timespan
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
        except Exception:
            chart_json = None
    else:
        chart_json = None

    return render_template(
        "market.html",
        token=token,
        token_info=token_info,
        chart_json=chart_json,
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

    richlist = get_richlist(token)

    return render_template(
        "view.html", token=token, token_info=token_info, richlist=richlist
    )


@app.route("/favicon.ico")
def favicon():
    """Serve the favicon."""
    return redirect(url_for("static", filename="images/favicon.ico"))


if __name__ == "__main__":
    app.run(debug=True, port=9000)
