import json
import time
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, get_proxy_dict


MAPPING_FILE = DATA_DIR / "cusip_mapping_cache.json"
SEC_TICKER_FILE = DATA_DIR / "sec_ticker_cache.json"
SEC_EXCHANGE_FILE = DATA_DIR / "sec_ticker_exchange_cache.json"
NASDAQ_DIRECTORY_FILE = DATA_DIR / "nasdaq_directory_cache.json"
TICKER_SECTOR_FILE = DATA_DIR / "ticker_sector_cache.json"
MAP_TTL_SECONDS = 30 * 24 * 60 * 60
US_EXCHANGES = {"US", "UN", "UW", "UQ", "UP", "UA", "UC", "UB", "UT", "UM", "UX", "UD", "UF"}


def _load_cache() -> dict[str, Any]:
    if not MAPPING_FILE.exists():
        return {}
    try:
        data = json.loads(MAPPING_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    MAPPING_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def _norm_name(name: str) -> str:
    import re
    text = re.sub(r"[^A-Z0-9]+", " ", (name or "").upper()).strip()
    suffixes = [" INC", " CORP", " CORPORATION", " CO", " LTD", " PLC", " HOLDINGS", " HLDGS", " GROUP", " NEW", " DEL", " COM", " CL A", " CL B", " CLASS A", " CLASS B"]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return re.sub(r"[^A-Z0-9]", "", text)


def _tokens(name: str) -> set[str]:
    import re
    stop = {"INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "HOLDINGS", "HLDGS", "GROUP", "NEW", "DEL", "COM", "CLASS", "CL", "DE", "THE"}
    return {t for t in re.findall(r"[A-Z0-9]+", (name or "").upper()) if t not in stop and len(t) > 1}


def _load_sec_ticker_cache() -> dict[str, Any]:
    if SEC_TICKER_FILE.exists():
        try:
            data = json.loads(SEC_TICKER_FILE.read_text(encoding="utf-8"))
            if time.time() - float(data.get("updated_at_ts") or 0) < MAP_TTL_SECONDS:
                return data.get("map", {})
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    try:
        import requests
        r = requests.get("https://www.sec.gov/files/company_tickers.json", headers={"User-Agent": "StockTracing/1.0 contact@example.com"}, timeout=20, proxies=get_proxy_dict())
        r.raise_for_status()
        result = {}
        for row in r.json().values():
            title = row.get("title", "")
            ticker = row.get("ticker", "")
            key = _norm_name(title)
            if key and ticker:
                result[key] = {"ticker": ticker.upper(), "name": title}
        SEC_TICKER_FILE.write_text(json.dumps({"updated_at_ts": time.time(), "map": result}, ensure_ascii=False), encoding="utf-8")
        return result
    except Exception:
        return {}


def _download_sec_exchange_directory() -> dict[str, Any]:
    try:
        import requests
        r = requests.get("https://www.sec.gov/files/company_tickers_exchange.json", headers={"User-Agent": "StockTracing/1.0 contact@example.com"}, timeout=20, proxies=get_proxy_dict())
        r.raise_for_status()
        payload = r.json()
        fields = payload.get("fields", [])
        data = payload.get("data", [])
        result = {}
        for values in data:
            row = dict(zip(fields, values))
            ticker = str(row.get("ticker", "")).upper().strip()
            title = row.get("name", "") or row.get("title", "")
            if ticker:
                result[ticker] = {"ticker": ticker, "name": title, "exchange": row.get("exchange", ""), "source": "sec_exchange"}
        SEC_EXCHANGE_FILE.write_text(json.dumps({"updated_at_ts": time.time(), "map": result}, ensure_ascii=False), encoding="utf-8")
        return result
    except Exception:
        return {}


def _parse_pipe_directory(text: str, source: str) -> dict[str, Any]:
    lines = [line for line in text.splitlines() if "|" in line]
    if not lines:
        return {}
    headers = lines[0].split("|")
    result = {}
    for line in lines[1:]:
        if line.startswith("File Creation"):
            continue
        values = line.split("|")
        row = dict(zip(headers, values))
        ticker = (row.get("Symbol") or row.get("ACT Symbol") or "").upper().strip()
        name = row.get("Security Name") or row.get("SecurityName") or ""
        if ticker:
            result[ticker] = {
                "ticker": ticker,
                "name": name,
                "exchange": row.get("Listing Exchange", "NASDAQ" if source == "nasdaq" else ""),
                "is_etf": row.get("ETF", "N") == "Y",
                "source": source,
            }
    return result


def _download_nasdaq_directory() -> dict[str, Any]:
    try:
        import requests
        urls = [
            ("nasdaq", "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"),
            ("otherlisted", "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"),
        ]
        result = {}
        for source, url in urls:
            r = requests.get(url, timeout=20, proxies=get_proxy_dict())
            r.raise_for_status()
            result.update(_parse_pipe_directory(r.text, source))
        NASDAQ_DIRECTORY_FILE.write_text(json.dumps({"updated_at_ts": time.time(), "map": result}, ensure_ascii=False), encoding="utf-8")
        return result
    except Exception:
        return {}


def _load_timed_cache(path: Path, downloader) -> dict[str, Any]:
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(data.get("updated_at_ts") or 0) < MAP_TTL_SECONDS:
                return data.get("map", {})
        except (json.JSONDecodeError, OSError, ValueError):
            pass
    return downloader()


def load_directory_index() -> dict[str, Any]:
    sec_by_name = _load_sec_ticker_cache()
    sec_exchange = _load_timed_cache(SEC_EXCHANGE_FILE, _download_sec_exchange_directory)
    nasdaq = _load_timed_cache(NASDAQ_DIRECTORY_FILE, _download_nasdaq_directory)

    by_ticker = {}
    by_ticker.update(sec_exchange)
    for ticker, row in nasdaq.items():
        by_ticker.setdefault(ticker, row)
        by_ticker[ticker] = {**row, **by_ticker[ticker]}

    by_name = dict(sec_by_name)
    for row in by_ticker.values():
        key = _norm_name(row.get("name", ""))
        if key and row.get("ticker"):
            by_name.setdefault(key, row)
    return {"by_name": by_name, "by_ticker": by_ticker}


def resolve_by_issuer_names(names: list[str]) -> dict[str, dict[str, str]]:
    master = load_directory_index()["by_name"]
    result = {}
    token_index = [(k, v, _tokens(v.get("name", ""))) for k, v in master.items()]
    for name in names:
        key = _norm_name(name)
        if key in master:
            result[name] = master[key]
            continue
        matches = [v for k, v in master.items() if k.startswith(key) or key.startswith(k)] if len(key) >= 4 else []
        if len(matches) == 1:
            result[name] = matches[0]
            continue
        for size in range(min(len(key), 16), 8, -1):
            prefix = key[:size]
            matches = [v for k, v in master.items() if k.startswith(prefix)]
            if len(matches) == 1:
                result[name] = matches[0]
                break
        if name in result:
            continue
        name_tokens = _tokens(name)
        if name_tokens and any(len(t) >= 4 for t in name_tokens):
            matches = [v for _, v, toks in token_index if name_tokens.issubset(toks)]
            if len(matches) == 1:
                result[name] = matches[0]
    return result


def _fresh(item: dict[str, Any]) -> bool:
    return bool(item.get("ticker")) and time.time() - float(item.get("updated_at_ts") or 0) < MAP_TTL_SECONDS


def _pick_figi(data: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not data:
        return None
    for row in data:
        if row.get("exchCode") == "US" and row.get("securityType2") in {"Common Stock", "ETF", "ADR"}:
            return row
    for row in data:
        if row.get("exchCode") in US_EXCHANGES:
            return row
    return data[0]


def _openfigi_map(cusips: list[str]) -> dict[str, dict[str, str]]:
    import requests

    result = {}
    for i in range(0, len(cusips), 10):
        batch = cusips[i:i + 10]
        payload = [{"idType": "ID_CUSIP", "idValue": c} for c in batch]
        r = requests.post(
            "https://api.openfigi.com/v3/mapping",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=25,
            proxies=get_proxy_dict(),
        )
        if r.status_code == 413 and len(batch) > 1:
            result.update(_openfigi_map(batch[: len(batch) // 2]))
            result.update(_openfigi_map(batch[len(batch) // 2 :]))
            continue
        r.raise_for_status()
        for cusip, item in zip(batch, r.json()):
            picked = _pick_figi(item.get("data", []))
            if picked:
                result[cusip] = {
                    "ticker": picked.get("ticker", ""),
                    "name": picked.get("name", ""),
                    "security_type": picked.get("securityType2") or picked.get("securityType", ""),
                    "exchange": picked.get("exchCode", ""),
                }
        time.sleep(0.35)
    return result


def _sector_from_yfinance(ticker: str) -> str:
    if not ticker:
        return ""
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info or {}
        return info.get("sector") or ""
    except Exception:
        return ""


def _load_sector_cache() -> dict[str, Any]:
    if not TICKER_SECTOR_FILE.exists():
        return {}
    try:
        data = json.loads(TICKER_SECTOR_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_sector_cache(cache: dict[str, Any]) -> None:
    TICKER_SECTOR_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_ticker_sectors(tickers: list[str], limit: int = 80) -> dict[str, str]:
    cleaned = sorted({t.upper().strip() for t in tickers if t and len(t) <= 8})
    cache = _load_sector_cache()
    if limit <= 0:
        return {t: cache.get(t, "") for t in cleaned}
    missing = [t for t in cleaned if t not in cache][:limit]
    if missing:
        for ticker in missing:
            cache[ticker] = _sector_from_yfinance(ticker)
            time.sleep(0.05)
        _save_sector_cache(cache)
    return {t: cache.get(t, "") for t in cleaned}


def resolve_tickers(tickers: list[str]) -> dict[str, dict[str, Any]]:
    by_ticker = load_directory_index()["by_ticker"]
    cleaned = {t.upper().strip() for t in tickers if t}
    return {t: by_ticker.get(t, {}) for t in cleaned if by_ticker.get(t)}


def resolve_cusips(cusips: list[str], enrich_sector: bool = True) -> dict[str, dict[str, Any]]:
    cleaned = sorted({c.upper().strip() for c in cusips if c})
    cache = _load_cache()
    missing = [c for c in cleaned if not _fresh(cache.get(c, {}))]

    if missing:
        try:
            mapped = _openfigi_map(missing)
        except Exception:
            mapped = {}
        now = time.time()
        for cusip, item in mapped.items():
            sector = cache.get(cusip, {}).get("sector", "")
            if enrich_sector and not sector:
                sector = _sector_from_yfinance(item.get("ticker", ""))
            cache[cusip] = {**item, "sector": sector, "updated_at_ts": now}
        for cusip in missing:
            cache.setdefault(cusip, {"ticker": "", "name": "", "sector": "", "updated_at_ts": now})
        _save_cache(cache)

    return {c: cache.get(c, {}) for c in cleaned}


def cached_cusip_mappings(cusips: list[str]) -> dict[str, dict[str, Any]]:
    cache = _load_cache()
    cleaned = {c.upper().strip() for c in cusips if c}
    return {c: cache.get(c, {}) for c in cleaned if cache.get(c, {}).get("ticker")}
