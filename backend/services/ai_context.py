from typing import Any

from backend.services.analyst import get_analyst_info
from backend.services.financials import get_financials
from backend.services.news_service import get_stock_news
from backend.services.stock_data import get_stock_info
from backend.services.technical import calculate_all_indicators, get_period_analysis


def _compact_news(news: list[dict], limit: int = 6) -> list[dict]:
    return [{
        "title": n.get("title", ""),
        "snippet": n.get("snippet", ""),
        "source": n.get("source", ""),
        "date": n.get("date", ""),
    } for n in (news or [])[:limit]]


def _compact_periods(periods: dict) -> dict:
    return {
        "changes": (periods or {}).get("changes", {}),
        "signals": (periods or {}).get("signals", {}),
    }


def _compact_technical(tech: dict) -> dict:
    if not tech:
        return {}
    return {
        "latest_price": tech.get("latest_price"),
        "signals": (tech.get("signals") or [])[-10:],
        "rsi": (tech.get("rsi") or [None])[-1],
        "macd": {k: (v[-1] if isinstance(v, list) and v else None) for k, v in (tech.get("macd") or {}).items()},
        "bollinger": {k: (v[-1] if isinstance(v, list) and v else None) for k, v in (tech.get("bollinger") or {}).items()},
    }


def _compact_financials(financials: dict) -> dict:
    fields = (
        "Total Revenue", "Operating Revenue", "Revenue",
        "Net Income", "Operating Income", "Gross Profit",
        "Free Cash Flow", "Operating Cash Flow", "Total Cash From Operating Activities",
        "Total Assets", "Total Liabilities Net Minority Interest",
    )

    def pick(rows: list[dict], limit: int = 4) -> list[dict]:
        compact = []
        for row in (rows or [])[:limit]:
            item = {"period": row.get("period")}
            for key in fields:
                if key in row:
                    item[key] = row.get(key)
            compact.append(item)
        return compact

    return {
        "annual_income": pick((financials or {}).get("income_statement", [])),
        "quarterly_income": pick((financials or {}).get("quarterly_income", []), 6),
        "annual_cash_flow": pick((financials or {}).get("cash_flow", [])),
        "annual_balance_sheet": pick((financials or {}).get("balance_sheet", [])),
    }


def build_ai_context(info: dict, analyst: dict, tech: dict, periods: dict, financials: dict, news: list[dict]) -> dict:
    return {
        "基本信息": {k: v for k, v in (info or {}).items() if k not in ("raw_info", "error")},
        "近期资讯": _compact_news(news),
        "不同时间段涨跌与信号": _compact_periods(periods),
        "技术指标": _compact_technical(tech),
        "机构评级": {
            **(analyst or {}),
            "recent_ratings": (analyst or {}).get("recent_ratings", [])[:8],
            "upgrades_downgrades": (analyst or {}).get("upgrades_downgrades", [])[:8],
        },
        "营收与财务摘要": _compact_financials(financials),
    }


def build_stock_ai_context(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    info = get_stock_info(sym)
    try:
        analyst = get_analyst_info(sym)
    except Exception:
        analyst = {}
    try:
        financials = get_financials(sym)
    except Exception:
        financials = {}
    try:
        periods = get_period_analysis(sym)
    except Exception:
        periods = {}
    try:
        news = get_stock_news(sym)
    except Exception:
        news = []
    try:
        tech = calculate_all_indicators(sym)
    except Exception:
        tech = {}
    return build_ai_context(info, analyst, tech, periods, financials, news)
