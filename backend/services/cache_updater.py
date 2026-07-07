import time
import threading
from backend.config import retry_on_rate_limit, CACHE_TTL_SECONDS, CACHE_UPDATE_INTERVAL
from backend.database.models import StockCache
from backend.database.deps import db_session
from backend.services import ai_task
from backend.utils.logger import logger
from backend.utils.watchlist import load_watchlist
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


class CacheUpdater:
    def __init__(self, interval: int = 30):
        self._interval = interval
        self._thread: threading.Thread | None = None
        self._ai_thread: threading.Thread | None = None
        self._running = False
        self._ticks: dict[str, dict] = {}
        self._ai_refreshed: dict[str, str] = {}

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        self._ai_thread = threading.Thread(target=self._ai_loop, daemon=True)
        self._ai_thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                syms = load_watchlist()
                # Also include queued hunt symbols
                for sym in list(self._ticks.keys()):
                    if sym not in syms:
                        syms = list(syms) + [sym]
                syms = list(dict.fromkeys(syms))  # dedupe
                for i in range(0, len(syms), 2):
                    batch = syms[i:i + 2]
                    for sym in batch:
                        try:
                            self._update_one(sym)
                            self._maybe_refresh_ai(sym)
                        except Exception as e:
                            logger.warning("cache update failed for %s: %s", sym, e)
                        time.sleep(0.5)
                    time.sleep(1.5)
            except Exception as e:
                logger.warning("cache loop iteration error: %s", e)
            time.sleep(self._interval)

    def _ai_loop(self):
        """Process AI tasks from the persistent queue."""
        while self._running:
            try:
                task = ai_task.claim_next()
                if not task:
                    time.sleep(10)
                    continue
                try:
                    from backend.services.ai_context import build_stock_ai_context
                    from backend.services.llm_service import generate_summary
                    generate_summary(task.symbol, build_stock_ai_context(task.symbol))
                    ai_task.mark_done(task.id)
                    logger.info("AI task done: %s", task.symbol)
                except Exception as e:
                    ai_task.mark_failed(task.id, str(e))
            except Exception as e:
                logger.warning("AI loop error: %s", e)
            time.sleep(2)

    @retry_on_rate_limit
    def _update_one(self, symbol: str) -> None:
        sym = symbol.upper().strip()

        # Skip crypto - handled by separate service
        if sym.startswith("CRYPTO:") or "-USDT" in sym or "-USD" in sym:
            # Update tick cache for crypto
            try:
                from backend.services.crypto import get_crypto_info
                info = get_crypto_info(sym.replace("CRYPTO:", ""))
                if info and info.get("current_price"):
                    self._ticks[sym] = {"price": info["current_price"], "ts": time.time()}
            except Exception as e:
                logger.warning("crypto tick update failed for %s: %s", sym, e)
            return

        import yfinance as yf
        ticker = yf.Ticker(sym)
        info = ticker.info or {}

        price = info.get("currentPrice") or info.get("regularMarketPrice") or info.get("previousClose")
        pre_price = info.get("preMarketPrice")
        post_price = info.get("postMarketPrice")
        regular_price = info.get("regularMarketPrice")
        pre_change_pct = info.get("preMarketChangePercent")
        post_change_pct = info.get("postMarketChangePercent")
        market_state = info.get("marketState", "")

        # Keep only the active extended-hours side. Prefer explicit Yahoo
        # marketState, but fall back to which extended price is currently present.
        existing = self._ticks.get(sym, {})
        in_regular = market_state == "REGULAR"
        in_pre = market_state == "PRE" or (market_state != "POST" and pre_price is not None)
        in_post = market_state == "POST" or (market_state != "PRE" and post_price is not None)
        if in_pre:
            in_post = False
        elif in_post:
            in_pre = False
        self._ticks[sym] = {
            "price": price if price is not None else existing.get("price"),
            "ts": time.time(),
            "pre_market_price": (pre_price if pre_price is not None else existing.get("pre_market_price")) if in_pre else None,
            "pre_market_change": (pre_change_pct if pre_change_pct is not None else existing.get("pre_market_change")) if in_pre else None,
            "post_market_price": (post_price if post_price is not None else existing.get("post_market_price")) if in_post else None,
            "post_market_change": (post_change_pct if post_change_pct is not None else existing.get("post_market_change")) if in_post else None,
            "regular_market_price": regular_price if regular_price is not None else existing.get("regular_market_price"),
            "previous_close": (info.get("previousClose") or info.get("regularMarketPreviousClose")) or existing.get("previous_close"),
            "market_state": market_state,
        }

        data = {
            "symbol": sym,
            "name": info.get("longName") or info.get("shortName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap"),
            "current_price": price,
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
            "recommendation": info.get("recommendationKey"),
            "raw_info": info,
            "updated_at": datetime.now(timezone.utc),
        }

        # Update in-memory tick cache too (updates price, preserves extended data)
        if sym in self._ticks:
            self._ticks[sym]["price"] = price
            self._ticks[sym]["ts"] = time.time()
        else:
            self._ticks[sym] = {"price": price, "ts": time.time()}

        with db_session() as db:
            existing = db.query(StockCache).filter(StockCache.symbol == sym).first()
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                db.add(StockCache(**data))
            db.commit()

    def _market_key(self, symbol: str) -> str:
        sym = symbol.upper().strip()
        if sym.endswith((".SS", ".SZ")):
            return "CN"
        if sym.endswith(".HK"):
            return "HK"
        if sym.endswith(".T"):
            return "JP"
        return "US"

    def _is_after_market_close(self, symbol: str) -> tuple[bool, str]:
        market = self._market_key(symbol)
        configs = {
            "US": (ZoneInfo("America/New_York"), 16, 20),
            "CN": (ZoneInfo("Asia/Shanghai"), 15, 20),
            "HK": (ZoneInfo("Asia/Hong_Kong"), 16, 30),
            "JP": (ZoneInfo("Asia/Tokyo"), 15, 20),
        }
        tz, hour, minute = configs[market]
        now = datetime.now(tz)
        after_close = (now.hour, now.minute) >= (hour, minute)
        return after_close and now.weekday() < 5, now.date().isoformat()

    def _maybe_refresh_ai(self, symbol: str) -> None:
        sym = symbol.upper().strip()
        if sym.startswith("CRYPTO:") or "-USDT" in sym or "-USD" in sym:
            return
        ok, day_key = self._is_after_market_close(sym)
        if not ok or self._ai_refreshed.get(sym) == day_key:
            return
        self._ai_refreshed[sym] = day_key
        ai_task.enqueue(sym)

    def get_tick(self, symbol: str) -> dict | None:
        sym = symbol.upper().strip()
        tick = self._ticks.get(sym)
        if tick and time.time() - tick["ts"] < 120:
            return {
                "symbol": sym,
                "price": tick["price"],
                "change_5m": None,
                "pre_market_price": tick.get("pre_market_price"),
                "pre_market_change": tick.get("pre_market_change"),
                "post_market_price": tick.get("post_market_price"),
                "post_market_change": tick.get("post_market_change"),
                "regular_market_price": tick.get("regular_market_price"),
                "previous_close": tick.get("previous_close"),
                "market_state": tick.get("market_state"),
            }
        return None

    def queue_symbols(self, symbols: list[str]) -> None:
        for sym in symbols:
            sym = sym.upper().strip()
            if sym not in self._ticks:
                self._ticks[sym] = {"price": None, "ts": 0}


_updater: CacheUpdater | None = None


def get_updater(interval: int | None = None) -> CacheUpdater:
    """Get the singleton CacheUpdater. Interval defaults to CACHE_UPDATE_INTERVAL.

    Pass interval only for testing (must be called before first use).
    """
    global _updater
    if _updater is None:
        _updater = CacheUpdater(interval=interval if interval is not None else CACHE_UPDATE_INTERVAL)
    return _updater
