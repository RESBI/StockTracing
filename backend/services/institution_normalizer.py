import re
from typing import Any


CUSIP_MAP: dict[str, dict[str, str]] = {
    "037833100": {"ticker": "AAPL", "name": "Apple", "sector": "科技"},
    "025816109": {"ticker": "AXP", "name": "American Express", "sector": "金融"},
    "060505104": {"ticker": "BAC", "name": "Bank of America", "sector": "金融"},
    "191216100": {"ticker": "KO", "name": "Coca-Cola", "sector": "消费防御"},
    "166764100": {"ticker": "CVX", "name": "Chevron", "sector": "能源"},
    "674599105": {"ticker": "OXY", "name": "Occidental Petroleum", "sector": "能源"},
    "500754106": {"ticker": "KHC", "name": "Kraft Heinz", "sector": "消费防御"},
    "615369105": {"ticker": "MCO", "name": "Moody's", "sector": "金融"},
    "H1467J104": {"ticker": "CB", "name": "Chubb", "sector": "金融"},
    "92826C839": {"ticker": "V", "name": "Visa", "sector": "金融"},
    "57636Q104": {"ticker": "MA", "name": "Mastercard", "sector": "金融"},
    "02079K305": {"ticker": "GOOGL", "name": "Alphabet", "sector": "通信服务"},
    "02079K107": {"ticker": "GOOG", "name": "Alphabet", "sector": "通信服务"},
    "594918104": {"ticker": "MSFT", "name": "Microsoft", "sector": "科技"},
    "67066G104": {"ticker": "NVDA", "name": "NVIDIA", "sector": "科技"},
    "023135106": {"ticker": "AMZN", "name": "Amazon", "sector": "可选消费"},
    "30303M102": {"ticker": "META", "name": "Meta Platforms", "sector": "通信服务"},
    "88160R101": {"ticker": "TSLA", "name": "Tesla", "sector": "可选消费"},
    "46625H100": {"ticker": "JPM", "name": "JPMorgan Chase", "sector": "金融"},
    "532457108": {"ticker": "LLY", "name": "Eli Lilly", "sector": "医疗保健"},
    "30231G102": {"ticker": "XOM", "name": "Exxon Mobil", "sector": "能源"},
    "11135F101": {"ticker": "AVGO", "name": "Broadcom", "sector": "科技"},
    "91324P102": {"ticker": "UNH", "name": "UnitedHealth", "sector": "医疗保健"},
    "742718109": {"ticker": "PG", "name": "Procter & Gamble", "sector": "消费防御"},
    "437076102": {"ticker": "HD", "name": "Home Depot", "sector": "可选消费"},
    "78462F103": {"ticker": "SPY", "name": "SPDR S&P 500 ETF", "sector": "ETF"},
    "46090E103": {"ticker": "QQQ", "name": "Invesco QQQ Trust", "sector": "ETF"},
    "78463X889": {"ticker": "GLD", "name": "SPDR Gold Shares", "sector": "商品"},
    "81369Y506": {"ticker": "XLE", "name": "Energy Select Sector SPDR", "sector": "ETF"},
}

ISSUER_KEYWORD_MAP: list[tuple[str, dict[str, str]]] = [
    ("APPLE", {"ticker": "AAPL", "sector": "科技"}),
    ("MICROSOFT", {"ticker": "MSFT", "sector": "科技"}),
    ("NVIDIA", {"ticker": "NVDA", "sector": "科技"}),
    ("AMAZON", {"ticker": "AMZN", "sector": "可选消费"}),
    ("META PLATFORMS", {"ticker": "META", "sector": "通信服务"}),
    ("ALPHABET", {"ticker": "GOOGL", "sector": "通信服务"}),
    ("TESLA", {"ticker": "TSLA", "sector": "可选消费"}),
    ("BANK AMERICA", {"ticker": "BAC", "sector": "金融"}),
    ("COCA COLA", {"ticker": "KO", "sector": "消费防御"}),
    ("CHEVRON", {"ticker": "CVX", "sector": "能源"}),
    ("OCCIDENTAL", {"ticker": "OXY", "sector": "能源"}),
    ("AMERICAN EXPRESS", {"ticker": "AXP", "sector": "金融"}),
    ("MOODYS", {"ticker": "MCO", "sector": "金融"}),
    ("CHUBB", {"ticker": "CB", "sector": "金融"}),
    ("KRAFT HEINZ", {"ticker": "KHC", "sector": "消费防御"}),
    ("DAVITA", {"ticker": "DVA", "sector": "医疗保健"}),
    ("KROGER", {"ticker": "KR", "sector": "消费防御"}),
    ("SIRIUS", {"ticker": "SIRI", "sector": "通信服务"}),
    ("DELTA AIR", {"ticker": "DAL", "sector": "工业"}),
    ("VERISIGN", {"ticker": "VRSN", "sector": "科技"}),
    ("CAPITAL ONE", {"ticker": "COF", "sector": "金融"}),
    ("NEW YORK TIMES", {"ticker": "NYT", "sector": "通信服务"}),
    ("ALLY", {"ticker": "ALLY", "sector": "金融"}),
    ("LENNAR", {"ticker": "LEN", "sector": "可选消费"}),
    ("NUCOR", {"ticker": "NUE", "sector": "基础材料"}),
    ("LOUISIANA PAC", {"ticker": "LPX", "sector": "基础材料"}),
    ("CONSTELLATION BRANDS", {"ticker": "STZ", "sector": "消费防御"}),
    ("NVR", {"ticker": "NVR", "sector": "可选消费"}),
    ("MACYS", {"ticker": "M", "sector": "可选消费"}),
    ("JEFFERIES", {"ticker": "JEF", "sector": "金融"}),
    ("LIBERTY LIVE", {"ticker": "LLYVK", "sector": "通信服务"}),
    ("ETF", {"ticker": "", "sector": "ETF"}),
    ("ISHARES", {"ticker": "", "sector": "ETF"}),
    ("SPDR", {"ticker": "", "sector": "ETF"}),
]

SECTOR_TRANSLATIONS = {
    "Technology": "科技",
    "Financial Services": "金融",
    "Financial": "金融",
    "Communication Services": "通信服务",
    "Consumer Cyclical": "可选消费",
    "Consumer Discretionary": "可选消费",
    "Consumer Defensive": "消费防御",
    "Consumer Staples": "消费防御",
    "Healthcare": "医疗保健",
    "Health Care": "医疗保健",
    "Energy": "能源",
    "Industrials": "工业",
    "Industrial": "工业",
    "Basic Materials": "基础材料",
    "Materials": "基础材料",
    "Real Estate": "房地产",
    "Utilities": "公用事业",
}

TICKER_SECTOR_MAP = {
    "DVA": "医疗保健", "KR": "消费防御", "SIRI": "通信服务", "DAL": "工业", "VRSN": "科技",
    "COF": "金融", "NYT": "通信服务", "ALLY": "金融", "LLYVK": "通信服务", "LLYVA": "通信服务",
    "LEN": "可选消费", "LEN.B": "可选消费", "NUE": "基础材料", "LPX": "基础材料", "STZ": "消费防御",
    "NVR": "可选消费", "M": "可选消费", "JEF": "金融",
}


def clean_ticker(value: str) -> str:
    ticker = (value or "").upper().strip()
    ticker = ticker.replace(" ", "").replace("/", ".")
    if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", ticker):
        return ticker
    return ""


def normalize_issuer(name: str) -> str:
    text = re.sub(r"\s+", " ", (name or "").upper()).strip()
    suffixes = [" COM", " CL A", " CL B", " CLASS A", " CLASS B", " INC", " CORP", " CORPORATION", " LTD", " PLC"]
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text.title()


def normalize_sector(sector: str) -> str:
    sector = (sector or "").strip()
    return SECTOR_TRANSLATIONS.get(sector, sector or "未分类")


def infer_from_issuer(name: str) -> dict[str, str] | None:
    issuer = (name or "").upper()
    for keyword, mapped in ISSUER_KEYWORD_MAP:
        if keyword in issuer:
            return {"ticker": mapped.get("ticker", ""), "name": normalize_issuer(name), "sector": mapped.get("sector", "未分类")}
    return None


def infer_sector_from_name(name: str) -> str:
    issuer = (name or "").upper()
    rules = [
        (("BIO", "BIOTECH", "PHARMA", "THERAPEUTICS", "MEDICAL", "HEALTH", "LABS", "DIAGNOSTICS", "HOSPITAL", "SURGICAL", "GENOMICS", "LIFE SCIENCES", "IMMUNE", "ONCOLOGY", "CLINICAL", "PHARMACEUTICAL", "SCIENCES"), "医疗保健"),
        (("BANK", "BANC", "FINANC", "CAPITAL", "INSURANCE", "ASSURANCE", "MORTGAGE", "CREDIT", "ASSET", "INVEST", "BROKER", "EXCHANGE", "SOURCE CORP"), "金融"),
        (("SOFTWARE", "SEMICONDUCTOR", "NETWORK", "SYSTEMS", "TECH", "DIGITAL", "DATA", "CLOUD", "CYBER", "ELECTRONICS", "COMPUTER", "MICRO", "DEVICES", "3D", "ROBOTICS", "8X8"), "科技"),
        (("MEDIA", "COMMUNICATION", "ENTERTAINMENT", "BROADCAST", "CABLE", "TELECOM", "PUBLISH", "NEWS", "RADIO"), "通信服务"),
        (("ENERGY", "OIL", "GAS", "PETROLEUM", "DRILL", "MIDSTREAM", "PIPELINE", "SOLAR", "POWER"), "能源"),
        (("REALTY", "REIT", "PROPERTIES", "PROPERTY", "REAL ESTATE", "APARTMENT", "MALL", "HOTEL"), "房地产"),
        (("STEEL", "MATERIAL", "CHEM", "MINING", "METALS", "ALUMINUM", "COPPER", "PAPER", "PACKAGING", "FOREST", "LUMBER"), "基础材料"),
        (("AIR", "AEROSPACE", "DEFENSE", "INDUSTR", "MACHIN", "RAIL", "TRUCK", "LOGISTICS", "FREIGHT", "CONSTRUCTION", "TOOLS", "BRANDS", "DISTRIBUTION", "BUILDING"), "工业"),
        (("FOOD", "BEVERAGE", "GROCERY", "TOBACCO", "HOUSEHOLD", "CONSUMER PRODUCTS", "FARMS", "FLOWERS"), "消费防御"),
        (("RETAIL", "APPAREL", "RESTAURANT", "AUTO", "MOTOR", "LEISURE", "CASINO", "TRAVEL", "HOME", "FURNITURE", "SPORTS", "AUCTIONS", "EDUCATION", "BRANDS", "FITCH"), "可选消费"),
        (("UTILITY", "UTILITIES", "ELECTRIC", "WATER", "WASTE"), "公用事业"),
    ]
    for keywords, sector in rules:
        if any(k in issuer for k in keywords):
            return sector
    return ""


def normalize_value_units(value: float, shares: float) -> float:
    value = float(value or 0)
    shares = float(shares or 0)
    if shares and value / shares > 10000:
        return value / 1000
    return value


def detect_option_type(row: dict[str, Any]) -> str:
    put_call = (row.get("put_call") or row.get("putCall") or "").upper().strip()
    if put_call in {"PUT", "CALL"}:
        return put_call
    title = f"{row.get('name','')} {row.get('title','')}".upper()
    if " PUT" in title:
        return "PUT"
    if " CALL" in title:
        return "CALL"
    return "SHARE"


def map_security(row: dict[str, Any], external_map: dict[str, dict[str, Any]] | None = None, issuer_map: dict[str, dict[str, str]] | None = None, sector_map: dict[str, str] | None = None, ticker_map: dict[str, dict[str, Any]] | None = None) -> dict[str, str]:
    cusip = (row.get("cusip") or "").upper().strip()
    if external_map and cusip in external_map:
        mapped = external_map[cusip]
        if mapped.get("ticker"):
            inferred = infer_from_issuer(mapped.get("name", "") or row.get("name", "")) or {}
            ticker = clean_ticker(mapped.get("ticker", ""))
            return {"ticker": ticker, "name": mapped.get("name", ""), "sector": normalize_sector(mapped.get("sector", "") or (sector_map or {}).get(ticker, "") or inferred.get("sector", "") or TICKER_SECTOR_MAP.get(ticker, "") or infer_sector_from_name(mapped.get("name", "") or row.get("name", "")) or row.get("sector") or "未分类"), "security_type": mapped.get("security_type", "")}
    if cusip in CUSIP_MAP:
        return CUSIP_MAP[cusip]
    issuer_key = row.get("name", "")
    if issuer_map and issuer_key in issuer_map:
        mapped = issuer_map[issuer_key]
        ticker = clean_ticker(mapped.get("ticker", ""))
        inferred = infer_from_issuer(mapped.get("name", "") or issuer_key) or {}
        return {"ticker": ticker, "name": mapped.get("name", issuer_key), "sector": normalize_sector((sector_map or {}).get(ticker, "") or inferred.get("sector", "") or TICKER_SECTOR_MAP.get(ticker, "") or infer_sector_from_name(mapped.get("name", issuer_key)) or row.get("sector") or "未分类")}
    raw_ticker = clean_ticker(row.get("symbol", "") or row.get("ticker", ""))
    if raw_ticker and ticker_map and raw_ticker in ticker_map:
        mapped = ticker_map[raw_ticker]
        return {"ticker": raw_ticker, "name": mapped.get("name", row.get("name", "")), "sector": normalize_sector((sector_map or {}).get(raw_ticker, "") or TICKER_SECTOR_MAP.get(raw_ticker, "") or infer_sector_from_name(mapped.get("name", "")) or row.get("sector") or "未分类")}
    inferred = infer_from_issuer(row.get("name", ""))
    if inferred:
        return inferred
    return {"ticker": clean_ticker(row.get("symbol", "")), "name": normalize_issuer(row.get("name", "")) or row.get("name", ""), "sector": normalize_sector(row.get("sector") or "未分类")}


def frontend_fields(row: dict[str, Any]) -> dict[str, Any]:
    display_symbol = row.get("ticker") or row.get("symbol") or row.get("cusip") or ""
    asset_type = row.get("asset_type") or row.get("security_type") or "SHARE"
    security_type = row.get("security_type", "")
    return {
        "display_symbol": display_symbol,
        "display_name": row.get("name") or display_symbol,
        "asset_type": asset_type,
        "security_type": security_type,
        "is_option": asset_type in {"PUT", "CALL"},
        "badge": asset_type if asset_type in {"PUT", "CALL"} else (security_type if security_type not in {"", "Common Stock"} else ""),
    }


def standardize_row(row: dict[str, Any], external_map: dict[str, dict[str, Any]] | None = None, issuer_map: dict[str, dict[str, str]] | None = None, sector_map: dict[str, str] | None = None, ticker_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    result = dict(row)
    shares = float(result.get("shares") or 0)
    value = normalize_value_units(float(result.get("value") or 0), shares)
    result["value"] = round(value, 2)
    result["price"] = round(value / shares, 4) if shares else float(result.get("price") or 0)
    result["cusip"] = (result.get("cusip") or "").upper().strip()
    result["asset_type"] = detect_option_type(result)
    mapped = map_security(result, external_map, issuer_map, sector_map, ticker_map)
    ticker = clean_ticker(mapped.get("ticker") or result.get("ticker") or "")
    result["ticker"] = ticker
    if mapped.get("security_type"):
        result["security_type"] = mapped.get("security_type")
    result["symbol"] = ticker or result.get("symbol") or result.get("cusip") or result.get("name", "")
    result["name"] = mapped.get("name") or normalize_issuer(result.get("name", ""))
    result["sector"] = normalize_sector(mapped.get("sector") or (sector_map or {}).get(ticker, "") or TICKER_SECTOR_MAP.get(ticker, "") or infer_sector_from_name(result.get("name", "")) or result.get("sector") or "未分类")
    result.update(frontend_fields(result))
    return result


def aggregate_holdings(rows: list[dict[str, Any]], external_map: dict[str, dict[str, Any]] | None = None, issuer_map: dict[str, dict[str, str]] | None = None, sector_map: dict[str, str] | None = None, ticker_map: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for raw in rows:
        row = standardize_row(raw, external_map, issuer_map, sector_map, ticker_map)
        key = row.get("ticker") or row.get("cusip") or row.get("symbol") or row.get("name")
        key = f"{key}:{row.get('asset_type', 'SHARE')}"
        if key not in grouped:
            grouped[key] = dict(row)
            grouped[key]["cusips"] = [row.get("cusip")] if row.get("cusip") else []
            grouped[key]["_max_value"] = float(row.get("value") or 0)
            continue
        current = grouped[key]
        row_value = float(row.get("value") or 0)
        current["shares"] = float(current.get("shares") or 0) + float(row.get("shares") or 0)
        current["value"] = float(current.get("value") or 0) + row_value
        current["change_shares"] = float(current.get("change_shares") or 0) + float(row.get("change_shares") or 0)
        current["change_value"] = float(current.get("change_value") or 0) + float(row.get("change_value") or 0)
        if row.get("cusip") and row.get("cusip") not in current["cusips"]:
            current["cusips"].append(row.get("cusip"))
        if row_value > float(current.get("_max_value") or 0):
            current["_max_value"] = row_value
            for field in ("name", "sector", "ticker", "symbol", "display_symbol", "display_name", "security_type", "badge"):
                current[field] = row.get(field) or current.get(field)
    for row in grouped.values():
        shares = float(row.get("shares") or 0)
        value = float(row.get("value") or 0)
        row["price"] = round(value / shares, 4) if shares else 0
        row["value"] = round(value, 2)
        row.pop("_max_value", None)
        row.update(frontend_fields(row))
    return list(grouped.values())


def compare_with_history(rows: list[dict[str, Any]], previous: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    for row in rows:
        prev = previous.get(row.get("ticker", "")) or previous.get(row.get("cusip", "")) or previous.get(row.get("symbol", ""))
        if prev:
            row["change_shares"] = float(row.get("shares") or 0) - float(prev.get("shares") or 0)
            row["change_value"] = float(row.get("value") or 0) - normalize_value_units(float(prev.get("value") or 0), float(prev.get("shares") or 0))
        else:
            row.setdefault("change_shares", 0)
            row.setdefault("change_value", 0)
    return rows


def normalize_holdings(rows: list[dict[str, Any]], previous: dict[str, dict[str, Any]] | None = None, external_map: dict[str, dict[str, Any]] | None = None, issuer_map: dict[str, dict[str, str]] | None = None, sector_map: dict[str, str] | None = None, ticker_map: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    standardized = [standardize_row(row, external_map, issuer_map, sector_map, ticker_map) for row in rows]
    compared = compare_with_history(standardized, previous or {})
    return aggregate_holdings(compared, external_map, issuer_map, sector_map, ticker_map)
