import json
import time
from pathlib import Path
from typing import Any

from backend.config import DATA_DIR

DISCOVERY_CACHE = DATA_DIR / "exchange_stocks.json"
DISCOVERY_TTL = 86400  # 24h


def _cached_discovery() -> dict | None:
    if not DISCOVERY_CACHE.exists():
        return None
    try:
        data = json.loads(DISCOVERY_CACHE.read_text(encoding="utf-8"))
        if time.time() - data.get("_ts", 0) < DISCOVERY_TTL:
            return data
    except Exception:
        pass
    return None


def _save_discovery(data: dict) -> None:
    data["_ts"] = time.time()
    DISCOVERY_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# --- Bundled stock lists (fallback if Wikipedia unreachable) ---
def _bundled_sp500() -> list[str]:
    return [
        "AAPL","MSFT","GOOGL","AMZN","NVDA","META","BRK-B","TSLA","JPM","V",
        "UNH","JNJ","WMT","MA","PG","HD","CVX","XOM","LLY","ABBV",
        "BAC","PFE","KO","PEP","MRK","TMO","COST","AVGO","CSCO","ACN",
        "ABT","DHR","CMCSA","NFLX","VZ","WFC","MCD","DIS","INTC","CRM",
        "TXN","NKE","AMD","QCOM","T","PM","LOW","BMY","AMGN","UPS",
        "CAT","GS","RTX","INTU","IBM","GE","SPGI","UNP","MS","SCHW",
        "HON","NEE","DE","BLK","LMT","SYK","ADBE","MDT","AMAT","NOW",
        "PLD","AXP","ISRG","C","ADI","GILD","TJX","ELV","VRTX","CI",
        "COP","BKNG","FIS","ZTS","CB","MMC","LRCX","MU","ETN","MO",
        "PGR","BSX","ICE","DUK","SO","EOG","EQIX","AON","USB","BDX",
        "CME","TMUS","CL","ITW","PH","PNC","HUM","KLAC","WM","SHW",
        "REGN","GD","APD","CSX","FDX","EMR","PSA","ROP","MCO","MPC",
        "MMM","ORLY","EW","TGT","AEP","CTAS","NOC","MCK","AZO","TRV",
        "FCX","TT","ECL","PSX","AFL","SRE","HLT","EXC","MAR","MSI",
        "D","ADSK","NSC","CARR","F","JCI","LHX","PEG","SPG","OXY",
        "GIS","KMB","AIG","KMI","HCA","DLR","MET","ALL","OTIS","FISV",
    ]


def _bundled_nasdaq100() -> list[str]:
    return [
        "AAPL","MSFT","AMZN","GOOGL","NVDA","META","AVGO","TSLA","COST","NFLX",
        "ADBE","PEP","AMD","CSCO","TMUS","INTC","QCOM","TXN","AMAT","INTU",
        "HON","CMCSA","ADP","SBUX","GILD","VRTX","MELI","LRCX","MU","ADI",
        "LULU","PYPL","BKNG","REGN","MDLZ","KDP","MRVL","SNPS","ASML","CDNS",
        "KLAC","CRWD","MNST","FTNT","WDAY","CPRT","ABNB","ZS","TEAM","CTSH",
        "ODFL","PDD","CTAS","IDXX","PANW","CHTR","ORLY","PAYX","ADSK","FANG",
        "ROST","BKR","FAST","XEL","CEG","DXCM","BIIB","KHC","PCAR","MCHP",
        "CSGP","AZN","EA","WBD","EXC","ILMN","JD","LCID","GFS","MRNA",
    ]


def _bundled_csi300() -> list[str]:
    return [
        "600519.SS","000858.SZ","601318.SS","600036.SS","000333.SZ","601166.SS",
        "600900.SS","600887.SS","002415.SZ","601398.SS","600276.SS","601939.SS",
        "002714.SZ","300750.SZ","600030.SS","601668.SS","601288.SS","000001.SZ",
        "002304.SZ","601012.SS","600809.SS","603259.SS","600031.SS","000725.SZ",
        "601899.SS","600585.SS","601088.SS","600048.SS","000651.SZ","002142.SZ",
        "601211.SS","000568.SZ","002475.SZ","600309.SS","300760.SZ","601985.SS",
        "600028.SS","600104.SS","000063.SZ","600050.SS","601857.SS","000002.SZ",
        "300059.SZ","601688.SS","601628.SS","600690.SS","000776.SZ","002371.SZ",
    ]


def _bundled_hsi() -> list[str]:
    return [
        "0005.HK","0011.HK","0016.HK","0027.HK","0066.HK","0101.HK","0168.HK",
        "0175.HK","0267.HK","0288.HK","0386.HK","0388.HK","0669.HK","0688.HK",
        "0700.HK","0762.HK","0823.HK","0857.HK","0883.HK","0939.HK","0941.HK",
        "0960.HK","0992.HK","1038.HK","1044.HK","1088.HK","1109.HK","1113.HK",
        "1211.HK","1299.HK","1398.HK","1810.HK","1876.HK","1918.HK","1929.HK",
        "1997.HK","2007.HK","2015.HK","2020.HK","2269.HK","2313.HK","2318.HK",
        "2319.HK","2331.HK","2382.HK","2388.HK","2628.HK","2688.HK","2911.HK",
        "3690.HK","3968.HK","3988.HK","6160.HK","6618.HK","6690.HK","6862.HK",
        "9618.HK","9888.HK","9988.HK","9999.HK",
    ]


def _bundled_nikkei() -> list[str]:
    return [
        "7203.T","6758.T","9984.T","6501.T","6367.T","9432.T","7974.T",
        "8035.T","6861.T","6954.T","4063.T","7735.T","8306.T","6098.T",
        "4568.T","4519.T","7741.T","8801.T","8058.T","4502.T","7267.T",
        "9433.T","8316.T","8001.T","6981.T","3382.T","6301.T","9022.T",
        "8766.T","6273.T","4661.T","6702.T","4543.T","8411.T","5108.T",
        "6902.T","4452.T","6506.T","6723.T","7751.T","4901.T","9843.T",
        "6178.T","6971.T","6901.T","7270.T","2914.T","9613.T","4503.T",
        "6752.T","4005.T","2502.T","8604.T","7259.T","6903.T","9962.T",
    ]


def _fetch_wikipedia_table(url: str, col_idx: int = 0) -> list[str]:
    try:
        import pandas as pd
        tables = pd.read_html(url)
        if tables:
            df = tables[0]
            return [str(s).strip().replace('.', '-') for s in df.iloc[:, col_idx].tolist() if str(s).strip()]
    except Exception:
        pass
    return []


def discover_all_stocks() -> dict[str, list[str]]:
    cached = _cached_discovery()
    if cached:
        return {k: v for k, v in cached.items() if k != "_ts"}

    result: dict[str, list[str]] = {}

    # US - try Wikipedia, fallback to bundled
    sp500 = _fetch_wikipedia_table(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0
    )
    if not sp500:
        sp500 = _bundled_sp500()
    nasdaq100 = _bundled_nasdaq100()  # Always use bundled (fast)
    us_stocks = list(dict.fromkeys(sp500 + nasdaq100))
    result["美股"] = us_stocks

    result["A股"] = _bundled_csi300()
    result["港股"] = _bundled_hsi()
    result["日股"] = _bundled_nikkei()

    _save_discovery(result)
    return result
