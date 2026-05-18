import json
import logging
import random

import requests
from nectarengine.api import Api
from nectarengine.market import Market
from requests.adapters import HTTPAdapter, Retry

logger = logging.getLogger(__name__)


def get_engine_nodes(max_nodes=10, timeout=3):
    """Return a list of healthy Hive-Engine RPC nodes."""
    payload = {
        "jsonrpc": "2.0",
        "method": "database_api.find_accounts",
        "params": {"accounts": ["flowerengine"]},
        "id": 1,
    }
    hive_api_nodes = [
        "https://api.hive.blog",
        "https://api.syncad.com",
        "https://anyx.io",
    ]
    nodes = []
    for hive_node in hive_api_nodes:
        try:
            resp = requests.post(hive_node, json=payload, timeout=5)
            resp.raise_for_status()
            data = resp.json()
            meta_str = (
                data.get("result", {})
                .get("accounts", [{}])[0]
                .get("json_metadata", "{}")
            )
            meta = json.loads(meta_str) if meta_str else {}
            nodes = meta.get("nodes", [])
            if nodes:
                break
        except Exception as e:
            logger.warning(f"Failed to fetch node list from {hive_node}: {e}")
            continue

    if not isinstance(nodes, list):
        nodes = []

    healthy_nodes = []
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
                if isinstance(res, dict) and res.get("blockNumber"):
                    healthy_nodes.append(node)
        except Exception:
            continue

    fallback = "https://enginerpc.com/"
    if fallback not in healthy_nodes:
        healthy_nodes.append(fallback)
    return healthy_nodes


# API instances and session
session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

_nodes = None


def get_nodes():
    global _nodes
    if _nodes is None:
        _nodes = get_engine_nodes()
    return _nodes


def get_he_api():
    nodes = get_nodes()
    return Api(
        url=random.choice(nodes) if nodes else "https://enginerpc.com/",
        timeout=30,
        session=session,
    )


def get_he_market():
    return Market(api=get_he_api())


class _LazyProxy:
    def __init__(self, factory):
        self._factory = factory

    def __getattr__(self, item):
        return getattr(self._factory(), item)


he_api = _LazyProxy(get_he_api)
he_market = _LazyProxy(get_he_market)
