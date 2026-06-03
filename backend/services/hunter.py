import json
from datetime import datetime, timezone
from typing import Any

from backend.config import DATA_DIR
from backend.database.models import SessionLocal, StockCache, FinancialCache, AnalysisCache
from backend.services.discovery import discover_all_stocks

UNIVERSE_FILE = DATA_DIR / "stock_universe.json"


def get_markets() -> list[str]:
    discovery = discover_all_stocks()
    return [k for k in discovery.keys() if k != "_ts"]


def get_sectors(market: str) -> list[str]:
    """Dynamically discover sectors from cached stock info, plus '全部'."""
    discovery = discover_all_stocks()
    symbols = discovery.get(market, [])
    if not symbols:
        return ["全部"]

    db = SessionLocal()
    try:
        rows = db.query(StockCache.sector).filter(
            StockCache.symbol.in_([s.upper().replace('-', '.') for s in symbols])
        ).distinct().all()
        secs = sorted(set(r[0] for r in rows if r[0]))
        if secs:
            secs.insert(0, "全部")
        else:
            secs = ["全部"]
        return secs
    finally:
        db.close()


def get_symbols(market: str, sector: str) -> list[str]:
    discovery = discover_all_stocks()
    all_syms = discovery.get(market, [])
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for s in all_syms:
        if s not in seen:
            seen.add(s)
            unique.append(s)
    if sector == "全部":
        return unique

    db = SessionLocal()
    try:
        rows = db.query(StockCache.symbol).filter(
            StockCache.symbol.in_([s.upper().replace('-', '.') for s in unique]),
            StockCache.sector == sector,
        ).all()
        return list(dict.fromkeys([r[0] for r in rows]))
    finally:
        db.close()


def score_stock(symbol: str) -> dict[str, Any] | None:
    db = SessionLocal()
    try:
        sc = db.query(StockCache).filter(StockCache.symbol == symbol.upper()).first()
        if not sc or sc.current_price is None or sc.current_price <= 0:
            return None

        price = sc.current_price

        # --- Value (0-30) ---
        value_score = 15
        value_details = []
        if sc.pe_ratio and sc.pe_ratio > 0:
            if sc.pe_ratio < 15:
                value_score += 10
                value_details.append(f"PE={sc.pe_ratio:.1f} < 15")
            elif sc.pe_ratio < 25:
                value_score += 5
                value_details.append(f"PE={sc.pe_ratio:.1f} < 25")
            else:
                value_score -= 3
                value_details.append(f"PE={sc.pe_ratio:.1f} 偏高")
        if sc.eps and sc.pe_ratio and sc.pe_ratio > 0:
            peg = sc.pe_ratio / (sc.eps * 100 / price) if sc.eps > 0 else None
            if peg is not None and peg < 1:
                value_score += 5
                value_details.append(f"PEG≈{peg:.1f} < 1")
        value_score = max(0, min(30, value_score))

        # --- Analyst (0-25) ---
        analyst_score = 10
        analyst_details = []
        if sc.target_mean_price and sc.target_mean_price > price:
            upside = (sc.target_mean_price - price) / price * 100
            analyst_details.append(f"目标价{sc.target_mean_price:.0f}，空间+{upside:.0f}%")
            if upside > 30:
                analyst_score += 12
            elif upside > 15:
                analyst_score += 7
            elif upside > 5:
                analyst_score += 3
        if sc.number_of_analysts and sc.number_of_analysts > 5:
            analyst_score += 3
            analyst_details.append(f"{sc.number_of_analysts}位分析师覆盖")
        rec = (sc.recommendation or "").lower()
        if "buy" in rec:
            analyst_score += 5
            analyst_details.append("评级:买入")
        analyst_score = max(0, min(25, analyst_score))

        # --- Technical (0-25) ---
        tech_score = 10
        tech_details = []
        tech = db.query(AnalysisCache).filter(
            AnalysisCache.symbol == sc.symbol,
            AnalysisCache.analysis_type == "full_indicators",
        ).first()
        if tech and tech.data:
            signals = tech.data.get("signals", [])
            buy_n = sum(1 for s in signals if s.get("signal") == "buy")
            sell_n = sum(1 for s in signals if s.get("signal") == "sell")
            tech_score += buy_n * 2 - sell_n * 2
            tech_details.append(f"买入{buy_n} 卖出{sell_n}")
            for s in signals[-5:]:
                if s.get("signal") != "neutral":
                    tech_details.append(f"{s.get('indicator')}:{s.get('signal')}")
        tech_score = max(0, min(25, tech_score))

        # --- Financial health (0-20) ---
        fin_score = 10
        fin_details = []
        if sc.dividend_yield and sc.dividend_yield > 0:
            fin_score += 3
            fin_details.append(f"股息率{(sc.dividend_yield*100):.1f}%")
        if sc.beta and sc.beta < 1.5:
            fin_score += 2
        elif sc.beta and sc.beta > 2:
            fin_score -= 2
            fin_details.append(f"高Beta={sc.beta:.1f}")

        fin_score = max(0, min(20, fin_score))

        total = value_score + analyst_score + tech_score + fin_score

        return {
            "symbol": sc.symbol,
            "name": sc.name or "",
            "price": price,
            "pe": sc.pe_ratio,
            "eps": sc.eps,
            "dividend_yield": sc.dividend_yield,
            "beta": sc.beta,
            "market_cap": sc.market_cap,
            "sector": sc.sector or "",
            "recommendation": sc.recommendation or "",
            "target_mean": sc.target_mean_price,
            "number_of_analysts": sc.number_of_analysts,
            "total_score": total,
            "scores": {
                "value": {"score": value_score, "max": 30, "details": value_details},
                "analyst": {"score": analyst_score, "max": 25, "details": analyst_details},
                "technical": {"score": tech_score, "max": 25, "details": tech_details},
                "financial": {"score": fin_score, "max": 20, "details": fin_details},
            },
        }
    finally:
        db.close()


def hunt(market: str, sector: str) -> dict[str, Any]:
    symbols = get_symbols(market, sector)
    if not symbols:
        return {"market": market, "sector": sector, "results": [], "total": 0}

    # Rate-limit: scan in batches of 5, no yfinance calls (cache-only)
    results = []
    for i, sym in enumerate(symbols):
        s = score_stock(sym)
        if s:
            results.append(s)

    results.sort(key=lambda x: x["total_score"], reverse=True)

    return {
        "market": market,
        "sector": sector,
        "results": results,
        "total": len(results),
    }
