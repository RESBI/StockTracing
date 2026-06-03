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

    holdings = []
    total_value = 0.0
    sector_map = defaultdict(float)

    for t in trades:
        sym = t.get("symbol", "")
        open_p = t.get("open_price")
        qty = t.get("quantity", 0) or 0
        direction = t.get("direction", "long")
        is_open = t.get("status") == "open"

        sc = db.query(StockCache).filter(StockCache.symbol == sym.upper()).first()
        cur_p = sc.current_price if sc else None
        sector = (sc.sector or "未知") if sc else "未知"

        if is_open and open_p and cur_p:
            if direction == "long":
                pnl = (cur_p - open_p) * qty
                pnl_pct = (cur_p - open_p) / open_p * 100
            else:
                pnl = (open_p - cur_p) * qty
                pnl_pct = (open_p - cur_p) / cur_p * 100
            value = cur_p * qty
            total_value += value
            sector_map[sector] += value
            holdings.append({
                "symbol": sym,
                "direction": direction,
                "quantity": qty,
                "open_price": open_p,
                "current_price": cur_p,
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "value": round(value, 2),
                "sector": sector,
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
        "total_value": round(total_value, 2),
        "symbol_pie": symbol_pie,
        "sector_pie": sector_pie,
        "pnl_curve": pnl_curve,
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
            hist = db.query(AnalysisCache).filter(
                AnalysisCache.symbol == sym,
                AnalysisCache.analysis_type == "history_5d_60m",
            ).first()
            if hist and hist.data:
                records = hist.data.get("records", [])
                symbol_histories[sym] = {r["date"][:16]: r["close"] for r in records if r.get("close")}
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

    # For each day, compute total portfolio value
    curve = []
    current = start
    while current <= end:
        day_str = current.strftime("%Y-%m-%d")
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

            # Check if this trade was active on this day
            if od > day_str:
                continue  # Not opened yet
            if cd and cd < day_str:
                continue  # Already closed

            # Get price for this day
            price_map = symbol_histories.get(sym, {})
            price = price_map.get(day_str)

            if price is None:
                if cd and cd == day_str:
                    price = t.get("close_price") or price
                elif od == day_str:
                    price = open_p
                else:
                    # Use last known price
                    prev_date = current - timedelta(days=1)
                    while prev_date >= start:
                        prev_str = prev_date.strftime("%Y-%m-%d")
                        prev_p = price_map.get(prev_str)
                        if prev_p:
                            price = prev_p
                            break
                        prev_date -= timedelta(days=1)
                    if price is None:
                        price = open_p

            if price:
                if direction == "long":
                    pnl = (price - open_p) * qty
                else:
                    pnl = (open_p - price) * qty
                day_total += pnl

        curve.append({"date": day_str, "pnl": round(day_total, 2)})
        current += timedelta(days=1)

    return curve
