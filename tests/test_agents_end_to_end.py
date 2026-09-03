"""
End-to-end tests against the illustrative sample warehouse (see
tests/conftest.py). These exercise all three agents the same way
demo.py does, and specifically pin down the real bug-fix scenario from
build_sample_data.py's own comments: Alpine Trail Beanie's wholesale price
DROPPED between two orders and must NOT alert, while Summit Puffer Vest's
price genuinely rose and MUST alert.
"""
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from margin_erosion_agent import run_margin_erosion_check
from stockout_prevention_agent import run_stockout_prevention_agent
from markdown_optimization_agent import run_markdown_optimization_agent


def test_margin_erosion_does_not_alert_on_a_genuine_price_drop():
    payload = run_margin_erosion_check()
    flagged_names = {a["product_name"] for a in payload["topAnomalies"]}
    # POS pos_name for this SKU is "Trail Beanie" -- confirming it's absent
    # under either name is the real assertion that no false alert fired.
    assert "Alpine Trail Beanie" not in flagged_names
    assert "Trail Beanie" not in flagged_names


def test_margin_erosion_alerts_on_a_genuine_price_increase():
    payload = run_margin_erosion_check()
    # product_name comes from the POS system's own pos_name field
    # ("Puffer Vest"), not the wholesale order's Product Name -- see
    # run_margin_erosion_check()'s alert-building logic.
    flagged_names = {a["product_name"] for a in payload["topAnomalies"]}
    assert "Puffer Vest" in flagged_names
    vest = next(a for a in payload["topAnomalies"] if a["product_name"] == "Puffer Vest")
    assert vest["new_wholesale_cost"] == 39.50
    assert vest["pos_cost"] == 36.00


def test_stockout_prevention_flags_low_stock_high_velocity_skus():
    payload = run_stockout_prevention_agent()
    at_risk_names = {a["name"] for a in payload["urgentStockouts"]}
    # Alpine Trail Beanie (qty 3) and Summit Puffer Vest (qty 2) are the
    # sample data's deliberately low-stock, high-velocity SKUs.
    assert "Alpine Trail Beanie" in at_risk_names
    assert "Summit Puffer Vest" in at_risk_names


def test_stockout_prevention_does_not_flag_well_stocked_skus():
    payload = run_stockout_prevention_agent()
    at_risk_names = {a["name"] for a in payload["urgentStockouts"]}
    # Ridge Line Flannel carries 40 units against modest sales -- nowhere
    # near a 14-day stockout window.
    assert "Ridge Line Flannel" not in at_risk_names


def test_markdown_optimization_flags_the_dead_stock_sku():
    payload = run_markdown_optimization_agent()
    flagged_names = {c["name"] for c in payload["topMarkdownRecommendations"]}
    # The discontinued print tee has real stock (34 units) and zero sales
    # velocity in the sample COGS window -- the exact markdown-candidate case.
    assert "Discontinued Print Tee (Old Logo)" in flagged_names


def test_markdown_tier_assignment_matches_documented_thresholds():
    payload = run_markdown_optimization_agent()
    tee = next(
        c for c in payload["topMarkdownRecommendations"]
        if c["name"] == "Discontinued Print Tee (Old Logo)"
    )
    # 34 units on hand -> Tier 3 (35% liquidation), per the >10-unit rule.
    assert tee["discountPct"] == "35%"
    assert tee["recommendedPromoPrice"] == round(22.00 * 0.65, 2)
