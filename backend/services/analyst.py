from typing import Any
from datetime import datetime, timezone

import yfinance as yf

from backend.database.models import StockCache, AnalysisCache
from backend.database.deps import db_session
from backend.config import CACHE_TTL_SECONDS
from backend.utils.logger import logger


def _safe_float(val: Any) -> float | None:
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_ratings(sym: str) -> dict:
    """Fetch recent ratings and upgrades, cached in AnalysisCache."""
    with db_session() as db:
        existing = db.query(AnalysisCache).filter(
            AnalysisCache.symbol == sym,
            AnalysisCache.analysis_type == "analyst_ratings",
        ).first()
        if existing and existing.updated_at:
            updated = existing.updated_at.replace(tzinfo=timezone.utc) if existing.updated_at.tzinfo is None else existing.updated_at
            age = (datetime.now(timezone.utc) - updated).total_seconds()
            if age < CACHE_TTL_SECONDS:
                return existing.data

    result = {"recent_ratings": [], "upgrades_downgrades": []}
    try:
        ticker = yf.Ticker(sym)
        # Recent ratings
        recs = ticker.recommendations
        if recs is not None and not recs.empty:
            recent = recs.tail(5)
            for _, row in recent.iterrows():
                result["recent_ratings"].append({
                    "firm": str(row.get("Firm", "")),
                    "action": str(row.get("To Grade", "")),
                    "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
                })
    except Exception as e:
        logger.warning("fetch recommendations failed for %s: %s", sym, e)

    try:
        ticker = yf.Ticker(sym)
        upgrades = ticker.upgrades_downgrades
        if upgrades is not None and not upgrades.empty:
            recent_up = upgrades.tail(5)
            for _, row in recent_up.iterrows():
                result["upgrades_downgrades"].append({
                    "firm": str(row.get("Firm", "")),
                    "from_grade": str(row.get("FromGrade", "")),
                    "to_grade": str(row.get("ToGrade", "")),
                    "action": str(row.get("Action", "")),
                    "date": str(row.name.date()) if hasattr(row.name, "date") else str(row.name),
                })
    except Exception as e:
        logger.warning("fetch upgrades_downgrades failed for %s: %s", sym, e)

    # Save to cache
    with db_session() as db:
        try:
            existing = db.query(AnalysisCache).filter(
                AnalysisCache.symbol == sym,
                AnalysisCache.analysis_type == "analyst_ratings",
            ).first()
            now = datetime.now(timezone.utc)
            if existing:
                existing.data = result
                existing.updated_at = now
            else:
                db.add(AnalysisCache(symbol=sym, analysis_type="analyst_ratings",
                                     data=result, updated_at=now))
            db.commit()
        except Exception as e:
            logger.warning("save analyst_ratings cache failed for %s: %s", sym, e)

    return result


def get_analyst_info(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    ratings = {"recent_ratings": [], "upgrades_downgrades": []}

    # Try StockCache first
    with db_session() as db:
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
                # Fetch ratings from cache
                ratings = _fetch_ratings(sym)
                result["recent_ratings"] = ratings["recent_ratings"]
                result["upgrades_downgrades"] = ratings["upgrades_downgrades"]
                return result

    ticker = yf.Ticker(sym)
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
        "recent_ratings": [],
        "upgrades_downgrades": [],
    }

    if result["current_price"] and result["target_mean"]:
        upside = (result["target_mean"] - result["current_price"]) / result["current_price"] * 100
        result["upside_percent"] = round(upside, 2)
    else:
        result["upside_percent"] = None

    # Fetch ratings from cache/yfinance
    ratings = _fetch_ratings(sym)
    result["recent_ratings"] = ratings["recent_ratings"]
    result["upgrades_downgrades"] = ratings["upgrades_downgrades"]

    return result
