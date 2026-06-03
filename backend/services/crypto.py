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
        return ccxt.binance({"enableRateLimit": True, "timeout": 5000})
    except Exception:
        pass
    try:
        import ccxt
        return ccxt.okx({"enableRateLimit": True, "timeout": 5000})
    except Exception:
        return None


def _fetch_ticker_binance(sym: str) -> dict | None:
    try:
        import requests
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym.replace('-','')}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "last": float(data.get("lastPrice", 0)),
                "open": float(data.get("openPrice", 0)),
                "high": float(data.get("highPrice", 0)),
                "low": float(data.get("lowPrice", 0)),
                "baseVolume": float(data.get("volume", 0)),
                "percentage": float(data.get("priceChangePercent", 0)),
            }
    except Exception:
        pass
    return None


def _fetch_ticker_okx(sym: str) -> dict | None:
    try:
        import requests
        inst = sym.replace("-", "-")  # BTC-USDT
        url = f"https://www.okx.com/api/v5/market/ticker?instId={inst}"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            data = resp.json().get("data", [{}])[0]
            return {
                "last": float(data.get("last", 0)),
                "open": float(data.get("open24h", 0)),
                "high": float(data.get("high24h", 0)),
                "low": float(data.get("low24h", 0)),
                "baseVolume": float(data.get("vol24h", 0)),
                "percentage": 0,
            }
    except Exception:
        pass
    return None


def _fetch_ticker_http(sym: str) -> dict | None:
    return _fetch_ticker_binance(sym) or _fetch_ticker_okx(sym)


@retry_on_rate_limit
def get_crypto_info(symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    exchange = _get_client()
    if not exchange:
        http_data = _fetch_ticker_http(sym)
        return _build_crypto_info(sym, http_data)

    try:
        ticker = exchange.fetch_ticker(sym)
        return _build_crypto_info(sym, ticker)
    except Exception:
        pass

    http_data = _fetch_ticker_http(sym)
    return _build_crypto_info(sym, http_data)


def _build_crypto_info(sym: str, ticker: dict | None) -> dict[str, Any]:
    name = sym  # Full trading pair
    return {
        "symbol": name,
        "full_symbol": sym,
        "name": name,
        "current_price": ticker.get("last") if ticker else None,
        "previous_close": ticker.get("open") if ticker else None,
        "day_high": ticker.get("high") if ticker else None,
        "day_low": ticker.get("low") if ticker else None,
        "volume": ticker.get("baseVolume") if ticker else None,
        "change_24h": ticker.get("percentage") if ticker else None,
        "market_cap": ticker.get("info", {}).get("marketCap") if ticker and isinstance(ticker.get("info"), dict) else None,
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
        "raw_info": ticker or {},
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

    sparkline = _fetch_sparkline(symbol)
    return {
        "symbol": info["symbol"],
        "price": info["current_price"],
        "change_5m": None,
        "sparkline": sparkline,
    }


def _fetch_sparkline(symbol: str) -> list[float]:
    """Get today's intraday prices from Binance or OKX."""
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"
    try:
        import requests
        # Binance
        url = f"https://api.binance.com/api/v3/klines?symbol={sym.replace('-','')}&interval=5m&limit=80"
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return [float(c[4]) for c in resp.json()]
        # OKX
        url2 = f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar=5m&limit=80"
        resp2 = requests.get(url2, timeout=3)
        if resp2.status_code == 200:
            data = resp2.json().get("data", [])
            return [float(c[4]) for c in reversed(data)]
    except Exception:
        pass
    return []


def discover_crypto() -> list[str]:
    return CRYPTO_SYMBOLS
