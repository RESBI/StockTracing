import io
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


def _fetch_wikipedia(url: str, table_idx: int = 0, col_idx: int = 0) -> list[str]:
    try:
        import requests
        import pandas as pd
        resp = requests.get(url, timeout=20, headers={"User-Agent": "StockTracing/1.0"})
        resp.raise_for_status()
        tables = pd.read_html(io.StringIO(resp.text))
        if tables and table_idx < len(tables):
            df = tables[table_idx]
            col = df.iloc[:, col_idx].dropna().tolist()
            return [str(s).strip() for s in col if str(s).strip()]
    except Exception:
        pass
    return []


def _fetch_yahoo_index(symbols: list[str]) -> list[str]:
    """Try to get index components via yfinance."""
    try:
        import yfinance as yf
        results = []
        for sym in symbols:
            try:
                t = yf.Ticker(sym)
                holdings = getattr(t, 'holdings', None)
                if holdings is not None and hasattr(holdings, 'symbol'):
                    results.extend(holdings.symbol.tolist())
            except Exception:
                pass
        return results
    except Exception:
        return []


def _fetch_bing_search(query: str, max_results: int = 20) -> list[str]:
    """Use Bing search to find stock lists, fallback to duckduckgo."""
    try:
        from duckduckgo_search import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, region="us-en", safesearch="off", max_results=max_results):
                results.append(r.get("body", ""))
        return results
    except Exception:
        return []


# === Comprehensive bundled fallback lists ===

def _bundled_sp500() -> list[str]:
    return [
        "AAPL","MSFT","GOOGL","AMZN","NVDA","META","BRK-B","TSLA","JPM","V",
        "UNH","JNJ","WMT","MA","PG","HD","CVX","XOM","LLY","ABBV","BAC","PFE","KO",
        "PEP","MRK","TMO","COST","AVGO","CSCO","ACN","ABT","DHR","CMCSA","NFLX",
        "VZ","WFC","MCD","DIS","INTC","CRM","TXN","NKE","AMD","QCOM","T","PM",
        "LOW","BMY","AMGN","UPS","CAT","GS","RTX","INTU","IBM","GE","SPGI","UNP",
        "MS","SCHW","HON","NEE","DE","BLK","LMT","SYK","ADBE","MDT","AMAT","NOW",
        "PLD","AXP","ISRG","C","ADI","GILD","TJX","ELV","VRTX","CI","COP","BKNG",
        "ZTS","CB","MMC","LRCX","MU","ETN","MO","PGR","BSX","ICE","DUK","SO","EOG",
        "EQIX","AON","USB","BDX","CME","TMUS","CL","ITW","PH","PNC","HUM","KLAC",
        "WM","SHW","REGN","GD","APD","CSX","FDX","EMR","PSA","ROP","MCO","MPC",
        "MMM","ORLY","EW","TGT","AEP","CTAS","NOC","MCK","AZO","TRV","FCX","TT",
        "ECL","PSX","AFL","SRE","HLT","EXC","MAR","MSI","D","ADSK","NSC","CARR",
        "F","JCI","LHX","PEG","SPG","OXY","GIS","KMB","AIG","KMI","HCA","DLR","MET",
        "ALL","OTIS","FISV","FTNT","ROST","PAYX","COR","CCI","KMB","KVUE","MNST",
        "WMB","RSG","AME","CPRT","MSCI","TEL","PRU","EFX","BKR","YUM","SYY","ED",
        "FAST","A","DAL","KR","CTSH","RCL","PCAR","VLO","WBD","DD","HES","DOW",
        "NEM","VICI","HAL","GEV","ACGL","TRGP","HSY","EXR","DFS","XEL","CBRE",
        "BIIB","CNC","GLW","HPQ","EBAY","MLM","LULU","EXPD","STZ","WAB","MTD",
        "IR","RJF","NDAQ","IDXX","WELL","PPL","AWK","ANSS","GRMN","VMC","ETR",
        "TROW","ARE","DTE","EIX","FITB","WY","FE","TTWO","DOV","HPE","HBAN","LYB",
        "HUBB","NTRS","MKC","WRB","CINF","TSCO","CTRA","IFF","SW","ULTA","WST",
        "PKG","DGX","CDW","ZBRA","J","TFX","NDSN","CHD","MOH","PFG","DG","LUV",
        "SNA","SYF","LKQ","KMX","CF","HRL","BBY","DPZ","ROL","JBHT","AKAM","VRSN",
        "BRO","PNR","OC","MAS","IP","AOS","GPC","LW","CPT","POOL","TXT","AES",
        "GEN","NI","BG","FOXA","PARA","BXP","FRT","IVZ","BEN","WAT","MGM","ETSY",
        "APA","MTCH","BWA","NWSA","QRVO","HST","MOS","CZR","GL","GNRC","TAP",
        "NRG","PNW","DVA","FMC","BIO","HSIC","AAL","ALLE","RL","INCY","FOX",
        "UHS","XRAY","REG","UDR","FFIV","L","WDC","DXC","JBL","NWL","IPG","TPR",
        "HAS","EMN","AIZ","SEE","WHR",
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
        "NXPI","DDOG","TTD","ANSS","VRSK","CDW","GEHC","MDB","MAR","DASH",
        "SPLK","ZS","ON","TTWO","WDC","ULTA","OKTA","ZS","ZM","DOCU",
        "EBAY","VRSN","FOXA","FOX","SIRI","HST","UAL","AAL","LUV","DAL",
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
        "600016.SS","000338.SZ","600406.SS","002594.SZ","601088.SS","600025.SS",
        "601766.SS","603288.SS","600745.SS","000100.SZ","002050.SZ","601727.SS",
        "600019.SS","600150.SS","601800.SS","002230.SZ","600893.SS","000625.SZ",
        "601919.SS","600570.SS","002129.SZ","601788.SS","600196.SS","000792.SZ",
        "601225.SS","000538.SZ","601877.SS","002236.SZ","600660.SS","002459.SZ",
        "601816.SS","600886.SS","000408.SZ","300014.SZ","002271.SZ","600115.SS",
        "000786.SZ","600176.SS","300124.SZ","601238.SS","600362.SS","002475.SZ",
        "000301.SZ","000876.SZ","601799.SS","002241.SZ","300033.SZ","002601.SZ",
        "601111.SS","600029.SS","601006.SS","000723.SZ","600795.SS","601618.SS",
        "000661.SZ","002157.SZ","600346.SS","300015.SZ","000963.SZ","603501.SS",
        "688981.SS","688111.SS","688012.SS","688036.SS","688036.SS","688169.SS",
        "688256.SS","688008.SS","688396.SS","688561.SS","601138.SS","300274.SZ",
        "300316.SZ","300316.SZ","002920.SZ","300433.SZ","300502.SZ","300394.SZ",
        "603160.SS","603986.SS","600703.SS","600588.SS","600522.SS","000977.SZ",
        "002049.SZ","603019.SS","600845.SS","300782.SZ","300308.SZ","688188.SS",
        "002916.SZ","300413.SZ","002709.SZ","300450.SZ","600183.SS","601698.SS",
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
        "9618.HK","9888.HK","9988.HK","9999.HK","0001.HK","0002.HK","0003.HK",
        "0006.HK","0012.HK","0083.HK","0144.HK","0268.HK","0293.HK","0316.HK",
        "0322.HK","0493.HK","0788.HK","0868.HK","0881.HK","0968.HK","0981.HK",
        "1099.HK","1177.HK","1378.HK","1801.HK","1833.HK","2018.HK","2319.HK",
        "2382.HK","2689.HK","2883.HK","2899.HK","3320.HK","3888.HK","6185.HK",
        "6969.HK","9633.HK","9992.HK",
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
        "6504.T","5803.T","6594.T","4188.T","6645.T","6201.T","9020.T",
        "4507.T","4523.T","9735.T","7974.T","1925.T","5802.T","6326.T",
        "6479.T","4021.T","7752.T","5332.T","5401.T","6701.T","6146.T",
        "4911.T","6762.T","6976.T","4528.T","1802.T","6767.T","8015.T",
        "9502.T","5020.T","8591.T","3407.T","7733.T","6703.T","9101.T",
        "9021.T","4569.T","5801.T","7186.T","8031.T","8309.T","8410.T",
        "8304.T","8439.T","8253.T","7182.T","9202.T","6472.T","1801.T",
        "9503.T","9531.T","9301.T","2875.T","3402.T","5406.T","4755.T",
        "4612.T","8331.T","9107.T","4203.T","6794.T","6856.T","8354.T",
        "3003.T","1605.T","9064.T","4506.T","4527.T","8750.T","6305.T",
        "1928.T","9201.T","7453.T","7936.T","3382.T","4183.T","4182.T",
        "9434.T","9739.T","2587.T","6503.T","7769.T","7912.T","8697.T",
        "7261.T","5101.T","6471.T","8053.T","7011.T","7832.T","9602.T",
        "6971.T","6841.T","6506.T","7731.T","7013.T","6448.T","6361.T",
        "3769.T","6370.T","7921.T","4751.T","4773.T","6440.T","6134.T",
    ]


def discover_all_stocks(force_refresh: bool = False) -> dict[str, list[str]]:
    if not force_refresh:
        cached = _cached_discovery()
        if cached:
            return {k: v for k, v in cached.items() if k != "_ts"}

    result: dict[str, list[str]] = {}

    # === US: multi-source merge ===
    us_stocks = []
    # Wikipedia S&P 500
    sp500_wiki = _fetch_wikipedia("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", 0, 0)
    if sp500_wiki and len(sp500_wiki) > 300:
        sp500_wiki = [s.replace('.', '-').replace(' ', '') for s in sp500_wiki if s and not s.startswith('Symbol')]
        us_stocks.extend(sp500_wiki)
    # Wikipedia NASDAQ 100
    ndx_wiki = _fetch_wikipedia("https://en.wikipedia.org/wiki/Nasdaq-100", 0, 1)
    if ndx_wiki and len(ndx_wiki) > 50:
        us_stocks.extend([s.replace(' ', '') for s in ndx_wiki if s])
    # Wikipedia Russell 1000
    russell = _fetch_wikipedia("https://en.wikipedia.org/wiki/Russell_1000_Index", 0, 0)
    if russell and len(russell) > 100:
        us_stocks.extend([s.replace('.', '-').replace(' ', '') for s in russell if s])
    # Fallback
    if len(us_stocks) < 100:
        us_stocks = _bundled_sp500() + _bundled_nasdaq100()
    result["美股"] = list(dict.fromkeys(us_stocks))

    # === CN: multi-source ===
    cn_stocks = []
    csi300 = _fetch_wikipedia("https://en.wikipedia.org/wiki/CSI_300_Index", 1, 1)
    if csi300 and len(csi300) > 100:
        for s in csi300:
            s = s.strip()
            if s.endswith('.SS') or s.endswith('.SZ'):
                cn_stocks.append(s)
            elif s.isdigit() and len(s) == 6:
                cn_stocks.append(s + ('.SS' if s.startswith(('6', '9')) else '.SZ'))
    # CSI 500
    csi500 = _fetch_wikipedia("https://en.wikipedia.org/wiki/CSI_500_Index", 1, 1)
    if csi500 and len(csi500) > 100:
        for s in csi500:
            s = s.strip()
            if s.endswith('.SS') or s.endswith('.SZ'):
                cn_stocks.append(s)
            elif s.isdigit() and len(s) == 6:
                cn_stocks.append(s + ('.SS' if s.startswith(('6', '9')) else '.SZ'))
    if len(cn_stocks) < 50:
        cn_stocks = _bundled_csi300()
    result["A股"] = list(dict.fromkeys(cn_stocks))

    # === HK: multi-source ===
    hk_stocks = []
    hsi = _fetch_wikipedia("https://en.wikipedia.org/wiki/Hang_Seng_Index", 0, 2)
    if hsi and len(hsi) > 30:
        for s in hsi:
            s = s.strip()
            if s.endswith('.HK'):
                hk_stocks.append(s)
            elif s.isdigit() and len(s) <= 5:
                hk_stocks.append(s.zfill(4) + '.HK')
    # HSCEI (H-shares)
    hscei = _fetch_wikipedia("https://en.wikipedia.org/wiki/Hang_Seng_China_Enterprises_Index", 0, 1)
    if hscei and len(hscei) > 20:
        for s in hscei:
            s = s.strip()
            if s.endswith('.HK'):
                hk_stocks.append(s)
            elif s.isdigit() and len(s) <= 5:
                hk_stocks.append(s.zfill(4) + '.HK')
    if len(hk_stocks) < 30:
        hk_stocks = _bundled_hsi()
    result["港股"] = list(dict.fromkeys(hk_stocks))

    # === JP: multi-source ===
    jp_stocks = []
    nikkei = _fetch_wikipedia("https://en.wikipedia.org/wiki/Nikkei_225", 0, 1)
    if nikkei and len(nikkei) > 100:
        for s in nikkei:
            s = s.strip()
            if s.endswith('.T'):
                jp_stocks.append(s)
            elif s.isdigit():
                jp_stocks.append(s + '.T')
    # TOPIX 100
    topix = _fetch_wikipedia("https://en.wikipedia.org/wiki/TOPIX", 0, 1)
    if topix and len(topix) > 50:
        for s in topix:
            s = s.strip()
            if s.endswith('.T'):
                jp_stocks.append(s)
            elif s.isdigit():
                jp_stocks.append(s + '.T')
    if len(jp_stocks) < 50:
        jp_stocks = _bundled_nikkei()
    result["日股"] = list(dict.fromkeys(jp_stocks))

    _save_discovery(result)
    return result
