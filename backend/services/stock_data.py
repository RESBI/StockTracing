from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from sqlalchemy.orm import Session

from backend.config import CACHE_TTL_SECONDS, TTL, retry_on_rate_limit
from backend.database.models import StockCache
from backend.database.deps import db_session
from backend.utils.logger import logger
from backend.utils.circuit_breaker import circuit


def _is_cache_fresh(record: StockCache | None) -> bool:
    if not record or not record.updated_at:
        return False
    updated = record.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - updated).total_seconds()
    return age < CACHE_TTL_SECONDS


@circuit("yfinance", failure_threshold=5, recovery_timeout=60)
@retry_on_rate_limit
def _fetch_info(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}
    return {
        "symbol": ticker.ticker.upper(),
        "name": info.get("longName") or info.get("shortName", ""),
        "sector": info.get("sector", ""),
        "industry": info.get("industry", ""),
        "market_cap": info.get("marketCap"),
        "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
        "previous_close": info.get("previousClose") or info.get("regularMarketPreviousClose"),
        "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
        "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
        "volume": info.get("volume") or info.get("regularMarketVolume"),
        "avg_volume": info.get("averageVolume") or info.get("averageDailyVolume10Day"),
        "pe_ratio": info.get("trailingPE") or info.get("forwardPE"),
        "eps": info.get("trailingEps"),
        "dividend_yield": info.get("dividendYield"),
        "beta": info.get("beta"),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh"),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow"),
        "target_mean_price": info.get("targetMeanPrice"),
        "target_high_price": info.get("targetHighPrice"),
        "target_low_price": info.get("targetLowPrice"),
        "number_of_analysts": info.get("numberOfAnalystOpinions"),
        "recommendation": info.get("recommendationKey", ""),
        "raw_info": info,
    }


def get_stock_info(symbol: str, force_refresh: bool = False) -> dict[str, Any]:
    sym = _resolve_asymbol(symbol) or symbol.upper().strip()
    existing = None

    with db_session() as db:
        try:
            existing = db.query(StockCache).filter(StockCache.symbol == sym).first()
            if existing and not force_refresh and _is_cache_fresh(existing):
                return {c.name: getattr(existing, c.name) for c in StockCache.__table__.columns}

            data = _fetch_info(sym)

            if existing:
                for k, v in data.items():
                    if hasattr(existing, k):
                        setattr(existing, k, v)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                db.add(StockCache(**{**data, "updated_at": datetime.now(timezone.utc)}))

            db.commit()
            return data
        except Exception as e:
            logger.warning("get_stock_info fetch failed for %s: %s (serving fallback)", sym, e)
            if existing:
                return {c.name: getattr(existing, c.name) for c in StockCache.__table__.columns}
            return {
                "symbol": sym, "name": "", "sector": "", "industry": "",
                "current_price": None, "previous_close": None, "market_cap": None,
                "pe_ratio": None, "eps": None, "beta": None, "recommendation": "",
                "raw_info": {},
            }


@retry_on_rate_limit
def get_stock_history(symbol: str, period: str = "6mo", interval: str = "1d") -> list[dict]:
    sym = _resolve_asymbol(symbol) or symbol.upper().strip()

    # Check AnalysisCache
    from backend.database.models import AnalysisCache
    with db_session() as db:
        cache_key = f"history_{period}_{interval}"
        row = db.query(AnalysisCache).filter(
            AnalysisCache.symbol == sym,
            AnalysisCache.analysis_type == cache_key,
        ).first()
        if row and row.updated_at:
            age = (_time.time() - row.updated_at.timestamp())
            if age < TTL.HISTORY:  # 10 min TTL for history
                return row.data.get("records", [])

    ticker = yf.Ticker(sym)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    records = []
    for _, row in df.iterrows():
        records.append({
            "date": str(row["Date"].date()),
            "open": round(float(row["Open"]), 2),
            "high": round(float(row["High"]), 2),
            "low": round(float(row["Low"]), 2),
            "close": round(float(row["Close"]), 2),
            "volume": int(row["Volume"]),
        })

    # Save cache
    with db_session() as db:
        try:
            existing = db.query(AnalysisCache).filter(
                AnalysisCache.symbol == sym,
                AnalysisCache.analysis_type == cache_key,
            ).first()
            now = datetime.now(timezone.utc)
            if existing:
                existing.data = {"records": records}
                existing.updated_at = now
            else:
                db.add(AnalysisCache(symbol=sym, analysis_type=cache_key,
                                     data={"records": records}, updated_at=now))
            db.commit()
        except Exception as e:
            logger.warning("save history cache failed for %s: %s", sym, e)

    return records


def _resolve_asymbol(query: str) -> str | None:
    """Auto-append A-share suffix for numeric codes."""
    q = query.strip()
    if q.isdigit() and len(q) == 6:
        if q.startswith(('6', '9')):
            # Shanghai
            try:
                t = yf.Ticker(q + '.SS')
                if t.info and t.info.get('symbol'):
                    return q + '.SS'
            except Exception:
                pass
            try:
                t = yf.Ticker(q + '.SZ')
                if t.info and t.info.get('symbol'):
                    return q + '.SZ'
            except Exception:
                pass
        else:
            # Shenzhen first (0xx, 3xx)
            for suffix in ('.SZ', '.SS'):
                try:
                    t = yf.Ticker(q + suffix)
                    if t.info and t.info.get('symbol'):
                        return q + suffix
                except Exception:
                    pass
    return None


def search_stocks(query: str) -> list[dict]:
    q = query.upper().strip()
    # Try direct first
    try:
        ticker = yf.Ticker(q)
        info = ticker.info or {}
        if info.get("symbol"):
            return [{
                "symbol": info["symbol"],
                "name": info.get("longName") or info.get("shortName", ""),
                "sector": info.get("sector", ""),
                "exchange": info.get("exchange", ""),
            }]
    except Exception:
        pass
    # Auto-resolve A-share numeric codes
    resolved = _resolve_asymbol(q)
    if resolved:
        try:
            ticker = yf.Ticker(resolved)
            info = ticker.info or {}
            if info.get("symbol"):
                return [{
                    "symbol": resolved,
                    "name": info.get("longName") or info.get("shortName", ""),
                    "sector": info.get("sector", ""),
                    "exchange": info.get("exchange", ""),
                }]
        except Exception:
            pass
    return []


import time as _time
from collections import OrderedDict

_MAX_SYMBOLS = 200  # max symbols kept in process-memory tick caches
_price_history: OrderedDict[str, list[tuple[float, float]]] = OrderedDict()
_price_info_cache: OrderedDict[str, tuple[float, float | None]] = OrderedDict()
_MAX_HISTORY = 120
_INFO_TTL = TTL.TICK_INFO


def _touch_price_history(sym: str) -> list[tuple[float, float]]:
    """Access _price_history with LRU eviction."""
    if sym in _price_history:
        _price_history.move_to_end(sym)
    else:
        _price_history[sym] = []
        while len(_price_history) > _MAX_SYMBOLS:
            _price_history.popitem(last=False)
    return _price_history[sym]


def _touch_price_info(sym: str) -> tuple[float, float | None] | None:
    """Access _price_info_cache with LRU eviction. Returns None if absent."""
    if sym in _price_info_cache:
        _price_info_cache.move_to_end(sym)
        return _price_info_cache[sym]
    return None


def _set_price_info(sym: str, val: tuple[float, float | None]) -> None:
    _price_info_cache[sym] = val
    _price_info_cache.move_to_end(sym)
    while len(_price_info_cache) > _MAX_SYMBOLS:
        _price_info_cache.popitem(last=False)


@retry_on_rate_limit
def get_tick(symbol: str) -> dict:
    sym = _resolve_asymbol(symbol) or symbol.upper().strip()
    now = _time.time()

    # Try background cache updater first
    from backend.services.cache_updater import get_updater
    cached = get_updater().get_tick(sym)
    if cached:
        price_val = float(cached["price"]) if cached["price"] else None
        if price_val is not None:
            _set_price_info(sym, (now, price_val))
    else:
        price_c = _touch_price_info(sym)
        if price_c and now - price_c[0] < _INFO_TTL:
            price_val = price_c[1]
        else:
            try:
                ticker = yf.Ticker(sym)
                info = ticker.info or {}
                price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
                price_val = float(price) if price else None
                _set_price_info(sym, (now, price_val))
            except Exception:
                price_val = None

    # Seed history on first call
    hist = _touch_price_history(sym)
    if not hist:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(period="1d", interval="5m")
            if not df.empty:
                df = df.dropna(subset=["Close"])
                for idx, row in df.iterrows():
                    hist.append((idx.timestamp(), float(row["Close"])))
        except Exception:
            pass

    # Record current price only if changed
    if price_val is not None:
        last_p = hist[-1][1] if hist else None
        if last_p is None or abs(price_val - last_p) > 0.0001:
            hist.append((now, price_val))
            if len(hist) > _MAX_HISTORY:
                del hist[:-_MAX_HISTORY]

    # Find price ~5 min ago
    change_5m = None
    target = now - 300
    best_p = None
    best_dist = float('inf')
    for ts, p in hist:
        d = abs(ts - target)
        if d < 120 and d < best_dist:
            best_p = p
            best_dist = d

    if best_p is not None and best_p > 0 and price_val:
        change_5m = round((price_val - best_p) / best_p * 100, 2)

    # Sparkline: last 40 points from today's price history
    sparkline = [p for _, p in hist[-40:]] if hist else []

    # Extended hours data from background cache
    ext = {}
    cached_tick = get_updater().get_tick(sym)
    if cached_tick:
        ext = {
            "pre_market_price": cached_tick.get("pre_market_price"),
            "pre_market_change": cached_tick.get("pre_market_change"),
            "post_market_price": cached_tick.get("post_market_price"),
            "post_market_change": cached_tick.get("post_market_change"),
            "regular_market_price": cached_tick.get("regular_market_price"),
            "previous_close": cached_tick.get("previous_close"),
            "market_state": cached_tick.get("market_state"),
        }

    return {
        "symbol": sym,
        "price": price_val,
        "change_5m": change_5m,
        "sparkline": sparkline,
        "prev_close": ext.get("previous_close"),
        "pre_market": ext.get("pre_market_price"),
        "pre_market_chg": ext.get("pre_market_change"),
        "post_market": ext.get("post_market_price"),
        "post_market_chg": ext.get("post_market_change"),
        "regular_price": ext.get("regular_market_price"),
        "market_state": ext.get("market_state"),
    }
