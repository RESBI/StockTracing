import json
import os
import time
import random
from pathlib import Path
from functools import wraps

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT_CONFIG = {
    "llm": {
        "api_key": "",
        "model": "gpt-4o-mini",
        "base_url": "https://api.openai.com/v1",
    },
    "proxy": {
        "enabled": False,
        "http": "",
        "https": "",
    },
}


def _load_json_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=4), encoding="utf-8")
        return DEFAULT_CONFIG
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return DEFAULT_CONFIG


def save_json_config(data: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8")


def get_llm_config() -> dict:
    cfg = _load_json_config().get("llm", {})
    # Environment variables override config.json (container-friendly)
    if os.environ.get("ST_LLM_API_KEY"):
        cfg["api_key"] = os.environ["ST_LLM_API_KEY"]
    if os.environ.get("ST_LLM_MODEL"):
        cfg["model"] = os.environ["ST_LLM_MODEL"]
    if os.environ.get("ST_LLM_BASE_URL"):
        cfg["base_url"] = os.environ["ST_LLM_BASE_URL"]
    return cfg


def get_llm_enabled() -> bool:
    return bool(get_llm_config().get("api_key", ""))


def get_proxy_config() -> dict:
    cfg = _load_json_config().get("proxy", {"enabled": False, "http": "", "https": ""})
    # Environment variables override
    if os.environ.get("ST_PROXY_ENABLED"):
        cfg["enabled"] = os.environ["ST_PROXY_ENABLED"] in ("1", "true", "True")
    if os.environ.get("ST_PROXY_HTTP"):
        cfg["http"] = os.environ["ST_PROXY_HTTP"]
    if os.environ.get("ST_PROXY_HTTPS"):
        cfg["https"] = os.environ["ST_PROXY_HTTPS"]
    return cfg


SEC_USER_AGENT_DEFAULT = "StockTracing/1.0 contact@example.com"


def get_sec_user_agent() -> str:
    """SEC EDGAR requires a real contact User-Agent. Configurable via config.json sec.user_agent or ST_SEC_UA env."""
    if os.environ.get("ST_SEC_UA"):
        return os.environ["ST_SEC_UA"]
    cfg = _load_json_config()
    return cfg.get("sec", {}).get("user_agent", "") or SEC_USER_AGENT_DEFAULT


def get_proxy_dict() -> dict[str, str] | None:
    pc = get_proxy_config()
    if not pc.get("enabled"):
        return None
    proxies = {}
    if pc.get("http"):
        proxies["http"] = pc["http"]
    if pc.get("https"):
        proxies["https"] = pc["https"]
    elif pc.get("http"):
        proxies["https"] = pc["http"]
    return proxies if proxies else None

DATABASE_URL = f"sqlite:///{DATA_DIR / 'stocktracing.db'}"


class TTL:
    """Centralized cache TTLs (seconds)."""
    STOCK_INFO = 3600          # stock_cache 基础行情
    HISTORY = 600              # K 线 history_{period}_{interval}
    INDICATORS = 600           # 技术指标 full_indicators
    ANALYST_RATINGS = 3600     # 机构评级 analyst_ratings
    NEWS = 7200                # 资讯缓存
    DISCOVERY = 86400          # 候选集 exchange_stocks.json
    INSTITUTIONS = 8 * 3600    # 机构持仓 SEC 13F
    MAPPING = 30 * 86400       # CUSIP/ticker/sector 映射
    TICK_INFO = 15             # 进程内 tick 价格缓存


# Backward-compatible aliases
CACHE_TTL_SECONDS = TTL.STOCK_INFO
NEWS_CACHE_TTL = TTL.NEWS

# Background cache updater interval (seconds). Tick cache absorbs high-frequency polls.
CACHE_UPDATE_INTERVAL = 15

# Debug mode (exposes exception details in 500 responses). Set ST_DEBUG=1 to enable.
DEBUG = os.environ.get("ST_DEBUG", "0") == "1"

WATCHLIST_FILE = DATA_DIR / "watchlist.json"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


def _is_retryable(exc: Exception) -> bool:
    """Whether an exception represents a transient/rate-limit error worth retrying."""
    msg = str(exc).lower()
    if any(k in msg for k in ("rate limit", "too many requests", "429", "503", "502", "504", "server overloaded", "temporarily unavailable")):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    type_name = type(exc).__name__.lower()
    if "timeout" in type_name or "connection" in type_name:
        return True
    return False


def retry_on_rate_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                if not _is_retryable(e):
                    raise
                delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                time.sleep(delay)
                continue
        raise last_exc
    return wrapper


INDICATOR_PARAMS = {
    "sma": {"short": 20, "long": 50, "signal": 200},
    "ema": {"fast": 12, "slow": 26, "signal": 9},
    "rsi": {"period": 14, "overbought": 70, "oversold": 30},
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bollinger": {"period": 20, "std": 2},
    "atr": {"period": 14},
    "obv": {},
    "stochastic": {"k": 14, "d": 3, "overbought": 80, "oversold": 20},
}
