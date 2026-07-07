from fastapi import APIRouter, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.services.stock_data import get_stock_info, get_stock_history, search_stocks, get_tick
from backend.services.financials import get_financials
from backend.services.analyst import get_analyst_info
from backend.services.technical import calculate_all_indicators, get_period_analysis
from backend.services.ai_context import build_stock_ai_context
from backend.services.llm_service import generate_summary, get_latest_summary
from backend.services.news_service import get_cached_stock_news, get_stock_news, search_stock_insights
from backend.services.hunter import hunt, get_markets, get_sectors
from backend.services.discovery import discover_all_stocks
from backend.services.cache_updater import get_updater
from backend.services.ai_task import enqueue as enqueue_ai, queue_status as ai_queue_status
from backend.utils.circuit_breaker import circuit_status
from backend.services.trades import (
    get_all_trades, get_trade, create_trade, update_trade, 
    delete_trade, get_trade_stats, get_portfolio
)
from backend.services.crypto import get_crypto_info, get_crypto_history, get_crypto_tick, get_crypto_indicators, get_crypto_periods
from backend.services.symbol_resolver import is_crypto as _is_crypto, crypto_sym as _crypto_sym, resolve_sym as _resolve_sym
from backend.services.institutions import get_institutions, get_institution, get_institution_history, get_institution_history_detail, warm_institution_mappings


from backend.utils.watchlist import load_watchlist, add_to_watchlist, remove_from_watchlist
from backend.database.models import LLMCache, HuntSession
from backend.database.deps import db_session
from backend.config import _load_json_config, save_json_config, CONFIG_FILE
from backend.schemas import TradeCreate, TradeUpdate, ConfigUpdate, TicksRequest

router = APIRouter(prefix="/api", tags=["api"])
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/stock/{symbol}")
def api_stock_info(symbol: str, refresh: bool = False):
    try:
        if _is_crypto(symbol):
            info = get_crypto_info(_crypto_sym(symbol))
            if info:
                return info
            raise HTTPException(status_code=404)
        return get_stock_info(symbol, force_refresh=refresh)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"无法获取 {symbol}: {str(e)}")


@router.get("/stock/{symbol}/tick")
def api_tick(symbol: str):
    try:
        if _is_crypto(symbol):
            t = get_crypto_tick(_crypto_sym(symbol))
            if t: return t
            raise HTTPException(status_code=404)
        return get_tick(symbol)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/ticks")
def api_ticks(body: TicksRequest):
    """Batch tick endpoint. Reduces N HTTP requests to 1 for dashboard polling."""
    symbols = body.symbols
    ticks = {}
    for sym in symbols:
        try:
            if _is_crypto(sym):
                t = get_crypto_tick(_crypto_sym(sym))
                if t:
                    ticks[sym] = t
            else:
                ticks[sym] = get_tick(sym)
        except Exception:
            ticks[sym] = {"symbol": sym, "price": None}
    return {"ticks": ticks}


@router.get("/stock/{symbol}/history")
def api_stock_history(symbol: str, period: str = "6mo", interval: str = "1d"):
    try:
        if _is_crypto(symbol):
            return get_crypto_history(_crypto_sym(symbol), period=period)
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
        if _is_crypto(symbol):
            r = get_crypto_indicators(_crypto_sym(symbol))
            if r: return r
            raise HTTPException(status_code=404)
        return calculate_all_indicators(_resolve_sym(symbol))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/periods")
def api_periods(symbol: str):
    try:
        if _is_crypto(symbol):
            return get_crypto_periods(_crypto_sym(symbol))
        return get_period_analysis(_resolve_sym(symbol))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stock/{symbol}/news")
def api_news(symbol: str, refresh: bool = False):
    if not refresh:
        return get_cached_stock_news(_resolve_sym(symbol))
    return get_stock_news(_resolve_sym(symbol), force_refresh=refresh)


@router.get("/stock/{symbol}/insights")
def api_insights(symbol: str):
    return search_stock_insights(_resolve_sym(symbol))


@router.get("/stock/{symbol}/summary")
def api_summary(symbol: str, refresh: bool = True):
    try:
        sym = _resolve_sym(symbol)
        context = build_stock_ai_context(sym, force_refresh=refresh)
        return generate_summary(sym, context)
    except Exception as e:
        return {"enabled": False, "summary": f"数据获取失败: {str(e)}"}


@router.get("/stock/{symbol}/summary/latest")
def api_latest_summary(symbol: str, response: Response):
    response.headers["Cache-Control"] = "public, max-age=60"
    return get_latest_summary(_resolve_sym(symbol))


@router.get("/stock/{symbol}/full")
def api_full_analysis(symbol: str, refresh: bool = False):
    if _is_crypto(symbol):
        csym = _crypto_sym(symbol)
        result = {}
        try:
            result["info"] = get_crypto_info(csym) or {}
        except Exception:
            result["info"] = {}
        try:
            result["history"] = get_crypto_history(csym, period="6mo")
        except Exception:
            result["history"] = []
        result["analyst"] = {}
        result["financials"] = {}
        result["periods"] = get_crypto_periods(csym) or {"changes": {}, "signals": {}}
        try:
            tech = get_crypto_indicators(csym)
            if tech:
                result["technical"] = {
                    "latest_price": tech.get("latest_price"),
                    "signals": tech.get("signals"),
                    "rsi": tech.get("rsi", [])[-1] if tech.get("rsi") else None,
                    "macd": {k: v[-1] if v else None for k, v in tech.get("macd", {}).items()},
                    "bollinger": {k: v[-1] if v else None for k, v in tech.get("bollinger", {}).items()},
                }
            else:
                result["technical"] = {"latest_price": result["info"].get("current_price"), "signals": []}
        except Exception:
            result["technical"] = {"latest_price": result["info"].get("current_price"), "signals": []}
        result["summary"] = {"enabled": False, "summary": ""}
        result["news"] = []
        return result

    sym = _resolve_sym(symbol)
    result = {}

    from concurrent.futures import ThreadPoolExecutor

    def _safe(fn, default):
        try:
            return fn()
        except Exception:
            return default

    with ThreadPoolExecutor(max_workers=6) as ex:
        f_info = ex.submit(_safe, lambda: get_stock_info(sym, force_refresh=refresh), {"symbol": sym, "name": "获取失败"})
        f_history = ex.submit(_safe, lambda: get_stock_history(sym)[-90:], [])
        f_analyst = ex.submit(_safe, lambda: get_analyst_info(sym), {})
        f_fin = ex.submit(_safe, lambda: get_financials(sym, force_refresh=refresh), {})
        f_periods = ex.submit(_safe, lambda: get_period_analysis(sym), {"changes": {}, "signals": {}})
        f_tech = ex.submit(_safe, lambda: calculate_all_indicators(sym), None)

        result["info"] = f_info.result()
        result["history"] = f_history.result()
        result["analyst"] = f_analyst.result()
        result["financials"] = f_fin.result()
        result["periods"] = f_periods.result()

        tech = f_tech.result()
        if tech:
            result["technical"] = {
                "latest_price": tech.get("latest_price"),
                "signals": tech.get("signals"),
                "rsi": tech.get("rsi", [])[-1] if tech.get("rsi") else None,
                "macd": {k: v[-1] if v else None for k, v in tech.get("macd", {}).items()},
                "bollinger": {k: v[-1] if v else None for k, v in tech.get("bollinger", {}).items()},
            }
        else:
            result["technical"] = {"latest_price": None, "signals": []}

    result["summary"] = get_latest_summary(sym)

    return result


@router.get("/search")
def api_search(q: str = Query(..., min_length=1)):
    return search_stocks(q)


@router.get("/watchlist")
def api_get_watchlist():
    return {"symbols": load_watchlist()}


@router.post("/watchlist/{symbol}")
def api_add_watchlist(symbol: str):
    sym = _resolve_sym(symbol)
    if _is_crypto(sym) and not sym.startswith("CRYPTO:"):
        # Store as CRYPTO:BTC-USDT (full pair)
        base = sym.replace("-USDT","").replace("-USD","")
        sym = "CRYPTO:" + base + "-USDT"
    return {"symbols": add_to_watchlist(sym)}


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
def api_update_config(body: ConfigUpdate):
    current = _load_json_config()
    for section in ("llm", "proxy", "sec"):
        section_data = getattr(body, section, None)
        if section_data and isinstance(section_data, dict):
            for k, v in section_data.items():
                # Ignore masked api_key values to avoid overwriting the real key
                if section == "llm" and k == "api_key" and isinstance(v, str) and "****" in v:
                    continue
                current.setdefault(section, {})[k] = v
    save_json_config(current)
    from backend.utils.proxy import setup_proxy
    setup_proxy()
    return {"status": "ok"}


@router.get("/stock/{symbol}/ai-history")
def api_ai_history(symbol: str, response: Response):
    response.headers["Cache-Control"] = "public, max-age=120"
    sym = _resolve_sym(symbol).upper().strip()
    with db_session() as db:
        rows = db.query(LLMCache).filter(
            LLMCache.symbol == sym
        ).order_by(LLMCache.created_at.desc()).limit(10).all()
        return [{
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else "",
            "content": r.content,
        } for r in rows]


@router.get("/ai/queue")
def api_ai_queue():
    """Observe AI task queue status."""
    return ai_queue_status()


@router.post("/ai/queue/{symbol}")
def api_ai_enqueue(symbol: str):
    """Manually enqueue a symbol for AI generation."""
    enqueue_ai(_resolve_sym(symbol))
    return {"status": "ok"}


@router.get("/circuits")
def api_circuits():
    """Observe circuit breaker states."""
    return circuit_status()


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
    with db_session() as db:
        session = HuntSession(
            market=market,
            sector=sector,
            data=result,
            total=result["total"],
        )
        db.add(session)
        db.commit()
        result["created_at"] = session.created_at.isoformat() if session.created_at else ""
    return result


@router.get("/hunt/history")
def api_hunt_history(response: Response):
    response.headers["Cache-Control"] = "public, max-age=120"
    with db_session() as db:
        rows = db.query(HuntSession).order_by(HuntSession.created_at.desc()).limit(20).all()
        return [{
            "id": r.id,
            "market": r.market,
            "sector": r.sector,
            "total": r.total,
            "created_at": r.created_at.isoformat() if r.created_at else "",
        } for r in rows]


@router.get("/hunt/history/{session_id}")
def api_hunt_session_detail(session_id: int):
    with db_session() as db:
        row = db.query(HuntSession).filter(HuntSession.id == session_id).first()
        if not row:
            raise HTTPException(status_code=404)
        return row.data


# ---------- Trading Journal ----------
@router.get("/trades")
def api_get_trades():
    return get_all_trades()


@router.get("/trades/stats")
def api_trade_stats():
    return get_trade_stats()


@router.get("/trades/portfolio")
def api_portfolio(interval: str = "1d", range_key: str = "all"):
    return get_portfolio(interval=interval, range_key=range_key)


# ---------- Institution Holdings ----------
@router.get("/institutions")
def api_institutions(refresh: bool = False):
    return get_institutions(refresh=refresh)


@router.get("/institutions/history")
def api_institution_history(response: Response):
    response.headers["Cache-Control"] = "public, max-age=300"
    return {"history": get_institution_history()}


@router.get("/institutions/history/{snapshot_id}")
def api_institution_history_detail(snapshot_id: str):
    result = get_institution_history_detail(snapshot_id)
    if not result:
        raise HTTPException(status_code=404, detail="历史记录不存在")
    return result


@router.post("/institutions/warm-mappings")
def api_warm_institution_mappings(limit: int = 200):
    return warm_institution_mappings(limit=limit)


@router.get("/institutions/{institution_id}")
def api_institution_detail(institution_id: str):
    result = get_institution(institution_id)
    if not result:
        raise HTTPException(status_code=404, detail="机构不存在")
    return result


@router.post("/trades")
def api_create_trade(body: TradeCreate):
    return create_trade(body.model_dump())


@router.put("/trades/{trade_id}")
def api_update_trade(trade_id: str, body: TradeUpdate):
    result = update_trade(trade_id, body.model_dump(exclude_unset=True))
    if not result:
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return result


@router.delete("/trades/{trade_id}")
def api_delete_trade(trade_id: str):
    if not delete_trade(trade_id):
        raise HTTPException(status_code=404, detail="交易记录不存在")
    return {"status": "ok"}
