import json
from datetime import datetime

import pandas as pd
import plotly
import plotly.graph_objects as go
import requests
from flask import Flask, redirect, render_template, url_for
from hiveengine.api import Api
from hiveengine.market import Market

app = Flask(__name__)


# Custom Jinja2 filter for formatting timestamps
@app.template_filter("timestamp_to_date")
def timestamp_to_date(timestamp):
    """Convert a Unix timestamp to a formatted date string."""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")


# Hive Engine API endpoints for history API
HE_HISTORY_API = "https://history.hive-engine.com"

# Initialize hiveengine API
he_api = Api(url="https://engine.thecrazygm.com/")
he_market = Market()


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
            except json.JSONDecodeError:
                # If metadata is not valid JSON, keep it as is
                pass

        return token_info
    except Exception as e:
        print(f"Error getting token info: {e}")
        return None


# Get token market data
def get_market_data(symbol, days=7):
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
    except Exception as e:
        print(f"Error fetching trade history for {symbol}: {e}")
        return []


# Routes
@app.route("/")
def index():
    # Get all tokens
    tokens = get_tokens()

    # Parse metadata for each token
    for token in tokens:
        if token and "metadata" in token and isinstance(token["metadata"], str):
            try:
                token["metadata"] = json.loads(token["metadata"])
            except json.JSONDecodeError:
                # If metadata is not valid JSON, keep it as is
                pass

    return render_template("index.html", tokens=tokens)


@app.route("/market/<token>")
def market(token):
    token_info = get_token_info(token)
    if not token_info:
        return redirect(url_for("index"))

    market_data = get_market_data(token)

    # Get buy and sell book
    buy_book = he_market.get_buy_book(symbol=token)
    sell_book = he_market.get_sell_book(symbol=token)

    # Get trade history
    trade_history = get_trade_history(token)

    # Create candlestick chart
    if market_data:
        df = pd.DataFrame(market_data)
        # Convert timestamp to datetime (timestamp is in seconds, not milliseconds)
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")

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
    token_info = get_token_info(token)
    if not token_info:
        return redirect(url_for("index"))

    richlist = get_richlist(token)

    return render_template(
        "view.html", token=token, token_info=token_info, richlist=richlist
    )


if __name__ == "__main__":
    app.run(debug=True, port=9000)
