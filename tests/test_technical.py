"""Tests for backend.services.technical signal generation."""
import math

import numpy as np
import pytest

from backend.services.technical import _generate_signals, _sma, _ema


def _nan_arr(n, fill_idx=None, fill_val=None):
    arr = np.full(n, np.nan)
    if fill_idx is not None:
        arr[fill_idx] = fill_val
    return arr


def test_rsi_overbought_emits_sell():
    p = pytest.MONKEYPATCH if hasattr(pytest, "MONKEYPATCH") else None
    closes = np.linspace(100, 150, 30)
    volumes = np.full(30, 1000)
    rsi = np.full(30, np.nan)
    rsi[-1] = 75
    macd_hist = np.zeros(30)
    macd_hist[-1] = 0.1
    stoch_k = np.full(30, np.nan)
    stoch_k[-1] = 50
    bb_upper = np.full(30, 160)
    bb_lower = np.full(30, 90)
    sma_short = np.full(30, 120)
    sma_long = np.full(30, 115)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 150.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    rsi_sig = next(s for s in signals if s["indicator"] == "RSI")
    assert rsi_sig["signal"] == "sell"
    assert "超买" in rsi_sig["detail"]


def test_rsi_oversold_emits_buy():
    closes = np.linspace(100, 90, 30)
    volumes = np.full(30, 1000)
    rsi = np.full(30, np.nan)
    rsi[-1] = 25
    macd_hist = np.zeros(30)
    macd_hist[-1] = -0.1
    stoch_k = np.full(30, np.nan)
    stoch_k[-1] = 50
    bb_upper = np.full(30, 110)
    bb_lower = np.full(30, 80)
    sma_short = np.full(30, 95)
    sma_long = np.full(30, 96)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 90.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    rsi_sig = next(s for s in signals if s["indicator"] == "RSI")
    assert rsi_sig["signal"] == "buy"


def test_macd_golden_cross():
    closes = np.full(30, 100.0)
    volumes = np.full(30, 1000)
    rsi = np.full(30, 50.0)
    macd_hist = np.zeros(30)
    macd_hist[-2] = -0.5
    macd_hist[-1] = 0.5
    stoch_k = np.full(30, 50.0)
    bb_upper = np.full(30, 110.0)
    bb_lower = np.full(30, 90.0)
    sma_short = np.full(30, 100.0)
    sma_long = np.full(30, 100.0)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 100.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    macd_sig = next(s for s in signals if s["indicator"] == "MACD")
    assert macd_sig["signal"] == "buy"
    assert "金叉" in macd_sig["detail"]


def test_macd_death_cross():
    closes = np.full(30, 100.0)
    volumes = np.full(30, 1000)
    rsi = np.full(30, 50.0)
    macd_hist = np.zeros(30)
    macd_hist[-2] = 0.5
    macd_hist[-1] = -0.5
    stoch_k = np.full(30, 50.0)
    bb_upper = np.full(30, 110.0)
    bb_lower = np.full(30, 90.0)
    sma_short = np.full(30, 100.0)
    sma_long = np.full(30, 100.0)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 100.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    macd_sig = next(s for s in signals if s["indicator"] == "MACD")
    assert macd_sig["signal"] == "sell"
    assert "死叉" in macd_sig["detail"]


def test_bollinger_breakout_upper():
    closes = np.full(30, 100.0)
    volumes = np.full(30, 1000)
    rsi = np.full(30, 50.0)
    macd_hist = np.zeros(30)
    stoch_k = np.full(30, 50.0)
    bb_upper = np.full(30, 105.0)
    bb_lower = np.full(30, 95.0)
    sma_short = np.full(30, 100.0)
    sma_long = np.full(30, 100.0)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 106.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    bb_sig = next(s for s in signals if s["indicator"] == "Bollinger")
    assert bb_sig["signal"] == "sell"


def test_composite_score_aggregates():
    closes = np.full(30, 100.0)
    volumes = np.full(30, 1000)
    rsi = np.full(30, 25.0)
    macd_hist = np.zeros(30)
    macd_hist[-2] = -0.5
    macd_hist[-1] = 0.5
    stoch_k = np.full(30, 15.0)
    bb_upper = np.full(30, 80.0)
    bb_lower = np.full(30, 95.0)
    sma_short = np.full(30, 100.0)
    sma_long = np.full(30, 100.0)

    signals = _generate_signals(
        {"dummy": True}, closes, volumes, 90.0,
        rsi, macd_hist, stoch_k, bb_upper, bb_lower, sma_short, sma_long,
    )
    composite = next(s for s in signals if s["indicator"] == "综合评分")
    assert composite["signal"] == "buy"


def test_sma_basic():
    data = np.array([1, 2, 3, 4, 5], dtype=float)
    result = _sma(data, 3)
    assert math.isnan(result[0])
    assert math.isnan(result[1])
    assert result[2] == 2.0
    assert result[4] == 4.0


def test_ema_basic():
    data = np.array([10, 10, 10, 10], dtype=float)
    result = _ema(data, 3)
    assert result[2] == 10.0
