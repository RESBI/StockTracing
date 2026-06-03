from typing import Any
from datetime import datetime, timezone

import yfinance as yf
from sqlalchemy.orm import Session

from backend.database.models import StockCache, SessionLocal
from backend.config import CACHE_TTL_SECONDS


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def get_analyst_info(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    db: Session = SessionLocal()

    # Try StockCache first
    try:
        existing = db.query(StockCache).filter(StockCache.symbol == sym).first()
        if existing and existing.updated_at:
            now = datetime.now(timezone.utc)
            updated = existing.updated_at.replace(tzinfo=timezone.utc) if existing.updated_at.tzinfo is None else existing.updated_at
            age = (now - updated).total_seconds()
            if age < CACHE_TTL_SECONDS and existing.target_mean_price is not None:
                result = {
                    "target_mean": existing.target_mean_price,
                    "target_high": existing.target_high_price,
                    "target_low": existing.target_low_price,
                    "target_median": None,
                    "number_of_analysts": existing.number_of_analysts or 0,
                    "recommendation": existing.recommendation or "",
                    "recommendation_mean": None,
                    "current_price": existing.current_price,
                    "upside_percent": None,
                    "recent_ratings": [],
                    "upgrades_downgrades": [],
                }
                if result["current_price"] and result["target_mean"]:
                    result["upside_percent"] = round((result["target_mean"] - result["current_price"]) / result["current_price"] * 100, 2)
                return result
    finally:
        db.close()
    ticker = yf.Ticker(symbol.upper().strip())
    info = ticker.info or {}

    result = {
        "target_mean": _safe_float(info.get("targetMeanPrice")),
        "target_high": _safe_float(info.get("targetHighPrice")),
        "target_low": _safe_float(info.get("targetLowPrice")),
        "target_median": _safe_float(info.get("targetMedianPrice")),
        "number_of_analysts": info.get("numberOfAnalystOpinions", 0),
        "recommendation": info.get("recommendationKey", ""),
        "recommendation_mean": _safe_float(info.get("recommendationMean")),
        "current_price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
    }

    if result["current_price"] and result["target_mean"]:
        upside = (result["target_mean"] - result["current_price"]) / result["current_price"] * 100
        result["upside_percent"] = round(upside, 2)
    else:
        result["upside_percent"] = None

    try:
        recs = ticker.recommendations
        if recs is not None and not recs.empty:
            recent = recs.tail(5)
            result["recent_ratings"] = []
            for _, row in recent.iterrows():
                result["recent_ratings"].append({
                    "firm": str(row.get("Firm", "")),
                    "action": str(row.get("To Grade", "")),
                    "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
                })
    except Exception:
        result["recent_ratings"] = []

    try:
        upgrades = ticker.upgrades_downgrades
        if upgrades is not None and not upgrades.empty:
            recent_up = upgrades.tail(5)
            result["upgrades_downgrades"] = []
            for _, row in recent_up.iterrows():
                result["upgrades_downgrades"].append({
                    "firm": str(row.get("Firm", "")),
                    "from_grade": str(row.get("FromGrade", "")),
                    "to_grade": str(row.get("ToGrade", "")),
                    "action": str(row.get("Action", "")),
                    "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
                })
    except Exception:
        result["upgrades_downgrades"] = []

    return result
