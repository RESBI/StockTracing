import math
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np
import yfinance as yf

from backend.config import INDICATOR_PARAMS, TTL
from backend.database.models import AnalysisCache
from backend.database.deps import db_session
from backend.utils.logger import logger


def _get_hist_data(symbol: str, period: str = "1y") -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    ticker = yf.Ticker(symbol.upper().strip())
    df = ticker.history(period=period)
    if df.empty:
        raise ValueError(f"No price data for {symbol}")
    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    volumes = df["Volume"].values
    opens = df["Open"].values
    return closes, highs, lows, volumes, opens


def _sma(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    for i in range(period - 1, len(data)):
        result[i] = np.mean(data[i - period + 1 : i + 1])
    return result


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.full(len(data), np.nan)
    result[period - 1] = np.mean(data[:period])
    multiplier = 2 / (period + 1)
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def _round_arr(arr: np.ndarray) -> list:
    return [round(float(x), 4) if not math.isnan(x) else None for x in arr]


def calculate_all_indicators(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()

    with db_session() as db:
        row = db.query(AnalysisCache).filter(
            AnalysisCache.symbol == sym,
            AnalysisCache.analysis_type == "full_indicators",
        ).first()
        if row and row.updated_at:
            age = (time.time() - row.updated_at.timestamp())
            if age < TTL.INDICATORS:
                return row.data

    closes, highs, lows, volumes, opens = _get_hist_data(symbol)

    p = INDICATOR_PARAMS
    result: dict[str, Any] = {"symbol": symbol.upper()}

    # --- Moving Averages ---
    sma_short = _sma(closes, p["sma"]["short"])
    sma_long = _sma(closes, p["sma"]["long"])
    sma_signal = _sma(closes, p["sma"]["signal"])
    result["sma"] = {
        f"sma_{p['sma']['short']}": _round_arr(sma_short),
        f"sma_{p['sma']['long']}": _round_arr(sma_long),
        f"sma_{p['sma']['signal']}": _round_arr(sma_signal),
    }

    ema_fast_arr = _ema(closes, p["ema"]["fast"])
    ema_slow_arr = _ema(closes, p["ema"]["slow"])
    ema_signal_arr = _ema(closes, p["ema"]["signal"])
    result["ema"] = {
        f"ema_{p['ema']['fast']}": _round_arr(ema_fast_arr),
        f"ema_{p['ema']['slow']}": _round_arr(ema_slow_arr),
        f"ema_{p['ema']['signal']}": _round_arr(ema_signal_arr),
    }

    # --- RSI ---
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
    result["rsi"] = _round_arr(rsi)

    # --- MACD ---
    ema_12 = _ema(closes, p["macd"]["fast"])
    ema_26 = _ema(closes, p["macd"]["slow"])
    macd_line = ema_12 - ema_26
    macd_signal = _ema(macd_line, p["macd"]["signal"])
    macd_histogram = macd_line - macd_signal
    result["macd"] = {
        "macd_line": _round_arr(macd_line),
        "signal_line": _round_arr(macd_signal),
        "histogram": _round_arr(macd_histogram),
    }

    # --- Bollinger Bands ---
    bb_period = p["bollinger"]["period"]
    bb_std = p["bollinger"]["std"]
    middle = _sma(closes, bb_period)
    std_arr = np.full(len(closes), np.nan)
    for i in range(bb_period - 1, len(closes)):
        std_arr[i] = np.std(closes[i - bb_period + 1 : i + 1])
    upper = middle + bb_std * std_arr
    lower = middle - bb_std * std_arr
    result["bollinger"] = {
        "upper": _round_arr(upper),
        "middle": _round_arr(middle),
        "lower": _round_arr(lower),
    }

    # --- ATR ---
    atr_period = p["atr"]["period"]
    tr = np.full(len(closes), np.nan)
    for i in range(1, len(closes)):
        tr[i] = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr = _sma(tr[1:], atr_period)
    atr_full = np.concatenate([np.full(1, np.nan), atr])
    result["atr"] = _round_arr(atr_full)

    # --- OBV ---
    obv = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            obv[i] = obv[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            obv[i] = obv[i - 1] - volumes[i]
        else:
            obv[i] = obv[i - 1]
    result["obv"] = [int(x) for x in obv]

    # --- Stochastic ---
    k_period = p["stochastic"]["k"]
    d_period = p["stochastic"]["d"]
    stoch_k = np.full(len(closes), np.nan)
    for i in range(k_period - 1, len(closes)):
        low_k = np.min(lows[i - k_period + 1 : i + 1])
        high_k = np.max(highs[i - k_period + 1 : i + 1])
        if high_k != low_k:
            stoch_k[i] = (closes[i] - low_k) / (high_k - low_k) * 100
    stoch_d = _sma(stoch_k, d_period)
    result["stochastic"] = {
        "k": _round_arr(stoch_k),
        "d": _round_arr(stoch_d),
    }

    # --- Latest close & signals ---
    latest_close = float(closes[-1])
    result["latest_price"] = round(latest_close, 2)
    result["signals"] = _generate_signals(result, closes, volumes, latest_close, rsi, macd_histogram, stoch_k, upper, lower, sma_short, sma_long)

    # Save to cache
    with db_session() as db2:
        try:
            existing = db2.query(AnalysisCache).filter(
                AnalysisCache.symbol == sym,
                AnalysisCache.analysis_type == "full_indicators",
            ).first()
            now = datetime.now(timezone.utc)
            if existing:
                existing.data = result
                existing.updated_at = now
            else:
                db2.add(AnalysisCache(symbol=sym, analysis_type="full_indicators",
                                      data=result, updated_at=now))
            db2.commit()
        except Exception as e:
            logger.warning("save indicators cache failed for %s: %s", sym, e)

    return result


def _generate_signals(
    indicators: dict,
    closes: np.ndarray,
    volumes: np.ndarray,
    latest: float,
    rsi: np.ndarray,
    macd_hist: np.ndarray,
    stoch_k: np.ndarray,
    bb_upper: np.ndarray,
    bb_lower: np.ndarray,
    sma_short: np.ndarray,
    sma_long: np.ndarray,
) -> list[dict[str, str]]:
    signals: list[dict[str, str]] = []
    p = INDICATOR_PARAMS

    last_rsi = rsi[-1] if not math.isnan(rsi[-1]) else None
    if last_rsi is not None:
        if last_rsi > p["rsi"]["overbought"]:
            signals.append({"indicator": "RSI", "signal": "sell", "detail": f"RSI={last_rsi:.1f} > {p['rsi']['overbought']} (超买)"})
        elif last_rsi < p["rsi"]["oversold"]:
            signals.append({"indicator": "RSI", "signal": "buy", "detail": f"RSI={last_rsi:.1f} < {p['rsi']['oversold']} (超卖)"})
        else:
            signals.append({"indicator": "RSI", "signal": "neutral", "detail": f"RSI={last_rsi:.1f} (中性)"})

    last_hist = macd_hist[-1] if not math.isnan(macd_hist[-1]) else None
    prev_hist = macd_hist[-2] if len(macd_hist) > 1 and not math.isnan(macd_hist[-2]) else None
    if last_hist is not None and prev_hist is not None:
        if prev_hist < 0 and last_hist > 0:
            signals.append({"indicator": "MACD", "signal": "buy", "detail": "MACD金叉 (柱状图由负转正)"})
        elif prev_hist > 0 and last_hist < 0:
            signals.append({"indicator": "MACD", "signal": "sell", "detail": "MACD死叉 (柱状图由正转负)"})
        else:
            signals.append({"indicator": "MACD", "signal": "neutral", "detail": f"MACD柱={last_hist:.4f}"})

    last_k = stoch_k[-1] if not math.isnan(stoch_k[-1]) else None
    if last_k is not None:
        if last_k > p["stochastic"]["overbought"]:
            signals.append({"indicator": "Stochastic", "signal": "sell", "detail": f"K={last_k:.1f} > {p['stochastic']['overbought']} (超买)"})
        elif last_k < p["stochastic"]["oversold"]:
            signals.append({"indicator": "Stochastic", "signal": "buy", "detail": f"K={last_k:.1f} < {p['stochastic']['oversold']} (超卖)"})
        else:
            signals.append({"indicator": "Stochastic", "signal": "neutral", "detail": f"K={last_k:.1f}"})

    if not math.isnan(bb_upper[-1]) and not math.isnan(bb_lower[-1]):
        if latest > bb_upper[-1]:
            signals.append({"indicator": "Bollinger", "signal": "sell", "detail": "价格突破上轨 (超买)"})
        elif latest < bb_lower[-1]:
            signals.append({"indicator": "Bollinger", "signal": "buy", "detail": "价格跌破下轨 (超卖)"})
        else:
            signals.append({"indicator": "Bollinger", "signal": "neutral", "detail": "价格在布林带内"})

    if len(sma_short) > 0 and len(sma_long) > 0:
        last_short = sma_short[-1]
        last_long = sma_long[-1]
        prev_short = sma_short[-2] if len(sma_short) > 1 else None
        prev_long = sma_long[-2] if len(sma_long) > 1 else None
        if not math.isnan(last_short) and not math.isnan(last_long):
            if prev_short is not None and prev_long is not None and not math.isnan(prev_short) and not math.isnan(prev_long):
                if prev_short <= prev_long and last_short > last_long:
                    signals.append({"indicator": "MA Cross", "signal": "buy", "detail": f"SMA{p['sma']['short']}上穿SMA{p['sma']['long']} (金叉)"})
                elif prev_short >= prev_long and last_short < last_long:
                    signals.append({"indicator": "MA Cross", "signal": "sell", "detail": f"SMA{p['sma']['short']}下穿SMA{p['sma']['long']} (死叉)"})

    # Volume surge
    avg_vol = np.mean(volumes[-20:]) if len(volumes) >= 20 else np.mean(volumes)
    last_vol = volumes[-1]
    if last_vol > avg_vol * 1.5:
        signals.append({"indicator": "Volume", "signal": "buy", "detail": f"成交量放大 (当前={int(last_vol):,}, 均值={int(avg_vol):,})"})

    # Composite Score
    buy_count = sum(1 for s in signals if s["signal"] == "buy")
    sell_count = sum(1 for s in signals if s["signal"] == "sell")
    if buy_count > sell_count:
        signals.append({"indicator": "综合评分", "signal": "buy", "detail": f"买入信号{buy_count}个 vs 卖出信号{sell_count}个"})
    elif sell_count > buy_count:
        signals.append({"indicator": "综合评分", "signal": "sell", "detail": f"卖出信号{sell_count}个 vs 买入信号{buy_count}个"})
    else:
        signals.append({"indicator": "综合评分", "signal": "neutral", "detail": "信号中性，建议观望"})

    return signals


def get_period_analysis(symbol: str) -> dict[str, Any]:
    closes, highs, lows, volumes, opens = _get_hist_data(symbol, "1y")
    n = len(closes)
    if n < 20:
        return {"changes": {}, "signals": {}}

    p = INDICATOR_PARAMS
    result: dict[str, Any] = {"symbol": symbol.upper()}

    # Period: lookback days -> [data_window_days, trend_sma_period]
    # data_window: how many days of data to feed into analysis
    # trend_sma: SMA period used for short-term trend vs longer SMA
    periods_cfg = {
        "D": (20, 5),
        "W": (40, 10),
        "M": (80, 30),
        "Y": (min(252, n), 100),
    }

    changes = {}
    signals_summary = {}

    for label, (window, trend_period) in periods_cfg.items():
        lookback = {"D": 1, "W": 5, "M": 21, "Y": min(252, n - 1)}[label]
        if lookback >= n:
            lookback = n - 1
        if lookback < 1:
            continue

        # Price change
        start_price = float(closes[-lookback - 1]) if lookback < n else float(closes[0])
        end_price = float(closes[-1])
        change_pct = round((end_price - start_price) / start_price * 100, 2) if start_price and start_price != 0 else 0

        # Signals from period-specific data window
        window = min(window, n)
        sub_c = closes[-window:]
        sub_v = volumes[-window:]
        signals = _quick_signals(sub_c, sub_v, p, trend_period)

        changes[label] = round(change_pct, 2)
        signals_summary[label] = signals

    result["changes"] = changes
    result["signals"] = signals_summary
    return result


def _quick_signals(closes: np.ndarray, volumes: np.ndarray, p: dict, trend_sma_period: int = 10) -> dict[str, str]:
    n = len(closes)
    if n < 15:
        return {"rsi": "neutral", "trend": "neutral", "volume": "neutral", "overall": "neutral"}

    # RSI using last 14+1 points
    rsi_period = p["rsi"]["period"]
    seg = closes[-rsi_period - 1:]
    delta = np.diff(seg, prepend=seg[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = float(np.mean(gain[1:]))
    avg_loss = float(np.mean(loss[1:]))
    rsi_val = 50.0
    if avg_loss > 0:
        rsi_val = float(100 - (100 / (1 + avg_gain / avg_loss)))
    rsi_sig = "buy" if rsi_val < p["rsi"]["oversold"] else ("sell" if rsi_val > p["rsi"]["overbought"] else "neutral")

    # Trend: close vs SMA(trend_sma_period) and SMA(trend_sma_period*2)
    t = min(trend_sma_period, n)
    sma_short = float(np.mean(closes[-t:]))
    t2 = min(trend_sma_period * 2, n)
    sma_long = float(np.mean(closes[-t2:]))
    trend_sig = "buy" if sma_short > sma_long else ("sell" if sma_short < sma_long else "neutral")

    # Volume
    vn = min(20, n)
    last_vol = float(volumes[-1])
    avg_vol = float(np.mean(volumes[-vn:]))
    if avg_vol > 0:
        ratio = last_vol / avg_vol
        if ratio > 1.3:
            vol_sig = "buy"
        elif ratio < 0.5:
            vol_sig = "sell"
        else:
            vol_sig = "neutral"
    else:
        vol_sig = "neutral"

    # Overall
    score = 0
    if rsi_sig == "buy": score += 1
    elif rsi_sig == "sell": score -= 1
    if trend_sig == "buy": score += 1
    elif trend_sig == "sell": score -= 1

    overall = "buy" if score > 0 else ("sell" if score < 0 else "neutral")

    return {"rsi": rsi_sig, "trend": trend_sig, "volume": vol_sig, "overall": overall}
