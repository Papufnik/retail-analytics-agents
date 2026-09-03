import os
import csv
import json
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db.db import get_connection

# 2026-08-11 FIX: this used to keep the HIGHEST wholesale price ever paid
# per SKU ("i.e. vendor price hikes"), which conflates "worst historical
# price" with "current price." Checked against the real wholesale-orders.csv:
# 13 SKUs have more than one distinct wholesale price on record, and for 2
# of them (1001: $37.50 -> $34.50; 1004: $38.50 -> $36.00) the price has
# actually come DOWN over time -- the old logic would report a stale,
# inflated "current cost" for those and could manufacture a margin-erosion
# alert that isn't real. This now tracks the cost from the MOST RECENT
# order date per SKU, which is what "what are we paying now" actually means.
# Malformed rows (bad date, bad price) are skipped with a warning rather
# than crashing the whole agent -- this feeds the daily executive email via
# daily_email_dispatcher.py, so one bad row silently killing the section is
# worse than one bad row being skipped and logged.
def load_wholesale_orders(wholesale_path):
    """
    Extracts the MOST RECENT wholesale price paid for each SKU, from all
    wholesale marketplace orders on record.
    """
    wholesale_costs = {}
    skipped = 0
    with open(wholesale_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sku = row.get("SKU", "").strip()
            name = row.get("Product Name", "").strip()
            cost_raw = row.get("Wholesale Price", "")
            date_raw = row.get("Order Date", "").strip()

            key = sku if sku else name
            if not key or not cost_raw:
                continue

            try:
                cost = float(cost_raw.replace('$', '').replace(',', '').strip())
            except (ValueError, AttributeError):
                skipped += 1
                continue

            order_date = None
            if date_raw:
                try:
                    order_date = datetime.strptime(date_raw, "%B %d, %Y")
                except ValueError:
                    pass  # keep the row (still usable by cost), just can't rank it by recency

            existing = wholesale_costs.get(key)
            # Prefer whichever row has the most recent parseable date; if
            # this row's date can't be parsed, only use it as a fallback
            # when nothing better exists yet for this key.
            if existing is None:
                use_this = True
            elif order_date is not None and existing.get("_order_date") is not None:
                use_this = order_date > existing["_order_date"]
            elif order_date is not None:
                use_this = True  # this row has a real date, existing didn't
            else:
                use_this = False

            if use_this:
                wholesale_costs[key] = {
                    "cost": cost,
                    "name": name,
                    "brand": row.get("Brand Name", "").strip(),
                    "date": date_raw,
                    "_order_date": order_date,
                }

    if skipped:
        print(f"[WARNING] Skipped {skipped} wholesale marketplace order row(s) with an unparseable Wholesale Price.")
    return wholesale_costs

def load_pos_inventory():
    """
    Reads current inventory cost and retail price from the SQL warehouse's
    item_current view (single latest full retail-items export) --
    MIGRATED 2026-08-14, replacing a direct read of the newest
    retail-items-*.csv. Values are already typed (REAL/None) by
    db/ingest_retail_items.py's own money() parsing, so the "non-numeric"
    skip path from the CSV-parsing version can no longer occur here (that
    failure mode was already resolved once, at ingestion time) -- only the
    "blank cost or price" and "price == 0" skips still apply, same as
    before.
    """
    conn = get_connection()
    rows = conn.execute(
        "SELECT name, pos_name, cost, price FROM item_current"
    ).fetchall()
    conn.close()

    pos_items = []
    skipped_blank = 0
    for row in rows:
        name = (row["name"] or "").strip()
        pos_name = (row["pos_name"] or "").strip()
        cost = row["cost"]
        price = row["price"]

        if cost is None or price is None:
            skipped_blank += 1
            continue
        if price == 0:
            continue

        pos_items.append({
            "sku_or_name": name,
            "pos_name": pos_name,
            "cost": cost,
            "price": price,
            "margin_pct": ((price - cost) / price) * 100
        })
    if skipped_blank:
        print(f"[WARN] Skipped {skipped_blank} POS item row(s) with a blank cost or price.")
    return pos_items

def run_margin_erosion_check():
    business_dir = os.path.dirname(os.path.abspath(__file__))
    exports_dir = os.path.join(business_dir, "sample_data")
    dash_dir = os.path.join(business_dir, "dashboard_app")
    # 2026-09-03 FIX: unlike stockout_prevention_agent.py and
    # markdown_optimization_agent.py, this script never created dash_dir
    # before writing to it -- caught by a new end-to-end test, since
    # demo.py runs this agent FIRST, a genuinely fresh clone with no
    # dashboard_app/ directory yet would crash on the very first run.
    os.makedirs(dash_dir, exist_ok=True)

    print(f"=== Margin-Erosion Agent [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ===")

    # 1. Load the wholesale marketplace Orders
    wholesale_path = os.path.join(exports_dir, "wholesale-orders.csv")
    if not os.path.exists(wholesale_path):
        print(f"[ERROR] Missing the wholesale marketplace export: {wholesale_path}")
        return

    wholesale_costs = load_wholesale_orders(wholesale_path)
    print(f"[INFO] Loaded {len(wholesale_costs)} unique items from wholesale marketplace orders.")

    # 2. the POS platform inventory -- from the SQL warehouse (item_current), not a
    # freshly-globbed CSV. MIGRATED 2026-08-14: replaces the "find latest
    # POS Export" glob/regex/sort block entirely -- "current" is now a
    # SQL fact, not something re-derived from a directory listing.
    conn = get_connection()
    _meta = conn.execute("SELECT export_filename FROM item_current LIMIT 1").fetchone()
    conn.close()
    if not _meta:
        print("[ERROR] item_snapshots is empty -- run db/ingest_retail_items.py first.")
        return
    print(f"[INFO] Using POS export: {_meta['export_filename']} (SQL warehouse: item_current)")

    pos_items = load_pos_inventory()
    print(f"[INFO] Loaded {len(pos_items)} items from the POS platform.")

    # 3. Detect Margin Erosion
    alerts = []
    matched_count = 0
    for item in pos_items:
        # Match the wholesale marketplace SKU against the POS platform 'name' or 'pos name'
        match = wholesale_costs.get(item["sku_or_name"]) or wholesale_costs.get(item["pos_name"])
        if not match:
            continue
        matched_count += 1

        new_wholesale = match["cost"]
        pos_cost = item["cost"]
        pos_price = item["price"]

        # If the wholesale cost is strictly higher than the cost loaded into the POS system
        if new_wholesale > pos_cost:
            old_margin = item["margin_pct"]
            new_margin = ((pos_price - new_wholesale) / pos_price) * 100

            alerts.append({
                "sku": item["sku_or_name"],
                "product_name": item["pos_name"] or match["name"],
                "vendor": match["brand"],
                "retail_price": pos_price,
                "pos_cost": pos_cost,
                "new_wholesale_cost": new_wholesale,
                "old_margin_pct": old_margin,
                "new_margin_pct": new_margin,
                "cost_increase_amt": new_wholesale - pos_cost
            })

    # Sort by absolute margin drop
    alerts.sort(key=lambda x: x["old_margin_pct"] - x["new_margin_pct"], reverse=True)

    print(f"[INFO] Matched {matched_count} of {len(pos_items)} POS items to a wholesale marketplace order "
          f"(name/SKU exact match only -- a low match rate here means most items simply don't "
          f"have a comparable wholesale marketplace order on record, not that the script is broken).")
    print(f"[SUCCESS] Detected {len(alerts)} items with margin erosion.")

    payload = {
        "asOfDate": datetime.now().strftime("%B %d, %Y"),
        "totalAlerts": len(alerts),
        "topAnomalies": alerts[:5], # Only expose top 5 to avoid email clutter
        "status": "LIVE"
    }

    out_file = os.path.join(dash_dir, "margin_erosion_alerts.json")
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2)

    print(f"[SUCCESS] Wrote margin alerts -> {out_file}")

    # 2026-09-03 FIX: unlike stockout_prevention_agent.py and
    # markdown_optimization_agent.py, this function fell off the end
    # without returning its payload -- harmless for demo.py (which only
    # relies on the side effect of the JSON file being written), but it
    # meant nothing could call this function as a value and get real data
    # back. Caught by the same new end-to-end test suite.
    return payload

if __name__ == "__main__":
    run_margin_erosion_check()
