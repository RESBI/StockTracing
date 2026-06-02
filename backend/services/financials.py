from datetime import datetime, timezone
from typing import Any

import yfinance as yf
from sqlalchemy.orm import Session

from backend.database.models import FinancialCache, SessionLocal


def _parse_financials(ticker: yf.Ticker) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {
        "income_statement": [],
        "balance_sheet": [],
        "cash_flow": [],
        "quarterly_income": [],
        "quarterly_balance": [],
        "quarterly_cashflow": [],
    }

    def _df_to_list(df, label: str):
        if df is None or df.empty:
            return
        for col in df.columns:
            entry = {"period": str(col)}
            for idx, val in df[col].items():
                entry[idx] = float(val) if val is not None and not isinstance(val, str) else val
            result[label].append(entry)

    try:
        _df_to_list(ticker.financials, "income_statement")
    except Exception:
        pass
    try:
        _df_to_list(ticker.balance_sheet, "balance_sheet")
    except Exception:
        pass
    try:
        _df_to_list(ticker.cashflow, "cash_flow")
    except Exception:
        pass
    try:
        _df_to_list(ticker.quarterly_financials, "quarterly_income")
    except Exception:
        pass
    try:
        _df_to_list(ticker.quarterly_balance_sheet, "quarterly_balance")
    except Exception:
        pass
    try:
        _df_to_list(ticker.quarterly_cashflow, "quarterly_cashflow")
    except Exception:
        pass

    return result


def save_financials(symbol: str) -> None:
    sym = symbol.upper().strip()
    ticker = yf.Ticker(sym)
    data = _parse_financials(ticker)
    db: Session = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        for report_type, items in data.items():
            if not items:
                continue
            db.query(FinancialCache).filter(
                FinancialCache.symbol == sym,
                FinancialCache.report_type == report_type,
            ).delete()
            for item in items:
                fiscal_year = None
                period_str = item.get("period", "")
                try:
                    if "-" in str(period_str):
                        fiscal_year = int(str(period_str).split("-")[0])
                except ValueError:
                    pass
                db.add(FinancialCache(
                    symbol=sym,
                    report_type=report_type,
                    fiscal_year=fiscal_year or 0,
                    data=item,
                    updated_at=now,
                ))
        db.commit()
    finally:
        db.close()


def get_financials(symbol: str, force_refresh: bool = False) -> dict[str, Any]:
    sym = symbol.upper().strip()
    db: Session = SessionLocal()
    try:
        existing = db.query(FinancialCache).filter(FinancialCache.symbol == sym).first()
        if not existing or force_refresh:
            db.close()
            save_financials(sym)
            db = SessionLocal()
            existing = db.query(FinancialCache).filter(FinancialCache.symbol == sym).first()

        result = {
            "income_statement": [],
            "balance_sheet": [],
            "cash_flow": [],
            "quarterly_income": [],
            "quarterly_balance": [],
            "quarterly_cashflow": [],
        }
        records = db.query(FinancialCache).filter(FinancialCache.symbol == sym).all()
        for r in records:
            if r.report_type in result:
                result[r.report_type].append(r.data)
        return result
    finally:
        db.close()
