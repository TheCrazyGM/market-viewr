import csv
import io
import json
import logging

from flask import (
    Blueprint,
    Response,
    abort,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)

from ..api.hive_engine import he_market
from ..extensions import cache
from ..services.market import get_trade_history
from ..services.tokens import get_richlist, get_token_info, get_tokens
from ..utils.security import is_valid_image_url, sanitize_symbol

logger = logging.getLogger(__name__)

main_bp = Blueprint("main", __name__)


@main_bp.route("/robots.txt")
def robots_txt():
    return current_app.send_static_file("robots.txt")


@main_bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="images/favicon.ico"))


@main_bp.route("/")
@main_bp.route("/page/<int:page>")
@cache.cached(timeout=3600, query_string=True)
def index(page=1):
    search_query = request.args.get("q", "").lower()
    all_tokens = get_tokens()

    for token in all_tokens:
        if token and "metadata" in token and isinstance(token["metadata"], str):
            try:
                token["metadata"] = json.loads(token["metadata"])
                if token["metadata"] and "icon" in token["metadata"]:
                    if not is_valid_image_url(token["metadata"]["icon"]):
                        token["metadata"]["icon"] = None
            except json.JSONDecodeError:
                pass

    if search_query:
        all_tokens = [
            t
            for t in all_tokens
            if search_query in t.get("symbol", "").lower()
            or search_query in t.get("name", "").lower()
        ]

    per_page = 100
    total = len(all_tokens)
    offset = (page - 1) * per_page
    tokens = all_tokens[offset : offset + per_page]
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


@main_bp.route("/market/<token>")
@cache.cached(timeout=300)
def market(token):
    token = sanitize_symbol(token)
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    try:
        buy_book = he_market.get_buy_book(symbol=token)
    except Exception as e:
        logger.error(f"Error getting buy book for {token}: {e}")
        buy_book = []

    try:
        sell_book = he_market.get_sell_book(symbol=token)
    except Exception as e:
        logger.error(f"Error getting sell book for {token}: {e}")
        sell_book = []

    trade_history = get_trade_history(token, limit=500, days=30)
    return render_template(
        "market.html",
        token=token,
        token_info=token_info,
        buy_book=buy_book,
        sell_book=sell_book,
        trade_history=trade_history,
    )


@main_bp.route("/view/<token>")
@cache.cached(timeout=900)
def view(token):
    token = sanitize_symbol(token)
    token_info = get_token_info(token)
    if not token_info:
        abort(404)

    try:
        richlist, burned_balance = get_richlist(token)
    except RuntimeError:
        richlist, burned_balance = [], 0.0

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
        richlist=richlist[:100],
        burned_balance=burned_balance,
        burned_percentage=burned_percentage,
    )


@main_bp.route("/richlist/<token>")
@cache.cached(timeout=900)
def full_richlist(token):
    token = sanitize_symbol(token)
    token_info = get_token_info(token)
    if not token_info:
        abort(404)
    try:
        richlist, burned_balance = get_richlist(token)
    except RuntimeError:
        return render_template(
            "error_generic.html",
            code="503 - Service Unavailable",
            message="Richlist temporarily unavailable.",
        ), 503

    return render_template(
        "richlist_full.html",
        token=token,
        token_info=token_info,
        richlist=richlist,
        burned_balance=burned_balance,
    )


@main_bp.route("/richlist/<token>/csv")
@cache.cached(timeout=900)
def export_richlist_csv(token):
    token = sanitize_symbol(token)
    try:
        richlist, _ = get_richlist(token)
    except RuntimeError:
        abort(503)

    def generate():
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
            total = balance + stake
            percentage = (total / total_supply * 100) if total_supply else 0
            data.append(
                [
                    idx,
                    holder.get("account", ""),
                    f"{balance:.8f}",
                    f"{stake:.8f}",
                    f"{float(holder.get('pendingUnstake', 0) or 0):.8f}",
                    f"{float(holder.get('delegationsIn', 0) or 0):.8f}",
                    f"{float(holder.get('delegationsOut', 0) or 0):.8f}",
                    f"{float(holder.get('pendingUndelegations', 0) or 0):.8f}",
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
