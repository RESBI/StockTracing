"""Symbol resolution utilities shared across routes and services.

Handles: crypto detection, crypto pair normalization, A-share suffix resolution.
"""
from backend.services.crypto import CRYPTO_SYMBOLS
from backend.services.stock_data import _resolve_asymbol


def is_crypto(symbol: str) -> bool:
    s = symbol.upper().strip()
    if s.startswith("CRYPTO:"):
        return True
    if "-USDT" in s or "-USD" in s:
        return True
    return any(s == c.split("-")[0] or s == c for c in CRYPTO_SYMBOLS)


def crypto_sym(symbol: str) -> str:
    """Strip CRYPTO: prefix, return clean trading pair (default -USDT)."""
    s = symbol.upper().strip()
    if s.startswith("CRYPTO:"):
        s = s[7:]
    if "-" not in s:
        s = s + "-USDT"
    return s


def resolve_sym(symbol: str) -> str:
    """Resolve A-share suffix and normalize; falls back to uppercased input."""
    r = _resolve_asymbol(symbol)
    return r if r else symbol.upper().strip()
