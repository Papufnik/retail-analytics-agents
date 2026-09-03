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
    original CSV-parsing version, no $/,/% string cleanup is needed here.
    Only None (blank/missing) still needs to collapse to 0.0, same as the
    old "not v" blank check."""
    if v is None:
        return 0.0
    return float(v)


def run_markdown_optimization_agent():
    business_dir = os.path.dirname(os.path.abspath(__file__))
    out_dir = os.path.join(business_dir, "dashboard_app")
    os.makedirs(out_dir, exist_ok=True)

    print(f"=== Markdown & Clearance Optimizer Agent [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    conn = get_connection()

    # Retail items -- from the SQL warehouse's item_current view (single
    # latest full retail-items export), not a freshly-globbed CSV.
    # MIGRATED 2026-08-14: replaces the timestamped-filename glob/regex/
    # sort block entirely -- same pattern as stockout_prevention_agent.py.
    items = conn.execute("SELECT * FROM item_current").fetchall()
    if not items:
        conn.close()
        print("[ERROR] item_snapshots is empty -- run db/ingest_retail_items.py first.")
        return {"error": "no retail-items export found"}
    _meta = conn.execute("SELECT export_filename FROM item_current LIMIT 1").fetchone()
    print(f"Source retail export: {_meta['export_filename']} (SQL warehouse: item_current)")

    # COGS sales quantity -- from cogs_snapshots, filtered to the same
    # cumulative-from-April-1 report window the original script picked via
    # `"20260401" in filename`. MIGRATED 2026-08-14: cogs_snapshots holds
    # multiple window types (April-1-cumulative AND several shorter
    # partial windows), so the generic cogs_current view is NOT a safe
    # substitute here -- same finding as stockout_prevention_agent.py's
    # migration. This explicit report_start_date filter replicates the
    # original file-selection exactly.
    window = conn.execute(
        "SELECT MAX(report_end_date) AS max_end FROM cogs_snapshots WHERE report_start_date = '2026-04-01'"
    ).fetchone()
    if not window or not window["max_end"]:
        conn.close()
        print("[ERROR] No 2026-04-01-cumulative COGS window found in cogs_snapshots -- run db/ingest_cogs_report.py first.")
        return {"error": "no COGS report found"}
    report_start_date = "2026-04-01"
    report_end_date = window["max_end"]
    print(f"Source COGS window: {report_start_date} to {report_end_date} (SQL warehouse: cogs_snapshots)")

    cogs_rows = conn.execute(
        "SELECT item_id, item_name, quantity_sold FROM cogs_snapshots "
        "WHERE report_start_date = ? AND report_end_date = ?",
        (report_start_date, report_end_date),
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

    # Original parsed the day count from the COGS filename's
    # "_YYYYMMDD-YYYYMMDD.csv" suffix. MIGRATED 2026-08-14: same
    # inclusive-day-count math (end - start + 1), now off the SQL
    # window's actual dates instead of a filename regex.
    start_d = datetime.strptime(report_start_date, "%Y-%m-%d")
    end_d = datetime.strptime(report_end_date, "%Y-%m-%d")
    days_in_window = max(1.0, (end_d - start_d).days + 1)
    print(f"Sales velocity window: {days_in_window:.0f} days")

    markdown_candidates = []

    for r in items:
        # Original CSV version read r.get('sku') (never a real column in
        # the POS export -- only 'item id') falling back to r.get('item
        # id'), and r.get('sales category') (a real, separate column from
        # 'category', preferred when non-blank) falling back to
        # r.get('category'). Preserved exactly via item_current's item_id
        # and sales_category/category columns -- see schema.sql and
        # db.py for how sales_category was added (during the
        # stockout_prevention_agent.py migration) to capture this.
        sku = (r["item_id"] or "").strip()
        name = (r["name"] or "").strip()
        cat = (r["sales_category"] or r["category"] or "").strip()
        price = fnum(r["price"])
        cost = fnum(r["cost"])
        qty_on_hand = fnum(r["inventory_quantity"])

        total_qty_sold = sales_qty.get(sku) or sales_qty.get(name) or 0.0
        daily_velocity = total_qty_sold / days_in_window

        # Candidate for markdown if has stock on hand (> 2 units) AND zero or near-zero sales velocity (< 0.02 units/day)
        if qty_on_hand >= 2 and daily_velocity < 0.02 and price > 0:
            # Algorithmic Promotional Pricing Rules:
            # Tier 1: 15% Promo Discount (Protects 70%+ Gross Margin)
            # Tier 2: 25% Clearance Discount (Protects 60%+ Gross Margin)
            # Tier 3: 35% Liquidation Discount (Clears cash value)

            if qty_on_hand <= 5:
                discount_pct = 0.15
                tier = "Tier 1: 15% Seasonal Promo"
            elif qty_on_hand <= 10:
                discount_pct = 0.25
                tier = "Tier 2: 25% Clearance Markdown"
            else:
                discount_pct = 0.35
                tier = "Tier 3: 35% Liquidation Sale"

            promo_price = round(price * (1.0 - discount_pct), 2)
            promo_margin = round(((promo_price - cost) / promo_price * 100), 1) if promo_price > 0 else 0

            cand = {
                "sku": sku,
                "name": name,
                "category": cat,
                "originalPrice": price,
                "unitCost": cost,
                "qtyOnHand": qty_on_hand,
                "recommendedTier": tier,
                "discountPct": f"{int(discount_pct*100)}%",
                "recommendedPromoPrice": promo_price,
                "protectedGrossMargin": f"{promo_margin}%",
                "totalTiedUpCapital": round(qty_on_hand * cost, 2)
            }
            markdown_candidates.append(cand)

    # Sort by total tied up capital (highest dollar value first)
    markdown_candidates.sort(key=lambda x: x["totalTiedUpCapital"], reverse=True)

    output_data = {
        "asOfTimestamp": datetime.now().isoformat(),
        "totalSlowMovingSKUs": len(markdown_candidates),
        "totalCapitalTiedUp": round(sum(c["totalTiedUpCapital"] for c in markdown_candidates), 2),
        "topMarkdownRecommendations": markdown_candidates[:25]
    }

    out_file = os.path.join(out_dir, "markdown_optimization_live.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    print(f"\n[SUCCESS] Generated Markdown Optimization Feed ({len(markdown_candidates)} slow SKUs) -> {out_file}")

    print("==========================================================================")
    print(" TOP DYNAMIC MARKDOWN & CLEARANCE RECOMMENDATIONS")
    print("==========================================================================")
    for cand in markdown_candidates[:5]:
        print(f"   • {cand['name']:<35} Stock: {cand['qtyOnHand']:>2} | Orig: ${cand['originalPrice']:.2f} -> Promo: ${cand['recommendedPromoPrice']:.2f} ({cand['discountPct']} off) | Margin: {cand['protectedGrossMargin']}")
    print("==========================================================================\n")

    return output_data

if __name__ == "__main__":
    run_markdown_optimization_agent()

