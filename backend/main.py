import json
import math
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, Response
from pathlib import Path
from typing import Any

from backend.routers import stock, pages
from backend.database.models import Base, engine
from backend.utils.proxy import setup_proxy
from backend.services.cache_updater import get_updater

Base.metadata.create_all(bind=engine)
setup_proxy()
get_updater().start()


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    return obj


class SafeJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        return json.dumps(
            _sanitize(content),
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
        ).encode("utf-8")


app = FastAPI(title="StockTracing", description="股票追踪分析系统", version="1.0.0",
              default_response_class=SafeJSONResponse)

frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(frontend_dir / "static")), name="static")

app.include_router(stock.router)
app.include_router(pages.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return SafeJSONResponse(
        status_code=500,
        content={"detail": str(exc)},
    )
