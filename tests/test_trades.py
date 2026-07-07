"""Tests for backend.services.trades P&L computation."""
import json

from backend.services import trades as T
from backend.database.models import StockCache


def _write_trades(tmp_path, trades):
    (tmp_path / "trades.json").write_text(json.dumps(trades), encoding="utf-8")


def test_create_trade_assigns_id(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    t = T.create_trade({"symbol": "AAPL", "open_price": 100, "quantity": 10, "direction": "long"})
    assert "id" in t and len(t["id"]) == 12
    assert t["status"] == "open"
    assert t["symbol"] == "AAPL"


def test_create_closed_trade_status(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    t = T.create_trade({"symbol": "AAPL", "open_price": 100, "close_price": 110, "quantity": 10})
    assert t["status"] == "closed"


def test_long_pnl_calculation(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    _write_trades(tmp_path, [{
        "id": "1", "symbol": "AAPL", "direction": "long",
        "open_price": 100, "close_price": 120, "quantity": 10, "status": "closed",
        "open_date": "2024-01-01", "close_date": "2024-02-01",
    }])
    stats = T.get_trade_stats()
    assert stats["total_pnl"] == 200.0
    assert stats["win_count"] == 1
    assert stats["loss_count"] == 0


def test_short_pnl_calculation(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    _write_trades(tmp_path, [{
        "id": "1", "symbol": "AAPL", "direction": "short",
        "open_price": 100, "close_price": 80, "quantity": 10, "status": "closed",
        "open_date": "2024-01-01", "close_date": "2024-02-01",
    }])
    stats = T.get_trade_stats()
    assert stats["total_pnl"] == 200.0


def test_win_rate(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    _write_trades(tmp_path, [
        {"id": "1", "symbol": "A", "direction": "long", "open_price": 100, "close_price": 110, "quantity": 10, "status": "closed"},
        {"id": "2", "symbol": "B", "direction": "long", "open_price": 100, "close_price": 90, "quantity": 10, "status": "closed"},
        {"id": "3", "symbol": "C", "direction": "long", "open_price": 100, "close_price": 105, "quantity": 10, "status": "closed"},
    ])
    stats = T.get_trade_stats()
    assert stats["win_count"] == 2
    assert stats["loss_count"] == 1
    assert stats["win_rate"] == round(2 / 3 * 100, 1)


def test_update_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    t = T.create_trade({"symbol": "AAPL", "open_price": 100, "quantity": 10})
    updated = T.update_trade(t["id"], {"close_price": 110, "close_date": "2024-02-01"})
    assert updated["status"] == "closed"
    assert updated["close_price"] == 110


def test_delete_trade(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "TRADES_FILE", tmp_path / "trades.json")
    t = T.create_trade({"symbol": "AAPL", "open_price": 100, "quantity": 10})
    assert T.delete_trade(t["id"]) is True
    assert T.delete_trade(t["id"]) is False
