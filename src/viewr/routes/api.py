import json
import logging
from datetime import datetime, timezone

import pandas as pd
import plotly.graph_objects as go
import plotly.utils
from flask import Blueprint, jsonify, request

from ..api.hive_engine import he_api, he_market
from ..extensions import cache
from ..services.market import get_market_data
from ..services.tokens import get_token_info
from ..utils.security import sanitize_symbol

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)


@api_bp.route("/health", methods=["GET"])
def health_check():
    status = {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "dependencies": {},
    }
    try:
        cache.set("healthcheck", "ok", timeout=5)
        status["dependencies"]["redis"] = "ok"
    except Exception as e:
        status["status"] = "error"
        status["dependencies"]["redis"] = f"error: {str(e)}"
    try:
        he_api.find_one("tokens", "tokens", query={})
        status["dependencies"]["hive_engine"] = "ok"
    except Exception as e:
        status["status"] = "error"
        status["dependencies"]["hive_engine"] = f"error: {str(e)}"
    return jsonify(status), 200 if status["status"] == "ok" else 503


@api_bp.route("/api/chart/<token>/<timeframe>")
def api_chart(token, timeframe):
    try:
        token = sanitize_symbol(token)
        token_info = get_token_info(token)
        if not token_info:
            return jsonify({"error": "Invalid token"}), 404
        days = 30
        if timeframe == "all":
            days = 365 * 5
        else:
            try:
                days = int(timeframe)
            except Exception:
                pass
        market_data = get_market_data(token, days=days)
        if not market_data:
            fig = go.Figure()
            fig.update_layout(
                title=f"{token}/SWAP.HIVE Market Data - No Data Available"
            )
            return (
                json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder),
                200,
                {"Content-Type": "application/json"},
            )
        df = pd.DataFrame(market_data)
        if df["timestamp"].max() > 1000000000000:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        else:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        fig = go.Figure(
            data=[
                go.Candlestick(
                    x=df["timestamp"],
                    open=df["openPrice"],
                    high=df["highestPrice"],
                    low=df["lowestPrice"],
                    close=df["closePrice"],
                )
            ]
        )
        fig.update_layout(
            title=f"{token}/SWAP.HIVE Market Data", xaxis_rangeslider_visible=False
        )
        return (
            json.dumps(fig, cls=plotly.utils.PlotlyJSONEncoder),
            200,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        logger.error(f"Error generating chart: {e}")
        return jsonify({"error": "Chart error"}), 500


@api_bp.route("/api/orderbook/<token>")
def api_orderbook(token):
    token = sanitize_symbol(token)
    try:
        excluded_accounts = [
            a.strip() for a in request.args.get("exclude", "").split(",") if a.strip()
        ]
        buy_orders = []
        sell_orders = []
        limit = 100
        offset = 0
        buy_page = he_market.get_buy_book(symbol=token, limit=limit)
        while buy_page:
            buy_orders.extend(
                [o for o in buy_page if o.get("account") not in excluded_accounts]
            )
            offset += len(buy_page)
            if len(buy_page) < limit:
                break
            buy_page = he_market.get_buy_book(symbol=token, limit=limit, offset=offset)
        offset = 0
        sell_page = he_market.get_sell_book(symbol=token, limit=limit)
        while sell_page:
            sell_orders.extend(
                [o for o in sell_page if o.get("account") not in excluded_accounts]
            )
            offset += len(sell_page)
            if len(sell_page) < limit:
                break
            sell_page = he_market.get_sell_book(
                symbol=token, limit=limit, offset=offset
            )
        return jsonify({"buy_book": buy_orders, "sell_book": sell_orders}), 200
    except Exception as e:
        logger.error(f"Error getting order book for {token}: {e}")
        return jsonify({"error": "Orderbook error"}), 500
