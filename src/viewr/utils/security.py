import re
from urllib.parse import urlparse


def is_valid_image_url(url):
    """Lightweight validation that the URL looks safe for an image fetch."""
    if not url:
        return False

    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return False

        lowered = url.lower()
        if lowered.startswith("javascript:") or lowered.startswith("data:"):
            return False
        if "<script" in lowered or "onerror=" in lowered:
            return False

        return True
    except Exception:
        return False


def sanitize_symbol(symbol):
    """Sanitize a token symbol to prevent injection attacks."""
    if not symbol:
        return ""
    return re.sub(r"[^a-zA-Z0-9.\-_]", "", str(symbol))
