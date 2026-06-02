import os
from backend.config import get_proxy_dict


def setup_proxy() -> None:
    proxies = get_proxy_dict()
    if not proxies:
        return

    os.environ["HTTP_PROXY"] = proxies.get("http", "")
    os.environ["HTTPS_PROXY"] = proxies.get("https", proxies.get("http", ""))

    try:
        import yfinance as yf
        import requests
        session = requests.Session()
        session.proxies.update(proxies)
        yf.shared._SESSION = session
    except Exception:
        pass

    try:
        import yfinance.data
        yf_data = yfinance.data
        if hasattr(yf_data, '_requests'):
            yf_data._requests.get = _make_proxied_get(proxies)
    except Exception:
        pass


def _make_proxied_get(proxies: dict):
    import requests
    sess = requests.Session()
    sess.proxies.update(proxies)
    def proxied_get(url, **kwargs):
        return sess.get(url, **kwargs)
    return proxied_get
