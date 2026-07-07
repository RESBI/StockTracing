"""Pydantic request models for input validation."""
from typing import Literal
from pydantic import BaseModel, Field


class TradeCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=20)
    direction: Literal["long", "short"] = "long"
    open_date: str = ""
    open_price: float = Field(..., gt=0)
    close_date: str | None = None
    close_price: float | None = None
    quantity: float = Field(..., gt=0)
    notes: str = ""


class TradeUpdate(BaseModel):
    symbol: str | None = Field(None, min_length=1, max_length=20)
    direction: Literal["long", "short"] | None = None
    open_date: str | None = None
    open_price: float | None = Field(None, gt=0)
    close_date: str | None = None
    close_price: float | None = Field(None, gt=0)
    quantity: float | None = Field(None, gt=0)
    notes: str | None = None


class ConfigUpdate(BaseModel):
    llm: dict | None = None
    proxy: dict | None = None
    sec: dict | None = None


class TicksRequest(BaseModel):
    symbols: list[str] = Field(..., max_length=100)
