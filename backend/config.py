import json
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
    cfg = _load_json_config()
    return cfg.get("llm", {})


def get_llm_enabled() -> bool:
    return bool(get_llm_config().get("api_key", ""))


def get_proxy_config() -> dict:
    cfg = _load_json_config()
    return cfg.get("proxy", {"enabled": False, "http": "", "https": ""})


def get_proxy_dict() -> dict[str, str] | None:
    pc = get_proxy_config()
    if not pc.get("enabled"):
        return None
    proxies = {}
    if pc.get("http"):
        proxies["http"] = pc["http"]
    if pc.get("https"):
        proxies["https"] = pc["https"]
    return proxies if proxies else None

DATABASE_URL = f"sqlite:///{DATA_DIR / 'stocktracing.db'}"

CACHE_TTL_SECONDS = 3600
NEWS_CACHE_TTL = 7200

WATCHLIST_FILE = DATA_DIR / "watchlist.json"

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2


def retry_on_rate_limit(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(MAX_RETRIES):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                last_exc = e
                msg = str(e).lower()
                if "rate limit" in msg or "too many requests" in msg:
                    delay = RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                    continue
                raise
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
