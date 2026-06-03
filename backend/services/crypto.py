import time
from typing import Any

from backend.config import retry_on_rate_limit


CRYPTO_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
    "MATIC-USDT", "UNI-USDT", "ATOM-USDT", "LTC-USDT", "ETC-USDT",
    "FIL-USDT", "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT",
    "INJ-USDT", "SUI-USDT", "SEI-USDT", "TIA-USDT", "WLD-USDT",
    "ORDI-USDT", "SATS-USDT", "RATS-USDT", "PEPE-USDT", "SHIB-USDT",
]


def _get_client():
    try:
        import ccxt
        # Try Binance first (most accessible)
        return ccxt.binance({"enableRateLimit": True, "timeout": 10000})
    except Exception:
        pass
    try:
        import ccxt
        return ccxt.okx({"enableRateLimit": True, "timeout": 10000})
    except Exception:
        return None


@retry_on_rate_limit
def get_crypto_info(symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    exchange = _get_client()
    if not exchange:
        # Return minimal info when exchange unreachable
        name = sym.split("-")[0]
        return {
            "symbol": name,
            "full_symbol": sym,
            "name": name,
            "current_price": None,
            "previous_close": None,
            "day_high": None,
            "day_low": None,
            "volume": None,
            "change_24h": None,
            "market_cap": None,
            "recommendation": "",
            "target_mean_price": None,
            "target_high_price": None,
            "target_low_price": None,
            "number_of_analysts": 0,
            "pe_ratio": None,
            "eps": None,
            "dividend_yield": None,
            "beta": None,
            "sector": "加密货币",
            "industry": "数字货币",
            "raw_info": {},
        }

    try:
        ticker = exchange.fetch_ticker(sym)
        name = sym  # Full trading pair
        return {
            "symbol": name,
            "full_symbol": sym,
            "name": name,
            "current_price": ticker.get("last"),
            "previous_close": ticker.get("open"),
            "day_high": ticker.get("high"),
            "day_low": ticker.get("low"),
            "volume": ticker.get("baseVolume"),
            "change_24h": ticker.get("percentage"),
            "market_cap": ticker.get("info", {}).get("marketCap"),
            "recommendation": "",
            "target_mean_price": None,
            "target_high_price": None,
            "target_low_price": None,
            "number_of_analysts": 0,
            "pe_ratio": None,
            "eps": None,
            "dividend_yield": None,
            "beta": None,
            "sector": "加密货币",
            "industry": "数字货币",
            "raw_info": ticker,
        }
    except Exception:
        # Return minimal info when API call fails
        pass

    # Fallback: minimal info
    name = sym  # Full trading pair
    return {
        "symbol": name,
        "full_symbol": sym,
        "name": name,
        "current_price": None,
        "previous_close": None,
        "day_high": None,
        "day_low": None,
        "volume": None,
        "change_24h": None,
        "market_cap": None,
        "recommendation": "",
        "target_mean_price": None,
        "target_high_price": None,
        "target_low_price": None,
        "number_of_analysts": 0,
        "pe_ratio": None,
        "eps": None,
        "dividend_yield": None,
        "beta": None,
        "sector": "加密货币",
        "industry": "数字货币",
        "raw_info": {},
    }


def get_crypto_history(symbol: str, period: str = "30d") -> list[dict]:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    timeframe_map = {"1d": "1d", "1mo": "1d", "3mo": "1d", "6mo": "1d", "1y": "1d"}
    limit_map = {"1d": 24, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
    tf = timeframe_map.get(period, "1d")
    limit = limit_map.get(period, 180)

    exchange = _get_client()
    if not exchange:
        return []

    try:
        ohlcv = exchange.fetch_ohlcv(sym, tf, limit=limit)
        records = []
        for candle in ohlcv:
            records.append({
                "date": time.strftime("%Y-%m-%d", time.gmtime(candle[0] / 1000)),
                "open": round(candle[1], 4),
                "high": round(candle[2], 4),
                "low": round(candle[3], 4),
                "close": round(candle[4], 4),
                "volume": round(candle[5], 2),
            })
        return records
    except Exception:
        return []


@retry_on_rate_limit
def get_crypto_tick(symbol: str) -> dict | None:
    info = get_crypto_info(symbol)
    if not info:
        return None
    return {
        "symbol": info["symbol"],
        "price": info["current_price"],
        "change_5m": None,
    }


def discover_crypto() -> list[str]:
    return CRYPTO_SYMBOLS
