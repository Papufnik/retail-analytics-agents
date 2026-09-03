"""
Tests for margin_erosion_agent.py -- pins down the exact real bug the
README describes: an earlier version tracked the HIGHEST wholesale price
ever paid per SKU as "current cost," which could manufacture a false
margin-erosion alert for a SKU whose price actually went DOWN. The fix
tracks the MOST RECENT order date's price instead.
"""
import os
import sys
import csv

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
sys.path.insert(0, REPO_ROOT)

from margin_erosion_agent import load_wholesale_orders


def _write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["SKU", "Product Name", "Wholesale Price", "Order Date", "Brand Name"]
        )
        writer.writeheader()
        writer.writerows(rows)


def test_load_wholesale_orders_keeps_most_recent_price_when_price_dropped(tmp_path):
    """The real bug scenario: Alpine Trail Beanie's price went DOWN from
    $11.00 (Jan) to $9.50 (Jul). The old "keep the highest" logic would
    have kept $11.00 and could manufacture a false alert. The fix must
    keep $9.50 -- the most recent order."""
    csv_path = tmp_path / "wholesale-orders.csv"
    _write_csv(csv_path, [
        {"SKU": "", "Product Name": "Alpine Trail Beanie", "Wholesale Price": "$11.00",
         "Order Date": "January 14, 2026", "Brand Name": "Alpine Supply Co."},
        {"SKU": "", "Product Name": "Alpine Trail Beanie", "Wholesale Price": "$9.50",
         "Order Date": "July 02, 2026", "Brand Name": "Alpine Supply Co."},
    ])
    costs = load_wholesale_orders(str(csv_path))
    assert costs["Alpine Trail Beanie"]["cost"] == 9.50


def test_load_wholesale_orders_keeps_most_recent_price_when_price_rose(tmp_path):
    """The companion case: Summit Puffer Vest's price genuinely rose from
    $34.00 to $39.50 -- the most recent (higher) price must win, so this
    SKU correctly remains alert-eligible."""
    csv_path = tmp_path / "wholesale-orders.csv"
    _write_csv(csv_path, [
        {"SKU": "", "Product Name": "Summit Puffer Vest", "Wholesale Price": "$34.00",
         "Order Date": "February 10, 2026", "Brand Name": "Summit Outfitters"},
        {"SKU": "", "Product Name": "Summit Puffer Vest", "Wholesale Price": "$39.50",
         "Order Date": "July 18, 2026", "Brand Name": "Summit Outfitters"},
    ])
    costs = load_wholesale_orders(str(csv_path))
    assert costs["Summit Puffer Vest"]["cost"] == 39.50


def test_load_wholesale_orders_falls_back_to_sku_when_present(tmp_path):
    csv_path = tmp_path / "wholesale-orders.csv"
    _write_csv(csv_path, [
        {"SKU": "SKU-9001", "Product Name": "Widget", "Wholesale Price": "$5.00",
         "Order Date": "January 01, 2026", "Brand Name": "Acme"},
    ])
    costs = load_wholesale_orders(str(csv_path))
    assert "SKU-9001" in costs
    assert "Widget" not in costs


def test_load_wholesale_orders_skips_unparseable_price_row(tmp_path, capsys):
    csv_path = tmp_path / "wholesale-orders.csv"
    _write_csv(csv_path, [
        {"SKU": "", "Product Name": "Broken Row", "Wholesale Price": "N/A",
         "Order Date": "January 01, 2026", "Brand Name": "Acme"},
        {"SKU": "", "Product Name": "Good Row", "Wholesale Price": "$3.00",
         "Order Date": "January 01, 2026", "Brand Name": "Acme"},
    ])
    costs = load_wholesale_orders(str(csv_path))
    assert "Broken Row" not in costs
    assert costs["Good Row"]["cost"] == 3.00
    assert "Skipped 1" in capsys.readouterr().out


def test_load_wholesale_orders_row_with_unparseable_date_only_used_as_fallback(tmp_path):
    """A row with a real date should always beat a row with no usable
    date, regardless of CSV order."""
    csv_path = tmp_path / "wholesale-orders.csv"
    _write_csv(csv_path, [
        {"SKU": "", "Product Name": "Item", "Wholesale Price": "$1.00",
         "Order Date": "not a date", "Brand Name": "Acme"},
        {"SKU": "", "Product Name": "Item", "Wholesale Price": "$2.00",
         "Order Date": "March 03, 2026", "Brand Name": "Acme"},
    ])
    costs = load_wholesale_orders(str(csv_path))
    assert costs["Item"]["cost"] == 2.00
