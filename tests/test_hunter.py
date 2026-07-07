"""Tests for backend.services.hunter scoring logic (pure cache read)."""
import pytest

from backend.database.models import StockCache, AnalysisCache, SessionLocal
from backend.services.hunter import score_stock


def _make_stock_cache(db, symbol, **kw):
    defaults = dict(
        symbol=symbol, name=kw.get("name", symbol), sector="科技", industry="",
        market_cap=1e10, current_price=kw.get("current_price", 100.0),
        previous_close=99.0, day_high=105, day_low=98, volume=1e6, avg_volume=1e6,
        pe_ratio=kw.get("pe_ratio", 15), eps=kw.get("eps", 5),
        dividend_yield=kw.get("dividend_yield", 0.01), beta=kw.get("beta", 1.0),
        fifty_two_week_high=120, fifty_two_week_low=80,
        target_mean_price=kw.get("target_mean_price", 130),
        target_high_price=140, target_low_price=90,
        number_of_analysts=kw.get("number_of_analysts", 8),
        recommendation=kw.get("recommendation", "buy"),
        raw_info={},
    )
    sc = StockCache(**defaults)
    db.add(sc)
    db.commit()
    return sc


def test_score_stock_returns_none_when_no_price(db_session):
    _make_stock_cache(db_session, "ZERO", current_price=None)
    assert score_stock("ZERO") is None


def test_score_stock_returns_none_when_not_cached(db_session):
    assert score_stock("NOTCACHED") is None


def test_score_stock_value_low_pe(db_session):
    _make_stock_cache(db_session, "LOWPE", pe_ratio=10, eps=10, current_price=100)
    r = score_stock("LOWPE")
    assert r is not None
    assert r["scores"]["value"]["score"] >= 20


def test_score_stock_value_high_pe(db_session):
    _make_stock_cache(db_session, "HIGHPE", pe_ratio=40, eps=1, current_price=100)
    r = score_stock("HIGHPE")
    assert r is not None
    assert r["scores"]["value"]["score"] < 20


def test_score_stock_analyst_upside(db_session):
    _make_stock_cache(db_session, "UPSI", target_mean_price=200, current_price=100, number_of_analysts=10, recommendation="buy")
    r = score_stock("UPSI")
    assert r is not None
    assert r["scores"]["analyst"]["score"] >= 20


def test_score_stock_total_in_range(db_session):
    _make_stock_cache(db_session, "TOTL", current_price=100)
    r = score_stock("TOTL")
    assert r is not None
    total = r["total_score"]
    assert 0 <= total <= 100
    s = r["scores"]
    assert s["value"]["score"] + s["analyst"]["score"] + s["technical"]["score"] + s["financial"]["score"] == total


def test_score_stock_technical_uses_signals(db_session):
    _make_stock_cache(db_session, "TECHS", current_price=100)
    db = SessionLocal()
    try:
        db.add(AnalysisCache(
            symbol="TECHS", analysis_type="full_indicators",
            data={"signals": [
                {"indicator": "RSI", "signal": "buy"},
                {"indicator": "MACD", "signal": "buy"},
                {"indicator": "Bollinger", "signal": "sell"},
            ]},
        ))
        db.commit()
    finally:
        db.close()
    r = score_stock("TECHS")
    assert r is not None
    tech = r["scores"]["technical"]
    assert tech["score"] > 10
