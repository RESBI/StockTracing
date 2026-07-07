"""Tests for backend.services.institution_normalizer."""
from backend.services.institution_normalizer import (
    clean_ticker,
    normalize_issuer,
    normalize_sector,
    normalize_value_units,
    detect_option_type,
    infer_from_issuer,
    infer_sector_from_name,
    standardize_row,
    aggregate_holdings,
    compare_with_history,
    normalize_holdings,
)


def test_clean_ticker_valid():
    assert clean_ticker("aapl") == "AAPL"
    assert clean_ticker(" BRK.B ") == "BRK.B"
    assert clean_ticker("0700.HK") == ""


def test_clean_ticker_invalid():
    assert clean_ticker("") == ""
    assert clean_ticker("TOOLONG") == ""
    assert clean_ticker("123") == ""


def test_normalize_issuer_strips_suffix():
    assert normalize_issuer("Apple Inc") == "Apple"
    assert normalize_issuer("Coca Cola Corp") == "Coca Cola"
    assert normalize_issuer("Foo COM") == "Foo"
    assert normalize_issuer("Bar CL A") == "Bar"


def test_normalize_sector_translations():
    assert normalize_sector("Technology") == "科技"
    assert normalize_sector("Financial Services") == "金融"
    assert normalize_sector("Healthcare") == "医疗保健"
    assert normalize_sector("") == "未分类"
    assert normalize_sector("Unknown") == "Unknown"


def test_normalize_value_units_large_ratio():
    assert normalize_value_units(100000, 1) == 100
    assert normalize_value_units(1000, 1) == 1000
    assert normalize_value_units(0, 0) == 0


def test_detect_option_type():
    assert detect_option_type({"put_call": "PUT"}) == "PUT"
    assert detect_option_type({"put_call": "CALL"}) == "CALL"
    assert detect_option_type({"put_call": "", "name": "AAPL", "title": ""}) == "SHARE"
    assert detect_option_type({"name": "AAPL PUT", "title": ""}) == "PUT"
    assert detect_option_type({"name": "AAPL CALL", "title": ""}) == "CALL"


def test_infer_from_issuer_keyword():
    r = infer_from_issuer("APPLE INC")
    assert r["ticker"] == "AAPL"
    assert r["sector"] == "科技"

    r2 = infer_from_issuer("Microsoft Corporation")
    assert r2["ticker"] == "MSFT"

    assert infer_from_issuer("Unknown Company XYZ") is None


def test_infer_sector_from_name():
    assert infer_sector_from_name("Moderna Pharmaceuticals") == "医疗保健"
    assert infer_sector_from_name("China Bank Corp") == "金融"
    assert infer_sector_from_name("Foo Software Systems") == "科技"
    assert infer_sector_from_name("Random Name") == ""


def test_standardize_row_cusip_map():
    row = {
        "cusip": "037833100",
        "name": "Apple Inc",
        "shares": 1000,
        "value": 150000,
        "put_call": "",
        "symbol": "",
    }
    r = standardize_row(row)
    assert r["ticker"] == "AAPL"
    assert r["name"] == "Apple"
    assert r["sector"] == "科技"
    assert r["value"] == 150000
    assert r["asset_type"] == "SHARE"
    assert r["display_symbol"] == "AAPL"


def test_aggregate_holdings_merges_same_ticker():
    rows = [
        {"cusip": "037833100", "name": "Apple Inc", "shares": 100, "value": 15000, "put_call": "", "symbol": ""},
        {"cusip": "037833100", "name": "Apple Inc", "shares": 200, "value": 30000, "put_call": "", "symbol": ""},
    ]
    result = aggregate_holdings(rows)
    assert len(result) == 1
    assert result[0]["shares"] == 300
    assert result[0]["value"] == 45000
    assert len(result[0]["cusips"]) == 1


def test_aggregate_holdings_separates_put_call():
    rows = [
        {"cusip": "037833100", "name": "Apple Inc", "shares": 100, "value": 15000, "put_call": "", "symbol": ""},
        {"cusip": "037833100", "name": "Apple Inc", "shares": 50, "value": 5000, "put_call": "PUT", "symbol": ""},
    ]
    result = aggregate_holdings(rows)
    assert len(result) == 2
    types = sorted(r["asset_type"] for r in result)
    assert types == ["PUT", "SHARE"]


def test_compare_with_history():
    rows = [
        {"ticker": "AAPL", "cusip": "", "symbol": "", "shares": 100, "value": 15000, "name": "Apple"},
        {"ticker": "MSFT", "cusip": "", "symbol": "", "shares": 200, "value": 40000, "name": "Microsoft"},
    ]
    previous = {
        "AAPL": {"shares": 80, "value": 12000},
    }
    result = compare_with_history(rows, previous)
    aapl = next(r for r in result if r["ticker"] == "AAPL")
    msft = next(r for r in result if r["ticker"] == "MSFT")
    assert aapl["change_shares"] == 20
    assert msft["change_shares"] == 0


def test_normalize_holdings_end_to_end():
    rows = [
        {"cusip": "037833100", "name": "Apple Inc", "shares": 100, "value": 15000, "put_call": "", "symbol": ""},
    ]
    result = normalize_holdings(rows)
    assert len(result) == 1
    assert result[0]["ticker"] == "AAPL"
    assert result[0]["change_shares"] == 0

    result2 = normalize_holdings(rows, previous={"AAPL": {"shares": 60, "value": 9000}})
    assert result2[0]["change_shares"] == 40
