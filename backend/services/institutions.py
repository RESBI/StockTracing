import json
import shutil
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR, TTL, get_proxy_dict, get_sec_user_agent
from backend.services.institution_mapper import cached_cusip_mappings, resolve_by_issuer_names, resolve_cusips, resolve_ticker_sectors, resolve_tickers
from backend.services.institution_normalizer import normalize_holdings
from backend.utils.circuit_breaker import circuit


HOLDINGS_FILE = DATA_DIR / "institution_holdings.json"
VISIBLE_CACHE_FILE = DATA_DIR / "institution_visible_cache.json"
HISTORY_DIR = DATA_DIR / "institution_holdings_history"
REFRESH_INTERVAL_SECONDS = TTL.INSTITUTIONS


def _sec_headers() -> dict[str, str]:
    return {
        "User-Agent": get_sec_user_agent(),
        "Accept-Encoding": "gzip, deflate",
    }


SEC_INSTITUTIONS = [
    {"id": "berkshire-hathaway", "name": "Berkshire Hathaway", "manager": "Warren Buffett", "cik": "1067983"},
    {"id": "blackrock", "name": "BlackRock", "manager": "Larry Fink", "cik": "1364742"},
    {"id": "vanguard-group", "name": "Vanguard Group", "manager": "Mortimer Buckley", "cik": "0102909"},
    {"id": "bridgewater-associates", "name": "Bridgewater Associates", "manager": "Ray Dalio", "cik": "1350694"},
    {"id": "tiger-global", "name": "Tiger Global Management", "manager": "Chase Coleman", "cik": "1167483"},
    {"id": "citadel-advisors", "name": "Citadel Advisors", "manager": "Ken Griffin", "cik": "1423053"},
    {"id": "renaissance-technologies", "name": "Renaissance Technologies", "manager": "Jim Simons", "cik": "1037389"},
    {"id": "ark-invest", "name": "ARK Invest", "manager": "Cathie Wood", "cik": "1697748"},
    {"id": "state-street", "name": "State Street", "manager": "State Street Global Advisors", "cik": "0093751"},
    {"id": "two-sigma", "name": "Two Sigma Investments", "manager": "Two Sigma", "cik": "1478735"},
    {"id": "millennium-management", "name": "Millennium Management", "manager": "Israel Englander", "cik": "1273087"},
    {"id": "point72", "name": "Point72 Asset Management", "manager": "Steven Cohen", "cik": "1603466"},
    {"id": "de-shaw", "name": "D. E. Shaw", "manager": "David Shaw", "cik": "1009207"},
    {"id": "coatue-management", "name": "Coatue Management", "manager": "Philippe Laffont", "cik": "1467679"},
]


def _load_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"institutions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"institutions": data if isinstance(data, list) else []}
    except (json.JSONDecodeError, OSError):
        return {"institutions": []}


def _save_file(data: dict[str, Any]) -> None:
    HOLDINGS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def _save_visible_cache(data: dict[str, Any]) -> None:
    VISIBLE_CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _backup_current() -> Path | None:
    if not HOLDINGS_FILE.exists():
        return None
    HISTORY_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    target = HISTORY_DIR / f"institution_holdings_{stamp}.json"
    shutil.copy2(HOLDINGS_FILE, target)
    if VISIBLE_CACHE_FILE.exists():
        shutil.copy2(VISIBLE_CACHE_FILE, _history_visible_path(stamp))
    return target


def _history_holdings_path(snapshot_id: str) -> Path:
    return HISTORY_DIR / f"institution_holdings_{snapshot_id}.json"


def _history_visible_path(snapshot_id: str) -> Path:
    return HISTORY_DIR / f"institution_visible_{snapshot_id}.json"


def _load_holdings() -> list[dict[str, Any]]:
    data = _load_file(HOLDINGS_FILE)
    institutions = data.get("institutions", [])
    return institutions if isinstance(institutions, list) else []


def _metadata() -> dict[str, Any]:
    return _load_file(HOLDINGS_FILE).get("metadata", {})


def _needs_refresh() -> bool:
    updated_at = _metadata().get("updated_at_ts")
    if not updated_at:
        return True
    return time.time() - float(updated_at) >= REFRESH_INTERVAL_SECONDS


def _http_get(url: str, timeout: int = 15) -> Any:
    import requests

    r = requests.get(url, timeout=timeout, headers=_sec_headers(), proxies=get_proxy_dict())
    r.raise_for_status()
    content_type = r.headers.get("content-type", "")
    if "json" in content_type or url.endswith(".json"):
        return r.json()
    return r.text


def _cik10(cik: str) -> str:
    return str(cik).lstrip("0").zfill(10)


def _latest_13f(cik: str) -> dict[str, str] | None:
    sub = _http_get(f"https://data.sec.gov/submissions/CIK{_cik10(cik)}.json")
    recent = sub.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    report_dates = recent.get("reportDate", [])
    filing_dates = recent.get("filingDate", [])
    for i, form in enumerate(forms):
        if str(form).startswith("13F-HR"):
            return {
                "accession": accessions[i],
                "report_date": report_dates[i] if i < len(report_dates) else "",
                "filing_date": filing_dates[i] if i < len(filing_dates) else "",
            }
    return None


def _info_table_url(cik: str, accession: str) -> str | None:
    cik_int = str(int(cik))
    accession_dir = accession.replace("-", "")
    index_url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_dir}/index.json"
    data = _http_get(index_url)
    items = data.get("directory", {}).get("item", [])
    names = [item.get("name", "") for item in items]
    for name in names:
        lname = name.lower()
        if lname.endswith(".xml") and ("info" in lname or "form13f" in lname or "primary_doc" not in lname):
            return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_dir}/{name}"
    for name in names:
        if name.lower().endswith(".xml"):
            return f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_dir}/{name}"
    return None


def _text(node: ET.Element, name: str) -> str:
    found = node.find(f".//{{*}}{name}")
    return found.text.strip() if found is not None and found.text else ""


def _parse_info_table(xml_text: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text.encode("utf-8"))
    rows = []
    for info in root.findall(".//{*}infoTable"):
        issuer = _text(info, "nameOfIssuer")
        cusip = _text(info, "cusip")
        title = _text(info, "titleOfClass")
        put_call = _text(info, "putCall")
        value = float(_text(info, "value") or 0) * 1000
        shares = float(_text(info, "sshPrnamt") or 0)
        rows.append({
            "symbol": cusip or issuer,
            "name": issuer or cusip,
            "title": title,
            "put_call": put_call,
            "sector": "未分类",
            "shares": shares,
            "price": round(value / shares, 4) if shares else 0,
            "value": round(value, 2),
            "change_shares": 0,
            "change_value": 0,
            "cusip": cusip,
        })
    return rows


def _previous_holdings_by_id() -> dict[str, dict[str, dict[str, Any]]]:
    result = {}
    for inst in _load_holdings():
        rows = {}
        for h in inst.get("holdings", []) or []:
            if h.get("cusip"):
                rows[h["cusip"]] = h
            if h.get("ticker"):
                rows[h["ticker"]] = h
            if h.get("symbol"):
                rows[h["symbol"]] = h
        result[inst.get("id", "")] = rows
    return result


@circuit("sec", failure_threshold=3, recovery_timeout=300)
def fetch_sec_13f_holdings() -> dict[str, Any]:
    previous = _previous_holdings_by_id()
    institutions = []
    errors = []
    for item in SEC_INSTITUTIONS:
        try:
            latest = _latest_13f(item["cik"])
            if not latest:
                raise RuntimeError("未找到 13F-HR")
            url = _info_table_url(item["cik"], latest["accession"])
            if not url:
                raise RuntimeError("未找到 13F 信息表 XML")
            rows = _parse_info_table(_http_get(url, timeout=25))
            issuer_map = resolve_by_issuer_names([r.get("name", "") for r in rows])
            cusip_map = resolve_cusips([r.get("cusip", "") for r in rows[:120]])
            sector_map = resolve_ticker_sectors([v.get("ticker", "") for v in issuer_map.values()], limit=0)
            ticker_map = resolve_tickers([v.get("ticker", "") for v in issuer_map.values()])
            institutions.append({
                "id": item["id"],
                "name": item["name"],
                "manager": item["manager"],
                "cik": item["cik"],
                "report_date": latest.get("report_date") or latest.get("filing_date") or "",
                "filing_date": latest.get("filing_date", ""),
                "source": "SEC EDGAR 13F",
                "holdings": normalize_holdings(rows, previous.get(item["id"], {}), cusip_map, issuer_map, sector_map, ticker_map),
            })
            time.sleep(0.12)
        except Exception as e:
            errors.append({"id": item["id"], "name": item["name"], "error": str(e)})
    if not institutions:
        raise RuntimeError("SEC 13F 拉取失败: " + "; ".join(e["name"] + " " + e["error"] for e in errors[:3]))
    return {
        "metadata": {
            "source": "SEC EDGAR 13F",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_at_ts": time.time(),
            "refresh_interval_seconds": REFRESH_INTERVAL_SECONDS,
            "errors": errors,
        },
        "institutions": institutions,
    }


def refresh_institution_holdings(force: bool = False) -> dict[str, Any]:
    if not force and not _needs_refresh():
        return _load_file(HOLDINGS_FILE)
    _backup_current()
    try:
        data = fetch_sec_13f_holdings()
        _save_file(data)
        _save_visible_cache(_summarize_data(data, include_holdings=False))
        return data
    except Exception as e:
        data = _load_file(HOLDINGS_FILE)
        data.setdefault("metadata", {})["last_refresh_error"] = str(e)
        data["metadata"]["last_refresh_error_at"] = datetime.now(timezone.utc).isoformat()
        _save_file(data)
        return data


def _holding_value(holding: dict[str, Any]) -> float:
    value = holding.get("value")
    if value is not None:
        return float(value or 0)
    shares = float(holding.get("shares") or 0)
    price = float(holding.get("price") or 0)
    return shares * price


def _trend(delta_value: float) -> str:
    if delta_value > 0:
        return "up"
    if delta_value < 0:
        return "down"
    return "flat"


def _raw_value(row: dict[str, Any]) -> float:
    value = _holding_value(row)
    shares = float(row.get("shares") or 0)
    if shares and value / shares > 10000:
        return value / 1000
    return value


def _summarize_institution(inst: dict[str, Any], include_holdings: bool = True) -> dict[str, Any]:
    holdings = inst.get("holdings", [])
    if not isinstance(holdings, list):
        holdings = []
    source_rows = holdings
    if include_holdings:
        unresolved = [h.get("cusip", "") for h in holdings if h.get("cusip") and not h.get("ticker")]
        issuer_map = resolve_by_issuer_names([h.get("name", "") for h in holdings])
        cusip_map = cached_cusip_mappings(unresolved)
        if unresolved:
            cusip_map.update(resolve_cusips(unresolved[:30], enrich_sector=False))
        sector_map = resolve_ticker_sectors([v.get("ticker", "") for v in issuer_map.values()], limit=0)
        ticker_map = resolve_tickers([v.get("ticker", "") for v in issuer_map.values()])
        source_rows = normalize_holdings(holdings, external_map=cusip_map, issuer_map=issuer_map, sector_map=sector_map, ticker_map=ticker_map)
    else:
        issuer_map = resolve_by_issuer_names([h.get("name", "") for h in holdings])
        cusip_map = cached_cusip_mappings([h.get("cusip", "") for h in holdings])
        sector_map = resolve_ticker_sectors([v.get("ticker", "") for v in issuer_map.values()], limit=0)
        ticker_map = resolve_tickers([v.get("ticker", "") for v in issuer_map.values()])
        source_rows = normalize_holdings(holdings, external_map=cusip_map, issuer_map=issuer_map, sector_map=sector_map, ticker_map=ticker_map)
        raw_total = sum(_holding_value(h) for h in source_rows)

    rows = []
    sector_totals: dict[str, float] = defaultdict(float)
    total_value = 0.0 if include_holdings else raw_total

    for h in source_rows:
        value = _holding_value(h)
        delta_value = float(h.get("change_value") or 0)
        sector = h.get("sector") or "未分类"
        if include_holdings:
            total_value += value
        sector_totals[sector] += value
        rows.append({
            "symbol": h.get("symbol", ""),
            "ticker": h.get("ticker", ""),
            "name": h.get("name") or h.get("symbol", ""),
            "display_symbol": h.get("display_symbol") or h.get("symbol", ""),
            "display_name": h.get("display_name") or h.get("name") or h.get("symbol", ""),
            "asset_type": h.get("asset_type", "SHARE"),
            "security_type": h.get("security_type", ""),
            "badge": h.get("badge", ""),
            "is_option": bool(h.get("is_option")),
            "sector": sector,
            "shares": float(h.get("shares") or 0),
            "price": float(h.get("price") or 0),
            "value": round(value, 2),
            "weight": 0,
            "change_shares": float(h.get("change_shares") or 0),
            "change_value": round(delta_value, 2),
            "trend": _trend(delta_value),
            "cusip": h.get("cusip", ""),
            "cusips": h.get("cusips", []),
        })

    rows.sort(key=lambda x: x["value"], reverse=True)
    for i, row in enumerate(rows, 1):
        row["index"] = i
        row["weight"] = round(row["value"] / total_value * 100, 2) if total_value else 0

    top_assets = [{
        "symbol": row["symbol"],
        "display_symbol": row.get("display_symbol") or row["symbol"],
        "name": row["name"],
        "display_name": row.get("display_name") or row["name"],
        "asset_type": row.get("asset_type", "SHARE"),
        "security_type": row.get("security_type", ""),
        "badge": row.get("badge", ""),
        "value": row["value"],
        "weight": row["weight"],
    } for row in rows[:10]]

    sectors = [{
        "sector": sector,
        "value": round(value, 2),
        "weight": round(value / total_value * 100, 2) if total_value else 0,
    } for sector, value in sector_totals.items()]
    sectors.sort(key=lambda x: x["value"], reverse=True)

    return {
        "id": inst.get("id") or inst.get("name", "").lower().replace(" ", "-"),
        "name": inst.get("name", "未知机构"),
        "manager": inst.get("manager", ""),
        "report_date": inst.get("report_date", ""),
        "filing_date": inst.get("filing_date", ""),
        "source": inst.get("source", "本地缓存"),
        "total_value": round(total_value, 2),
        "holding_count": len(rows) if include_holdings else len(holdings),
        "top_assets": top_assets,
        "sectors": sectors,
        "holdings": rows if include_holdings else [],
    }


def _summarize_data(data: dict[str, Any], include_holdings: bool = True) -> dict[str, Any]:
    institutions = [_summarize_institution(inst, include_holdings=include_holdings) for inst in data.get("institutions", [])]
    institutions.sort(key=lambda x: x["total_value"], reverse=True)
    return {"metadata": data.get("metadata", {}), "institutions": institutions}


def _visible_cache_current(data: dict[str, Any], cached: dict[str, Any]) -> bool:
    return data.get("metadata", {}).get("updated_at") == cached.get("metadata", {}).get("updated_at")


def get_visible_cache(data: dict[str, Any]) -> dict[str, Any]:
    cached = _load_file(VISIBLE_CACHE_FILE)
    if cached.get("institutions") and _visible_cache_current(data, cached):
        return cached
    visible = _summarize_data(data, include_holdings=False)
    _save_visible_cache(visible)
    return visible


def get_institutions(refresh: bool = False, include_holdings: bool = False) -> dict[str, Any]:
    data = refresh_institution_holdings(force=refresh)
    if not include_holdings:
        return get_visible_cache(data)
    return _summarize_data(data, include_holdings=include_holdings)


def get_institution(institution_id: str) -> dict[str, Any] | None:
    target = institution_id.lower().strip()
    data = refresh_institution_holdings(force=False)
    for inst in data.get("institutions", []):
        inst_id = (inst.get("id") or inst.get("name", "")).lower().strip()
        if inst_id == target:
            return _summarize_institution(inst, include_holdings=True)
    return None


def get_institution_history() -> list[dict[str, Any]]:
    HISTORY_DIR.mkdir(exist_ok=True)
    rows = []
    for path in sorted(HISTORY_DIR.glob("institution_holdings_*.json"), reverse=True):
        snapshot_id = path.stem.replace("institution_holdings_", "")
        data = _load_file(path)
        visible = _load_file(_history_visible_path(snapshot_id))
        meta = data.get("metadata", {})
        modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
        rows.append({
            "id": snapshot_id,
            "file": path.name,
            "created_at": meta.get("updated_at") or modified_at,
            "source": meta.get("source", "历史备份"),
            "total": len((visible.get("institutions") or data.get("institutions") or [])),
            "visible_cached": bool(visible.get("institutions")),
        })
    return rows[:30]


def get_institution_history_detail(snapshot_id: str) -> dict[str, Any] | None:
    visible_path = _history_visible_path(snapshot_id)
    if visible_path.exists():
        visible = _load_file(visible_path)
        if visible.get("institutions"):
            return visible
    path = _history_holdings_path(snapshot_id)
    if not path.exists():
        return None
    data = _load_file(path)
    visible = _summarize_data(data, include_holdings=False)
    _history_visible_path(snapshot_id).write_text(json.dumps(visible, ensure_ascii=False, indent=2), encoding="utf-8")
    return visible


def warm_institution_mappings(limit: int = 200) -> dict[str, Any]:
    data = _load_file(HOLDINGS_FILE)
    cusips = []
    names = []
    for inst in data.get("institutions", []) or []:
        for h in inst.get("holdings", []) or []:
            if h.get("cusip"):
                cusips.append(h["cusip"])
            if h.get("name"):
                names.append(h["name"])
    issuer_map = resolve_by_issuer_names(names)
    cusip_map = resolve_cusips(cusips[:limit], enrich_sector=False)
    sector_map = resolve_ticker_sectors([v.get("ticker", "") for v in issuer_map.values()], limit=limit)
    return {
        "cusip_requested": min(len(set(cusips)), limit),
        "cusip_mapped": len([v for v in cusip_map.values() if v.get("ticker")]),
        "issuer_mapped": len(issuer_map),
        "sector_checked": len(sector_map),
    }
