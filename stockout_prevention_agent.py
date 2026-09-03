import os
import sys
import json
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db.db import get_connection


def fnum(v):
    """SQL-sourced numeric fields are already typed (REAL/None) by
    db/ingest_retail_items.py and db/ingest_cogs_report.py -- unlike the
    original CSV-parsing version, no string cleanup is needed here. Only
    None (blank/missing) still needs to collapse to 0.0, same as the old
    "not v" blank check."""
    if v is None:
        return 0.0
    return float(v)


def run_stockout_prevention_agent():
    business_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(business_dir, "dashboard_app")
    os.makedirs(out_dir, exist_ok=True)

    print(f"=== Autonomous Stockout Prevention & Auto-Reorder Agent [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    conn = get_connection()

    # Retail items -- from the SQL warehouse's item_current view (single
    # latest full retail-items export), not a freshly-globbed CSV.
    # MIGRATED 2026-08-14: replaces the "find latest retail-items export"
    # regex/glob/sort block entirely.
    items = conn.execute("SELECT * FROM item_current").fetchall()
    if not items:
        conn.close()
        print("[ERROR] item_snapshots is empty -- run db/ingest_retail_items.py first.")
        return {"error": "no retail-items export found"}

    # COGS sales quantity -- from cogs_snapshots, filtered to the same
    # cumulative-from-April-1 report window the original script picked
    # via `"20260401" in filename`. MIGRATED 2026-08-14: cogs_snapshots
    # contains MULTIPLE window types (April-1-cumulative AND several
    # shorter partial windows), so the generic cogs_current view (latest
    # window overall, regardless of start date) is NOT a safe substitute
    # here -- confirmed during migration review. This explicit
    # report_start_date filter replicates the original file-selection
    # exactly: same window, same "latest end date within that window."
    window = conn.execute(
        "SELECT MAX(report_end_date) AS max_end FROM cogs_snapshots WHERE report_start_date = '2026-04-01'"
    ).fetchone()
    if not window or not window["max_end"]:
        conn.close()
        print("[ERROR] No 2026-04-01-cumulative COGS window found in cogs_snapshots -- run db/ingest_cogs_report.py first.")
        return {"error": "no matching COGS window found"}
    report_end_date = window["max_end"]
    print(f"[INFO] Using COGS window: 2026-04-01 to {report_end_date} (SQL warehouse: cogs_snapshots)")

    cogs_rows = conn.execute(
        "SELECT item_id, item_name, quantity_sold FROM cogs_snapshots "
        "WHERE report_start_date = '2026-04-01' AND report_end_date = ?",
        (report_end_date,),
    ).fetchall()
    conn.close()

    sales_qty = defaultdict(float)
    for r in cogs_rows:
        qty = fnum(r["quantity_sold"])
        sku = (r["item_id"] or "").strip()
        name = (r["item_name"] or "").strip()
        if sku:
            sales_qty[sku] += qty
        if name:
            sales_qty[name] += qty

    days_in_window = 125.0  # Apr 1 to Aug 4

    stockout_alerts = []

    for r in items:
        # Original CSV version read r.get('sku') (never a real column in
        # the POS export -- only 'item id') falling back to r.get('item
        # id'), and r.get('sales category') (a real, separate column from
        # 'category', preferred when non-blank) falling back to
        # r.get('category'). Preserved exactly here via item_current's
        # item_id and sales_category/category columns -- see schema.sql
        # and db.py for how sales_category was added to capture this.
        sku = (r["item_id"] or "").strip()
        name = (r["name"] or "").strip()
        cat = (r["sales_category"] or r["category"] or "").strip()
        price = fnum(r["price"])
        cost = fnum(r["cost"])
        qty_on_hand = fnum(r["inventory_quantity"])

        total_qty_sold = sales_qty.get(sku) or sales_qty.get(name) or 0.0
        daily_velocity = total_qty_sold / days_in_window

        if daily_velocity > 0 and qty_on_hand <= (daily_velocity * 14):
            days_left = round(qty_on_hand / daily_velocity, 1) if daily_velocity > 0 else 999
            reorder_qty = max(12, int(daily_velocity * 30))

            alert = {
                "sku": sku, "name": name, "category": cat,
                "retailPrice": price, "unitCost": cost, "qtyOnHand": qty_on_hand,
                "dailyVelocity": round(daily_velocity, 2),
                "daysInventoryRemaining": days_left,
                "recommendedReorderQty": reorder_qty,
                "estimatedPOCost": round(reorder_qty * cost, 2)
            }
            stockout_alerts.append(alert)

    stockout_alerts.sort(key=lambda x: x["daysInventoryRemaining"])

    output_data = {
        "asOfTimestamp": datetime.now().isoformat(),
        "totalMonitoredSKUs": len(items),
        "atRiskStockoutSKUs": len(stockout_alerts),
        "urgentStockouts": stockout_alerts[:25]
    }

    out_file = os.path.join(out_dir, "stockout_alerts_live.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n[SUCCESS] Identified {len(stockout_alerts)} SKUs at risk of stockout -> {out_file}")

    print("==========================================================================")
    print(" TOP URGENT REORDER ALERTS (STOCKOUT PREVENTION)")
    print("==========================================================================")
    for alert in stockout_alerts[:5]:
        print(f"   • {alert['name']:<35} Stock: {alert['qtyOnHand']:>2} | Days Left: {alert['daysInventoryRemaining']:>4.1f} days -> Reorder: {alert['recommendedReorderQty']} units (${alert['estimatedPOCost']:.2f})")
    print("==========================================================================\n")

    return output_data


if __name__ == "__main__":
    run_stockout_prevention_agent()

