import time
from typing import Any

from backend.config import get_proxy_dict, retry_on_rate_limit

CRYPTO_SYMBOLS = [
    "BTC-USDT", "ETH-USDT", "SOL-USDT", "BNB-USDT", "XRP-USDT",
    "ADA-USDT", "DOGE-USDT", "AVAX-USDT", "DOT-USDT", "LINK-USDT",
    "MATIC-USDT", "UNI-USDT", "ATOM-USDT", "LTC-USDT", "ETC-USDT",
    "FIL-USDT", "APT-USDT", "ARB-USDT", "OP-USDT", "NEAR-USDT",
    "INJ-USDT", "SUI-USDT", "SEI-USDT", "TIA-USDT", "WLD-USDT",
    "ORDI-USDT", "SATS-USDT", "RATS-USDT", "PEPE-USDT", "SHIB-USDT",
]


# ======================== HTTP helpers (dual-source) ========================
def _http_get(url, timeout=3):
    try:
        import requests
        r = requests.get(url, timeout=timeout, proxies=get_proxy_dict())
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def _fetch_ticker_binance(sym: str) -> dict | None:
    data = _http_get(
        f"https://api.binance.com/api/v3/ticker/24hr?symbol={sym.replace('-','')}"
    )
    if data:
        return {
            "last": float(data.get("lastPrice", 0)),
            "open": float(data.get("openPrice", 0)),
            "high": float(data.get("highPrice", 0)),
            "low": float(data.get("lowPrice", 0)),
            "baseVolume": float(data.get("volume", 0)),
            "percentage": float(data.get("priceChangePercent", 0)),
        }
    return None


def _fetch_ticker_okx(sym: str) -> dict | None:
    data = _http_get(f"https://www.okx.com/api/v5/market/ticker?instId={sym}")
    if data:
        d = (data.get("data") or [{}])[0]
        return {
            "last": float(d.get("last", 0)),
            "open": float(d.get("open24h", 0)),
            "high": float(d.get("high24h", 0)),
            "low": float(d.get("low24h", 0)),
            "baseVolume": float(d.get("vol24h", 0)),
            "percentage": 0,
        }
    return None


def _fetch_ticker_http(sym: str) -> dict | None:
    return _fetch_ticker_binance(sym) or _fetch_ticker_okx(sym)


def _fetch_klines_binance(sym: str, interval: str = "1d", limit: int = 365) -> list | None:
    data = _http_get(
        f"https://api.binance.com/api/v3/klines?symbol={sym.replace('-','')}&interval={interval}&limit={limit}",
        timeout=5
    )
    return data


def _fetch_klines_okx(sym: str, interval: str = "1d", limit: int = 365) -> list | None:
    bar_map = {"1d": "1D", "5m": "5m", "1m": "1m", "1w": "1W"}
    bar = bar_map.get(interval, "1D")
    data = _http_get(
        f"https://www.okx.com/api/v5/market/candles?instId={sym}&bar={bar}&limit={limit}",
        timeout=5
    )
    if data:
        return list(reversed(data.get("data", [])))
    return None


def _fetch_klines(sym: str, interval: str = "1d", limit: int = 365) -> list | None:
    return _fetch_klines_binance(sym, interval, limit) or _fetch_klines_okx(sym, interval, limit)


# ======================== ccxt fallback ========================
def _get_ccxt():
    try:
        import ccxt
        return ccxt.binance({"enableRateLimit": True, "timeout": 5000})
    except Exception:
        pass
    try:
        import ccxt
        return ccxt.okx({"enableRateLimit": True, "timeout": 5000})
    except Exception:
        pass
    return None


# ======================== Info builders ========================
def _build_crypto_info(sym: str, ticker: dict | None) -> dict[str, Any]:
    name = sym
    return {
        "symbol": name, "full_symbol": sym, "name": name,
        "current_price": ticker.get("last") if ticker else None,
        "previous_close": ticker.get("open") if ticker else None,
        "day_high": ticker.get("high") if ticker else None,
        "day_low": ticker.get("low") if ticker else None,
        "volume": ticker.get("baseVolume") if ticker else None,
        "change_24h": ticker.get("percentage") if ticker else None,
        "market_cap": None,
        "recommendation": "", "target_mean_price": None, "target_high_price": None,
        "target_low_price": None, "number_of_analysts": 0,
        "pe_ratio": None, "eps": None, "dividend_yield": None, "beta": None,
        "sector": "加密货币", "industry": "数字货币",
        "raw_info": ticker or {},
    }


def _klines_to_history(rows: list) -> list[dict]:
    records = []
    for c in rows:
        records.append({
            "date": time.strftime("%Y-%m-%d", time.gmtime(float(c[0]) / 1000)),
            "open": round(float(c[1]), 4),
            "high": round(float(c[2]), 4),
            "low": round(float(c[3]), 4),
            "close": round(float(c[4]), 4),
            "volume": round(float(c[5]), 2),
        })
    return records


# ======================== Public API ========================
@retry_on_rate_limit
def get_crypto_info(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    # Try ccxt
    exchange = _get_ccxt()
    if exchange:
        try:
            ticker = exchange.fetch_ticker(sym)
            return _build_crypto_info(sym, ticker)
        except Exception:
            pass

    # Try HTTP
    ticker = _fetch_ticker_http(sym)
    return _build_crypto_info(sym, ticker)


def get_crypto_history(symbol: str, period: str = "6mo") -> list[dict]:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    limit_map = {"1d": 24, "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}
    limit = limit_map.get(period, 180)

    # Try ccxt
    exchange = _get_ccxt()
    if exchange:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, "1d", limit=limit)
            if ohlcv:
                return _klines_to_history([[c[0], c[1], c[2], c[3], c[4], c[5]] for c in ohlcv])
        except Exception:
            pass

    # Try HTTP
    rows = _fetch_klines(sym, "1d", limit)
    if rows:
        return _klines_to_history(rows)
    return []


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
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"
    rows = _fetch_klines(sym, "5m", 80)
    if rows:
        return [float(r[4]) for r in rows]
    return []


def get_crypto_periods(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    rows = _fetch_klines(sym, "1d", 500)
    if not rows:
        return {"changes": {}, "signals": {}}

    closes = [float(r[4]) for r in rows]
    if len(closes) < 10:
        return {"changes": {}, "signals": {}}

    import numpy as np

    def _quick(cl, period_days):
        seg = cl[-period_days:] if len(cl) >= period_days else cl
        n = len(seg)
        if n < 5:
            return "neutral"
        sma_short = float(np.mean(seg[-min(5, n):]))
        sma_long = float(np.mean(seg[-min(10, n):]))
        if sma_short > sma_long * 1.01:
            return "buy"
        elif sma_short < sma_long * 0.99:
            return "sell"
        return "neutral"

    changes = {}
    signals = {}
    lookbacks = {"D": 1, "W": 7, "M": 30, "Y": 365}
    windows = {"D": 7, "W": 14, "M": 60, "Y": 365}

    for label, lb in lookbacks.items():
        if lb >= len(closes):
            continue
        start = closes[-lb - 1]
        end = closes[-1]
        chg = round((end - start) / start * 100, 2) if start > 0 else 0
        changes[label] = chg
        w = min(windows[label], len(closes))
        sig = _quick(closes, w)
        signals[label] = {"rsi": sig, "trend": sig, "volume": "neutral", "overall": sig}

    return {"changes": changes, "signals": signals}


def get_crypto_indicators(symbol: str) -> dict[str, Any] | None:
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    rows = _fetch_klines(sym, "1d", 365)
    if not rows or len(rows) < 20:
        # Try ccxt
        exchange = _get_ccxt()
        if exchange:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, "1d", limit=365)
                if ohlcv:
                    rows = [[c[0], c[1], c[2], c[3], c[4], c[5]] for c in ohlcv]
            except Exception:
                pass

    if not rows or len(rows) < 20:
        return None

    import numpy as np
    from backend.config import INDICATOR_PARAMS
    from backend.services.technical import _generate_signals

    closes = np.array([float(r[4]) for r in rows])
    highs = np.array([float(r[2]) for r in rows])
    lows = np.array([float(r[3]) for r in rows])
    volumes = np.array([float(r[5]) for r in rows])

    p = INDICATOR_PARAMS

    def _sma(arr, period):
        result = np.full(len(arr), np.nan)
        for i in range(period - 1, len(arr)):
            result[i] = np.mean(arr[i - period + 1 : i + 1])
        return result

    def _ema(arr, period):
        result = np.full(len(arr), np.nan)
        result[period - 1] = np.mean(arr[:period])
        mult = 2 / (period + 1)
        for i in range(period, len(arr)):
            result[i] = (arr[i] - result[i - 1]) * mult + result[i - 1]
        return result

    def _round(arr):
        return [round(float(x), 4) if not np.isnan(x) else None for x in arr]

    result: dict[str, Any] = {"symbol": sym}

    sma_short = _sma(closes, p["sma"]["short"])
    sma_long = _sma(closes, p["sma"]["long"])
    sma_signal = _sma(closes, p["sma"]["signal"])
    result["sma"] = {f"sma_{p['sma']['short']}": _round(sma_short), f"sma_{p['sma']['long']}": _round(sma_long), f"sma_{p['sma']['signal']}": _round(sma_signal)}

    ema_12, ema_26 = _ema(closes, 12), _ema(closes, 26)
    macd_line = ema_12 - ema_26
    macd_signal = _ema(macd_line, 9)
    result["macd"] = {"macd_line": _round(macd_line), "signal_line": _round(macd_signal), "histogram": _round(macd_line - macd_signal)}

    period = p["rsi"]["period"]
    delta = np.diff(closes, prepend=closes[0])
    gain, loss = np.where(delta > 0, delta, 0.0), np.where(delta < 0, -delta, 0.0)
    avg_gain, avg_loss = np.full(len(closes), np.nan), np.full(len(closes), np.nan)
    avg_gain[period], avg_loss[period] = np.mean(gain[1:period+1]), np.mean(loss[1:period+1])
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i-1]*(period-1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i-1]*(period-1) + loss[i]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
    result["rsi"] = _round(100 - (100 / (1 + rs)))

    bb_period, bb_std = 20, 2
    middle = _sma(closes, bb_period)
    std_arr = np.full(len(closes), np.nan)
    for i in range(bb_period - 1, len(closes)):
        std_arr[i] = np.std(closes[i - bb_period + 1 : i + 1])
    result["bollinger"] = {"upper": _round(middle + bb_std * std_arr), "middle": _round(middle), "lower": _round(middle - bb_std * std_arr)}

    tr = np.full(len(closes), np.nan)
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
    result["atr"] = _round(np.concatenate([np.full(1, np.nan), _sma(tr[1:], 14)]))

    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        obv[i] = obv[i-1] + (volumes[i] if closes[i] > closes[i-1] else (-volumes[i] if closes[i] < closes[i-1] else 0))
    result["obv"] = [int(x) for x in obv]

    k_period = 14
    stoch_k = np.full(len(closes), np.nan)
    for i in range(k_period - 1, len(closes)):
        low_k, high_k = np.min(lows[i-k_period+1:i+1]), np.max(highs[i-k_period+1:i+1])
        if high_k != low_k:
            stoch_k[i] = (closes[i] - low_k) / (high_k - low_k) * 100
    stoch_d = _sma(stoch_k, 3)
    result["stochastic"] = {"k": _round(stoch_k), "d": _round(stoch_d)}

    latest_close = float(closes[-1])
    result["latest_price"] = round(latest_close, 4)
    result["signals"] = _generate_signals(result, closes, volumes, latest_close, result["rsi"], np.array(result["macd"]["histogram"]), stoch_k, np.array(result["bollinger"]["upper"]), np.array(result["bollinger"]["lower"]), sma_short, sma_long)

    return result


def discover_crypto() -> list[str]:
    return CRYPTO_SYMBOLS
