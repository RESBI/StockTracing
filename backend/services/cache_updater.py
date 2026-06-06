import time
import threading
from backend.config import retry_on_rate_limit, CACHE_TTL_SECONDS
from backend.database.models import StockCache, SessionLocal
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
        self._ai_queue: list[str] = []
        self._ai_lock = threading.Lock()

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
                        except Exception:
                            pass
                        time.sleep(0.5)
                    time.sleep(1.5)
            except Exception:
                pass
            time.sleep(self._interval)

    def _ai_loop(self):
        while self._running:
            sym = None
            with self._ai_lock:
                if self._ai_queue:
                    sym = self._ai_queue.pop(0)
            if not sym:
                time.sleep(10)
                continue
            try:
                from backend.services.ai_context import build_stock_ai_context
                from backend.services.llm_service import generate_summary
                generate_summary(sym, build_stock_ai_context(sym))
            except Exception:
                pass
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
            except Exception:
                pass
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

        # Keep only the active extended-hours side. Otherwise stale post-market
        # values can remain visible during the next pre-market session.
        existing = self._ticks.get(sym, {})
        in_regular = market_state == "REGULAR"
        in_pre = market_state == "PRE"
        in_post = market_state == "POST"
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

        db = SessionLocal()
        try:
            existing = db.query(StockCache).filter(StockCache.symbol == sym).first()
            if existing:
                for k, v in data.items():
                    setattr(existing, k, v)
            else:
                db.add(StockCache(**data))
            db.commit()
        finally:
            db.close()

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
        with self._ai_lock:
            if sym not in self._ai_queue:
                self._ai_queue.append(sym)

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


def get_updater() -> CacheUpdater:
    global _updater
    if _updater is None:
        _updater = CacheUpdater(interval=1)
    return _updater
