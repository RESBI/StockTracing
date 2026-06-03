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


def get_crypto_periods(symbol: str) -> dict[str, Any]:
    """Compute D/W/M/Y changes and signals for crypto using OHLCV data."""
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    # Fetch 1y of daily data
    closes = []
    try:
        import requests
        url = f"https://api.binance.com/api/v3/klines?symbol={sym.replace('-','')}&interval=1d&limit=365"
        resp = requests.get(url, timeout=8)
        if resp.status_code == 200:
            closes = [float(r[4]) for r in resp.json()]
    except Exception:
        pass

    if not closes:
        # Try ccxt
        exchange = _get_client()
        if exchange:
            try:
                ohlcv = exchange.fetch_ohlcv(sym, "1d", limit=365)
                closes = [c[4] for c in ohlcv]
            except Exception:
                pass

    if len(closes) < 20:
        return {"changes": {}, "signals": {}}

    import numpy as np
    from backend.config import INDICATOR_PARAMS
    p = INDICATOR_PARAMS

    def _quick(cl, period_days):
        """Quick buy/sell/neutral signal for a lookback window."""
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

    result = {"changes": changes, "signals": signals}
    return result


def get_crypto_indicators(symbol: str) -> dict[str, Any] | None:
    """Fetch OHLCV and compute full technical indicators for crypto."""
    sym = symbol.upper().strip()
    if "-" not in sym:
        sym = sym + "-USDT"

    # Try ccxt first for 1y daily data
    data = None
    exchange = _get_client()
    if exchange:
        try:
            ohlcv = exchange.fetch_ohlcv(sym, "1d", limit=365)
            if ohlcv:
                data = {
                    "closes": [c[4] for c in ohlcv],
                    "highs": [c[2] for c in ohlcv],
                    "lows": [c[3] for c in ohlcv],
                    "volumes": [c[5] for c in ohlcv],
                    "opens": [c[1] for c in ohlcv],
                }
        except Exception:
            pass

    # Fallback: Binance HTTP klines
    if not data:
        try:
            import requests
            bin_sym = sym.replace("-", "")
            url = f"https://api.binance.com/api/v3/klines?symbol={bin_sym}&interval=1d&limit=365"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                rows = resp.json()
                data = {
                    "closes": [float(r[4]) for r in rows],
                    "highs": [float(r[2]) for r in rows],
                    "lows": [float(r[3]) for r in rows],
                    "volumes": [float(r[5]) for r in rows],
                    "opens": [float(r[1]) for r in rows],
                }
        except Exception:
            pass

    if not data or len(data["closes"]) < 20:
        return None

    import numpy as np
    from backend.config import INDICATOR_PARAMS
    from backend.services.technical import _generate_signals
    closes = np.array(data["closes"])
    highs = np.array(data["highs"])
    lows = np.array(data["lows"])
    volumes = np.array(data["volumes"])
    opens = np.array(data["opens"])

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

    # SMA
    sma_short = _sma(closes, p["sma"]["short"])
    sma_long = _sma(closes, p["sma"]["long"])
    sma_signal = _sma(closes, p["sma"]["signal"])
    result["sma"] = {f"sma_{p['sma']['short']}": _round(sma_short), f"sma_{p['sma']['long']}": _round(sma_long), f"sma_{p['sma']['signal']}": _round(sma_signal)}

    # EMA / MACD
    ema_12 = _ema(closes, 12)
    ema_26 = _ema(closes, 26)
    macd_line = ema_12 - ema_26
    macd_signal = _ema(macd_line, 9)
    macd_histogram = macd_line - macd_signal
    result["macd"] = {"macd_line": _round(macd_line), "signal_line": _round(macd_signal), "histogram": _round(macd_histogram)}

    # RSI
    period = p["rsi"]["period"]
    delta = np.diff(closes, prepend=closes[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = np.full(len(closes), np.nan)
    avg_loss = np.full(len(closes), np.nan)
    avg_gain[period] = np.mean(gain[1 : period + 1])
    avg_loss[period] = np.mean(loss[1 : period + 1])
    for i in range(period + 1, len(closes)):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gain[i]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + loss[i]) / period
    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
    rsi = 100 - (100 / (1 + rs))
    result["rsi"] = _round(rsi)

    # Bollinger
    bb_period = 20
    middle = _sma(closes, bb_period)
    std_arr = np.full(len(closes), np.nan)
    for i in range(bb_period - 1, len(closes)):
        std_arr[i] = np.std(closes[i - bb_period + 1 : i + 1])
    upper = middle + 2 * std_arr
    lower = middle - 2 * std_arr
    result["bollinger"] = {"upper": _round(upper), "middle": _round(middle), "lower": _round(lower)}

    # ATR
    tr = np.full(len(closes), np.nan)
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = np.concatenate([np.full(1, np.nan), _sma(tr[1:], 14)])
    result["atr"] = _round(atr)

    # OBV
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    result["obv"] = [int(x) for x in obv]

    # Stochastic
    k_period = 14
    stoch_k = np.full(len(closes), np.nan)
    for i in range(k_period - 1, len(closes)):
        low_k = np.min(lows[i - k_period + 1 : i + 1])
        high_k = np.max(highs[i - k_period + 1 : i + 1])
        if high_k != low_k:
            stoch_k[i] = (closes[i] - low_k) / (high_k - low_k) * 100
    stoch_d = _sma(stoch_k, 3)
    result["stochastic"] = {"k": _round(stoch_k), "d": _round(stoch_d)}

    latest_close = float(closes[-1])
    result["latest_price"] = round(latest_close, 4)
    result["signals"] = _generate_signals(result, closes, volumes, latest_close, rsi, macd_histogram, stoch_k, upper, lower, sma_short, sma_long)

    return result
