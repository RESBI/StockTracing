import json
from pathlib import Path
from backend.config import WATCHLIST_FILE


def load_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
    return []


def save_watchlist(symbols: list[str]) -> None:
    WATCHLIST_FILE.write_text(json.dumps(symbols, ensure_ascii=False, indent=2), encoding="utf-8")


def add_to_watchlist(symbol: str) -> list[str]:
    symbols = load_watchlist()
    sym = symbol.upper().strip()
    if sym not in symbols:
        symbols.append(sym)
        save_watchlist(symbols)
    return symbols


def remove_from_watchlist(symbol: str) -> list[str]:
    symbols = load_watchlist()
    sym = symbol.upper().strip()
    if sym in symbols:
        symbols.remove(sym)
        save_watchlist(symbols)
    return symbols
