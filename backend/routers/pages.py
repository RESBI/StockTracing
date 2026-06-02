from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from backend.config import get_llm_enabled

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="frontend/templates")


@router.get("/", response_class=HTMLResponse)
def page_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "config": {"LLM_ENABLED": get_llm_enabled()}})


@router.get("/stock/{symbol}", response_class=HTMLResponse)
def page_stock_detail(request: Request, symbol: str):
    return templates.TemplateResponse("stock_detail.html", {"request": request, "symbol": symbol.upper(), "config": {"LLM_ENABLED": get_llm_enabled()}})


@router.get("/scan", response_class=HTMLResponse)
def page_scan(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request, "config": {"LLM_ENABLED": get_llm_enabled()}})


@router.get("/hunt", response_class=HTMLResponse)
def page_hunt(request: Request):
    return templates.TemplateResponse("hunt.html", {"request": request, "config": {"LLM_ENABLED": get_llm_enabled()}})


@router.get("/trades", response_class=HTMLResponse)
def page_trades(request: Request):
    return templates.TemplateResponse("trades.html", {"request": request, "config": {"LLM_ENABLED": get_llm_enabled()}})
