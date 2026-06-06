import json
from datetime import datetime, timezone, timedelta
from typing import Any

from backend.config import DATA_DIR, NEWS_CACHE_TTL, retry_on_rate_limit


NEWS_CACHE_DIR = DATA_DIR / "news_cache"
NEWS_CACHE_DIR.mkdir(exist_ok=True)


def _get_cache_path(symbol: str) -> str:
    return str(NEWS_CACHE_DIR / f"{symbol.upper()}.json")


def _read_cache(symbol: str, ignore_ttl: bool = False) -> list[dict] | None:
    path = _get_cache_path(symbol)
    if not __import__("os").path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.loads(f.read())
        ts = data.get("_ts", 0)
        age = datetime.now(timezone.utc).timestamp() - ts
        if ignore_ttl or age < NEWS_CACHE_TTL:
            return data.get("items", [])
    except Exception:
        pass
    return None


def _write_cache(symbol: str, items: list[dict]) -> None:
    try:
        with open(_get_cache_path(symbol), "w", encoding="utf-8") as f:
            f.write(json.dumps({
                "_ts": datetime.now(timezone.utc).timestamp(),
                "items": items,
            }, ensure_ascii=False, indent=2))
    except Exception:
        pass


def _search_web(query: str, max_results: int = 8) -> list[dict]:
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="us-en", safesearch="off", max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
        return results
    except Exception:
        return []


def get_stock_news(symbol: str, force_refresh: bool = False) -> list[dict]:
    sym = symbol.upper().strip()

    if not force_refresh:
        cached = _read_cache(sym, ignore_ttl=True)
        if cached is not None:
            return cached

    results = []

    try:
        import yfinance as yf
        ticker = yf.Ticker(sym)
        news = ticker.news
        if news:
            for item in news[:5]:
                content = item.get("content", {})
                results.append({
                    "title": content.get("title", ""),
                    "url": content.get("canonicalUrl", {}).get("url", ""),
                    "snippet": content.get("summary", ""),
                    "source": content.get("provider", {}).get("displayName", ""),
                    "date": content.get("pubDate", ""),
                })
    except Exception:
        pass

    web_query = f"{sym} stock analysis financial report latest news"
    web_results = _search_web(web_query, max_results=6)
    for wr in web_results:
        if not any(r.get("url") == wr.get("url") for r in results):
            results.append(wr)

    try:
        company_name = ""
        try:
            import yfinance as yf
            t = yf.Ticker(sym)
            company_name = (t.info or {}).get("longName", "") or (t.info or {}).get("shortName", "")
        except Exception:
            pass

        if company_name:
            cn_query = f"{company_name} 股票 财报 分析"
            cn_results = _search_web(cn_query, max_results=4)
            for cr in cn_results:
                if not any(r.get("url") == cr.get("url") for r in results):
                    results.append(cr)
    except Exception:
        pass

    _write_cache(sym, results)
    return results


def get_cached_stock_news(symbol: str) -> list[dict]:
    return _read_cache(symbol.upper().strip(), ignore_ttl=True) or []


def search_stock_insights(symbol: str) -> dict[str, Any]:
    sym = symbol.upper().strip()
    queries = {
        "fundamentals": f"{sym} stock fundamental analysis revenue earnings growth",
        "technicals": f"{sym} stock technical analysis RSI MACD support resistance",
        "analyst_ratings": f"{sym} stock analyst rating price target upgrade downgrade",
        "risks": f"{sym} stock risks challenges competition",
    }

    insights: dict[str, list[dict]] = {}
    for key, query in queries.items():
        insights[key] = _search_web(query, max_results=3)

    return insights
