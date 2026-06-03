import json
import uuid
from datetime import datetime
from typing import Any

from backend.config import DATA_DIR

TRADES_FILE = DATA_DIR / "trades.json"


def _load() -> list[dict]:
    if TRADES_FILE.exists():
        try:
            return json.loads(TRADES_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return []


def _save(trades: list[dict]) -> None:
    TRADES_FILE.write_text(json.dumps(trades, ensure_ascii=False, indent=2), encoding="utf-8")


def get_all_trades() -> list[dict]:
    from backend.database.models import StockCache, SessionLocal
    trades = _load()
    db = SessionLocal()
    try:
        for t in trades:
            if t.get("status") == "open":
                sym = t.get("symbol", "")
                sc = db.query(StockCache).filter(StockCache.symbol == sym.upper()).first()
                t["current_price"] = sc.current_price if sc else None
                t["_unrealized"] = None
                open_p = t.get("open_price")
                cur_p = t.get("current_price")
                qty = t.get("quantity", 0) or 0
                if open_p and cur_p:
                    direction = t.get("direction", "long")
                    if direction == "long":
                        t["_unrealized"] = round((cur_p - open_p) * qty, 2)
                    else:
                        t["_unrealized"] = round((open_p - cur_p) * qty, 2)
    finally:
        db.close()
    return trades


def get_trade(trade_id: str) -> dict | None:
    for t in _load():
        if t.get("id") == trade_id:
            return t
    return None


def create_trade(data: dict) -> dict:
    trade = {
        "id": uuid.uuid4().hex[:12],
        "symbol": data.get("symbol", "").upper().strip(),
        "direction": data.get("direction", "long"),  # long or short
        "open_date": data.get("open_date", ""),
        "open_price": data.get("open_price"),
        "close_date": data.get("close_date", ""),
        "close_price": data.get("close_price"),
        "quantity": data.get("quantity"),
        "notes": data.get("notes", ""),
        "created_at": datetime.now().isoformat(),
        "status": "open" if data.get("close_price") is None else "closed",
    }
    trades = _load()
    trades.insert(0, trade)
    _save(trades)
    return trade


def update_trade(trade_id: str, data: dict) -> dict | None:
    trades = _load()
    for t in trades:
        if t.get("id") == trade_id:
            for k in ("symbol", "direction", "open_date", "open_price", "close_date",
                       "close_price", "quantity", "notes"):
                if k in data:
                    t[k] = data[k]
            if t.get("close_price") is not None:
                t["status"] = "closed"
            else:
                t["status"] = "open"
            _save(trades)
            return t
    return None


def delete_trade(trade_id: str) -> bool:
    trades = _load()
    new_trades = [t for t in trades if t.get("id") != trade_id]
    if len(new_trades) < len(trades):
        _save(new_trades)
        return True
    return False


def get_trade_stats() -> dict[str, Any]:
    from backend.database.models import StockCache, SessionLocal
    trades = _load()
    total = len(trades)
    open_positions = [t for t in trades if t.get("status") == "open"]
    closed = [t for t in trades if t.get("status") == "closed"]

    total_pnl = 0.0
    win_count = 0
    loss_count = 0
    for t in closed:
        open_p = t.get("open_price")
        close_p = t.get("close_price")
        qty = t.get("quantity", 0) or 0
        if open_p and close_p:
            direction = t.get("direction", "long")
            if direction == "long":
                pnl = (close_p - open_p) * qty
            else:
                pnl = (open_p - close_p) * qty
            total_pnl += pnl
            if pnl > 0:
                win_count += 1
            elif pnl < 0:
                loss_count += 1

    # Unrealized P&L for open positions
    unrealized_pnl = 0.0
    db = SessionLocal()
    try:
        for t in open_positions:
            open_p = t.get("open_price")
            qty = t.get("quantity", 0) or 0
            if not open_p:
                continue
            sym = t.get("symbol", "")
            sc = db.query(StockCache).filter(StockCache.symbol == sym.upper()).first()
            if sc and sc.current_price:
                direction = t.get("direction", "long")
                if direction == "long":
                    unrealized_pnl += (sc.current_price - open_p) * qty
                else:
                    unrealized_pnl += (open_p - sc.current_price) * qty
    finally:
        db.close()

    return {
        "total": total,
        "open_count": len(open_positions),
        "closed_count": len(closed),
        "total_pnl": round(total_pnl, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": round(win_count / len(closed) * 100, 1) if closed else 0,
    }


def get_portfolio(interval: str = "1d") -> dict[str, Any]:
    from backend.database.models import StockCache, SessionLocal
    from collections import defaultdict
    trades = _load()
    db = SessionLocal()

    # Merge holdings by symbol (weighted average cost)
    merged = {}
    total_value = 0.0
    sector_map = defaultdict(float)
    for t in trades:
        sym = t.get("symbol", "").upper()
        open_p = t.get("open_price")
        qty = t.get("quantity", 0) or 0
        direction = t.get("direction", "long")
        is_open = t.get("status") == "open"

        sc = db.query(StockCache).filter(StockCache.symbol == sym).first()
        cur_p = sc.current_price if sc else None
        sector = (sc.sector or "未知") if sc else "未知"

        if not is_open or not open_p or not cur_p:
            continue

        key = sym
        if key not in merged:
            merged[key] = {"symbol": sym, "direction": direction, "total_qty": 0, "total_cost": 0.0, "cur_p": cur_p, "sector": sector}
        m = merged[key]
        m["total_qty"] += qty
        m["total_cost"] += open_p * qty

    holdings = []
    total_cost = 0.0
    for sym, m in merged.items():
        avg_price = m["total_cost"] / m["total_qty"] if m["total_qty"] > 0 else 0
        total_cost += m["total_cost"]
        cur_p = m["cur_p"]
        direction = m["direction"]
        qty = m["total_qty"]
        if direction == "long":
            pnl = (cur_p - avg_price) * qty
            pnl_pct = (cur_p - avg_price) / avg_price * 100 if avg_price > 0 else 0
        else:
            pnl = (avg_price - cur_p) * qty
            pnl_pct = (avg_price - cur_p) / cur_p * 100 if cur_p > 0 else 0
        value = cur_p * qty
        total_value += value
        sector_map[m["sector"]] += value
        holdings.append({
            "symbol": sym,
            "direction": direction,
            "quantity": qty,
            "open_price": round(avg_price, 2),
            "current_price": cur_p,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "value": round(value, 2),
            "sector": m["sector"],
        })

    # Build trade events for P&L curve markers
    events = []
    for t in trades:
        od = (t.get("open_date") or "")[:10]
        cd = (t.get("close_date") or "")[:10] if t.get("close_date") else None
        sym = t.get("symbol", "")
        price = t.get("open_price")
        qty = t.get("quantity", 0)
        direction = t.get("direction", "long")
        if od and price and qty:
            events.append({
                "date": od,
                "label": f"{sym}@{price}×{qty} {'多' if direction == 'long' else '空'}",
                "type": "buy" if direction == "long" else "sell",
            })
        if cd and t.get("close_price") and qty:
            events.append({
                "date": cd,
                "label": f"{sym}@{t['close_price']}×{qty} 平",
                "type": "close",
            })
    # P&L curve data
    pnl_curve = _compute_pnl_curve(db, interval)
    db.close()

    # Symbol pie
    symbol_pie = [{"name": h["symbol"], "value": round(h["value"], 2)} for h in holdings]

    # Sector pie
    sector_pie = [{"name": k, "value": round(v, 2)} for k, v in sector_map.items()]

    return {
        "holdings": holdings,
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "symbol_pie": symbol_pie,
        "sector_pie": sector_pie,
        "pnl_curve": pnl_curve,
        "events": events,
    }


def _compute_pnl_curve(db, interval: str = "1d") -> list[dict]:
    from backend.database.models import StockCache, AnalysisCache
    from datetime import datetime, timedelta
    from collections import defaultdict
    trades = _load()
    if not trades:
        return []

    # Get historical prices for each symbol from cache
    symbol_histories = {}
    for t in trades:
        sym = t.get("symbol", "").upper()
        if sym in symbol_histories:
            continue
        if interval == "1h":
            # Fetch real hourly data
            try:
                import yfinance as yf
                import logging
                logging.getLogger('yfinance').setLevel(logging.ERROR)
                ticker = yf.Ticker(sym)
                # Try progressively shorter periods for hourly data
                for try_period in ["5d", "2d", "1d"]:
                    for try_interval in ["60m", "30m", "15m"]:
                        df = ticker.history(period=try_period, interval=try_interval)
                        if not df.empty:
                            break
                    if not df.empty:
                        break
                if not df.empty:
                    hourly = {}
                    for idx, row in df.iterrows():
                        close_val = float(row["Close"])
                        if close_val and close_val > 0:
                            key = str(idx)[:16]
                            hourly[key] = close_val
                    if hourly:
                        symbol_histories[sym] = hourly
                        from datetime import timezone as tz
                        now = datetime.now(tz.utc)
                        records = [{"date": k, "close": v} for k, v in hourly.items()]
                        existing_cache = db.query(AnalysisCache).filter(
                            AnalysisCache.symbol == sym,
                            AnalysisCache.analysis_type == "history_5d_60m",
                        ).first()
                        if existing_cache:
                            existing_cache.data = {"records": records}
                            existing_cache.updated_at = now
                        else:
                            db.add(AnalysisCache(symbol=sym, analysis_type="history_5d_60m",
                                                 data={"records": records}, updated_at=now))
                        db.commit()
            except Exception:
                pass

        if sym not in symbol_histories:
            for period in ["1y", "6mo", "3mo", "1mo"]:
                key = f"history_{period}_1d"
                hist = db.query(AnalysisCache).filter(
                    AnalysisCache.symbol == sym,
                    AnalysisCache.analysis_type == key,
                ).first()
                if hist and hist.data:
                    records = hist.data.get("records", [])
                    symbol_histories[sym] = {r["date"]: r["close"] for r in records if r.get("close")}
                    break

    # Find date range
    all_dates = []
    for t in trades:
        od_raw = t.get("open_date")
        if od_raw:
            all_dates.append(od_raw[:10])
            # Also try to get history for this symbol close to open date
            sym = t.get("symbol", "").upper()
            if sym not in symbol_histories:
                symbol_histories[sym] = {}

    if not all_dates:
        return []

    all_dates.sort()
    start = datetime.strptime(all_dates[0], "%Y-%m-%d")
    end = datetime.now()

    # For hourly, interpolate from daily data
    if interval == "1h":
        # Use actual hourly timestamps from the data
        all_timestamps = set()
        for sym, pmap in symbol_histories.items():
            for k in pmap:
                if len(k) > 10:  # hourly key format
                    all_timestamps.add(k)
        if all_timestamps:
            all_timestamps = sorted(all_timestamps)
            start_dt = datetime.strptime(all_timestamps[0], "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(all_timestamps[-1], "%Y-%m-%d %H:%M")
            step = timedelta(hours=1)
        else:
            # No hourly data, fall back to daily
            interval = "1d"
    else:
        step = timedelta(days=1)

    # Build iteration list
    if interval == "1h" and len(all_timestamps) > 0:
        time_keys = all_timestamps
    else:
        time_keys = []
        current = start
        while current <= end:
            time_keys.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)

    curve = []
    last_prices = {}
    for key in time_keys:
        day_total = 0.0
        for t in trades:
            open_p = t.get("open_price")
            qty = t.get("quantity", 0) or 0
            if not open_p or not qty:
                continue
            direction = t.get("direction", "long")
            od_raw = t.get("open_date")
            cd_raw = t.get("close_date")
            if not od_raw:
                continue
            od = od_raw[:10]
            cd = cd_raw[:10] if cd_raw else None
            sym = t.get("symbol", "").upper()

            # Check active (compare dates only)
            if key[:10] < od:
                continue
            if cd and key[:10] > cd:
                continue

            # Get price
            price_map = symbol_histories.get(sym, {})
            price = price_map.get(key)

            if price is None:
                # Try nearby keys (for hourly)
                if interval == "1h" and len(key) > 10:
                    # Try same date keys
                    base_date = key[:10]
                    for h in range(24):
                        alt = f"{base_date} {str(h).zfill(2)}:30"
                        if alt in price_map:
                            price = price_map[alt]
                            break
                if price is None:
                    # Try daily key
                    price = price_map.get(key[:10])
                if price is None:
                    price = last_prices.get(sym, open_p)
            else:
                last_prices[sym] = price

            if direction == "long":
                pnl = (price - open_p) * qty
            else:
                pnl = (open_p - price) * qty
            day_total += pnl

        curve.append({"date": key, "pnl": round(day_total, 2)})

    return curve
