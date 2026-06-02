from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.stock_data import get_stock_info, get_stock_history, search_stocks, get_tick, _resolve_asymbol
from backend.services.financials import get_financials
from backend.services.analyst import get_analyst_info
from backend.services.technical import calculate_all_indicators, get_period_analysis
from backend.services.llm_service import generate_summary
from backend.services.news_service import get_stock_news, search_stock_insights
from backend.services.hunter import hunt, get_markets, get_sectors
from backend.services.discovery import discover_all_stocks
from backend.services.cache_updater import get_updater
from backend.services.trades import (
    get_all_trades, get_trade, create_trade, update_trade, 
    delete_trade, get_trade_stats
)
from backend.utils.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist
from backend.database.models import LLMCache, SessionLocal, HuntSession
from backend.config import _load_json_config, save_json_config, CONFIG_FILE

router = APIRouter(prefix="/api", tags=["api"])
templates = Jinja2Templates(directory="frontend/templates")


def _resolve_sym(symbol: str) -> str:
    r = _resolve_asymbol(symbol)
    return r if r else symbol.upper().strip()


@router.get("/stock/{symbol}")
def api_stock_info(symbol: str, refresh: bool = False):
    try:
        return get_stock_info(symbol, force_refresh=refresh)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"无法获取 {symbol}: {str(e)}")


@router.get("/stock/{symbol}/tick")
def api_tick(symbol: str):
    try:
        return get_tick(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/history")
def api_stock_history(symbol: str, period: str = "6mo", interval: str = "1d"):
    try:
        return get_stock_history(symbol, period=period, interval=interval)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/financials")
def api_financials(symbol: str, refresh: bool = False):
    try:
        return get_financials(_resolve_sym(symbol), force_refresh=refresh)
    except Exception as e:
        return {"income_statement": [], "balance_sheet": [], "cash_flow": [],
                "quarterly_income": [], "quarterly_balance": [], "quarterly_cashflow": []}


@router.get("/stock/{symbol}/analyst")
def api_analyst(symbol: str):
    try:
        return get_analyst_info(_resolve_sym(symbol))
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"分析师数据获取失败: {str(e)}")


@router.get("/stock/{symbol}/technical")
def api_technical(symbol: str):
    try:
        return calculate_all_indicators(_resolve_sym(symbol))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/periods")
def api_periods(symbol: str):
    try:
        return get_period_analysis(_resolve_sym(symbol))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/news")
def api_news(symbol: str, refresh: bool = False):
    return get_stock_news(_resolve_sym(symbol), force_refresh=refresh)


@router.get("/stock/{symbol}/insights")
def api_insights(symbol: str):
    return search_stock_insights(_resolve_sym(symbol))


@router.get("/stock/{symbol}/summary")
def api_summary(symbol: str):
    try:
        sym = _resolve_sym(symbol)
        info = get_stock_info(sym)
        analyst = get_analyst_info(sym)

        tech = None
        try:
            tech = calculate_all_indicators(sym)
        except Exception:
            pass

        context = {
            "基本信息": {k: v for k, v in info.items() if k != "raw_info"},
            "分析师评级": analyst,
        }
        if tech:
            context["技术面信号"] = tech.get("signals", [])[-7:]
            context["最新价格"] = tech.get("latest_price")

        return generate_summary(sym, context)
    except Exception as e:
        return {"enabled": False, "summary": f"数据获取失败: {str(e)}"}


@router.get("/stock/{symbol}/full")
def api_full_analysis(symbol: str, refresh: bool = False):
    sym = _resolve_sym(symbol)
    result = {}

    try:
        result["info"] = get_stock_info(sym, force_refresh=refresh)
    except Exception as e:
        result["info"] = {"symbol": sym, "name": "获取失败", "error": str(e)}

    try:
        result["history"] = get_stock_history(sym)[-90:]
    except Exception:
        result["history"] = []

    try:
        result["analyst"] = get_analyst_info(sym)
    except Exception:
        result["analyst"] = {}

    try:
        result["financials"] = get_financials(sym, force_refresh=refresh)
    except Exception:
        result["financials"] = {}

    try:
        tech = calculate_all_indicators(sym)
        result["technical"] = {
            "latest_price": tech.get("latest_price"),
            "signals": tech.get("signals"),
            "rsi": tech.get("rsi", [])[-1] if tech.get("rsi") else None,
            "macd": {k: v[-1] if v else None for k, v in tech.get("macd", {}).items()},
            "bollinger": {k: v[-1] if v else None for k, v in tech.get("bollinger", {}).items()},
        }
    except Exception:
        result["technical"] = {"latest_price": None, "signals": []}

    try:
        result["periods"] = get_period_analysis(sym)
    except Exception:
        result["periods"] = {"changes": {}, "signals": {}}

    try:
        if result.get("info", {}).get("name"):
            summary_context = {
                "基本信息": {k: v for k, v in result["info"].items() if k != "raw_info" and k != "error"},
                "分析师评级": result.get("analyst", {}),
                "技术面信号": result.get("technical", {}).get("signals", [])[-7:],
            }
            result["summary"] = generate_summary(sym, summary_context)
        else:
            result["summary"] = {"enabled": False, "summary": ""}
    except Exception:
        result["summary"] = {"enabled": False, "summary": ""}

    return result


@router.get("/search")
def api_search(q: str = Query(..., min_length=1)):
    return search_stocks(q)


@router.get("/watchlist")
def api_get_watchlist():
    return {"symbols": load_watchlist()}


@router.post("/watchlist/{symbol}")
def api_add_watchlist(symbol: str):
    return {"symbols": add_to_watchlist(_resolve_sym(symbol))}


@router.delete("/watchlist/{symbol}")
def api_remove_watchlist(symbol: str):
    return {"symbols": remove_from_watchlist(symbol)}


@router.get("/config")
def api_get_config():
    cfg = _load_json_config()
    if "llm" in cfg and cfg["llm"].get("api_key"):
        key = cfg["llm"]["api_key"]
        cfg["llm"]["api_key"] = key[:8] + "****" + key[-4:] if len(key) > 12 else "****"
    return cfg


@router.put("/config")
def api_update_config(body: dict):
    current = _load_json_config()
    for section in ("llm", "proxy"):
        if section in body and isinstance(body[section], dict):
            current.setdefault(section, {}).update(body[section])
    save_json_config(current)
    from backend.utils.proxy import setup_proxy
    setup_proxy()
    return {"status": "ok"}


@router.get("/stock/{symbol}/ai-history")
def api_ai_history(symbol: str):
    sym = _resolve_sym(symbol).upper().strip()
    db = SessionLocal()
    try:
        rows = db.query(LLMCache).filter(
            LLMCache.symbol == sym
        ).order_by(LLMCache.created_at.desc()).limit(10).all()
        return [{
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "content": r.content,
        } for r in rows]
    finally:
        db.close()


# ---------- Hunting ----------
@router.get("/hunt/markets")
def api_hunt_markets():
    return get_markets()


@router.get("/hunt/sectors")
def api_hunt_sectors(market: str):
    return get_sectors(market)


@router.post("/hunt/run")
def api_hunt_run(market: str, sector: str):
    # Queue all discovered symbols for background fetching
    discovery = discover_all_stocks()
    all_syms = discovery.get(market, [])
    if all_syms:
        get_updater().queue_symbols(all_syms)

    result = hunt(market, sector)
    # Save to history
    db = SessionLocal()
    try:
        db.add(HuntSession(
            market=market,
            sector=sector,
            data=result,
            total=result["total"],
        ))
        db.commit()
    finally:
        db.close()
    return result


@router.get("/hunt/history")
def api_hunt_history():
    db = SessionLocal()
    try:
        rows = db.query(HuntSession).order_by(HuntSession.created_at.desc()).limit(20).all()
        return [{
            "id": r.id,
            "market": r.market,
            "sector": r.sector,
            "total": r.total,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in rows]
    finally:
        db.close()


@router.get("/hunt/history/{session_id}")
def api_hunt_session_detail(session_id: int):
    db = SessionLocal()
    try:
        row = db.query(HuntSession).filter(HuntSession.id == session_id).first()
        if not row:
            raise HTTPException(status_code=404)
        return row.data
    finally:
        db.close()


# ---------- Trading Journal ----------
@router.get("/trades")
def api_get_trades():
    return get_all_trades()


@router.get("/trades/stats")
def api_trade_stats():
    return get_trade_stats()


@router.post("/trades")
def api_create_trade(body: dict):
    return create_trade(body)


@router.put("/trades/{trade_id}")
def api_update_trade(trade_id: str, body: dict):
    result = update_trade(trade_id, body)
    if not result:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return result


@router.delete("/trades/{trade_id}")
def api_delete_trade(trade_id: str):
    if not delete_trade(trade_id):
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return {"status": "ok"}

