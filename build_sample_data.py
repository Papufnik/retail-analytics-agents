"""
build_sample_data.py -- builds the illustrative SQLite warehouse
(db/warehouse.sqlite) and wholesale-orders.csv these three agent scripts
read from, so a reviewer can clone this repo and run all three end to end
with no real business data required.
"""
import csv
import os
import sqlite3

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "db", "warehouse.sqlite")
SAMPLE_DIR = os.path.join(HERE, "sample_data")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(SAMPLE_DIR, exist_ok=True)

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

conn = sqlite3.connect(DB_PATH)
conn.execute("""
    CREATE TABLE item_current (
        item_id TEXT,
        name TEXT,
        pos_name TEXT,
        sales_category TEXT,
        category TEXT,
        price REAL,
        cost REAL,
        inventory_quantity REAL,
        export_filename TEXT
    )
""")
conn.execute("""
    CREATE TABLE cogs_snapshots (
        item_id TEXT,
        item_name TEXT,
        quantity_sold REAL,
        report_start_date TEXT,
        report_end_date TEXT
    )
""")

# Illustrative catalog: a mix of healthy SKUs, near-stockout SKUs, and
# dead/slow-moving SKUs, so all three agents have something real to find.
items = [
    ("SKU-1001", "Classic Wool Scarf", "Wool Scarf", "Accessories", "Accessories", 42.00, 14.00, 6, "retail_items_export_2026-08-31.csv"),
    ("SKU-1002", "Alpine Trail Beanie", "Trail Beanie", "Accessories", "Accessories", 28.00, 9.50, 3, "retail_items_export_2026-08-31.csv"),
    ("SKU-1003", "Ridge Line Flannel", "Ridge Flannel", "Outerwear", "Outerwear", 68.00, 24.00, 40, "retail_items_export_2026-08-31.csv"),
    ("SKU-1004", "Summit Puffer Vest", "Puffer Vest", "Outerwear", "Outerwear", 96.00, 36.00, 2, "retail_items_export_2026-08-31.csv"),
    ("SKU-1005", "Meadow Sun Hat", "Sun Hat", "Accessories", "Accessories", 24.00, 8.00, 18, "retail_items_export_2026-08-31.csv"),
    ("SKU-2001", "Handforged Belt Buckle", "Belt Buckle", "Jewelry", "Jewelry", 55.00, 19.00, 22, "retail_items_export_2026-08-31.csv"),
    ("SKU-2002", "Turquoise Cuff Bracelet", "Cuff Bracelet", "Jewelry", "Jewelry", 88.00, 31.00, 15, "retail_items_export_2026-08-31.csv"),
    ("SKU-3001", "Trailhead Ceramic Mug", "Ceramic Mug", "Home", "Home", 18.00, 6.00, 60, "retail_items_export_2026-08-31.csv"),
    ("SKU-3002", "Cast Iron Trivet", "Cast Iron Trivet", "Home", "Home", 32.00, 12.00, 14, "retail_items_export_2026-08-31.csv"),
    ("SKU-4001", "Discontinued Print Tee (Old Logo)", "Old Logo Tee", "Apparel", "Apparel", 22.00, 8.00, 34, "retail_items_export_2026-08-31.csv"),
]
conn.executemany(
    "INSERT INTO item_current (item_id, name, pos_name, sales_category, category, price, cost, inventory_quantity, export_filename) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
    items,
)

# COGS window: 2026-04-01 cumulative through 2026-08-04 (matches the
# report_start_date the agents filter on). Sales quantities chosen so that
# SKU-1002/1004 (low stock, high velocity) trip the stockout check, and
# SKU-4001 (in stock, ~zero velocity) trips the markdown check.
cogs = [
    ("SKU-1001", "Classic Wool Scarf", 40, "2026-04-01", "2026-08-04"),
    ("SKU-1002", "Alpine Trail Beanie", 55, "2026-04-01", "2026-08-04"),
    ("SKU-1003", "Ridge Line Flannel", 30, "2026-04-01", "2026-08-04"),
    ("SKU-1004", "Summit Puffer Vest", 48, "2026-04-01", "2026-08-04"),
    ("SKU-1005", "Meadow Sun Hat", 22, "2026-04-01", "2026-08-04"),
    ("SKU-2001", "Handforged Belt Buckle", 10, "2026-04-01", "2026-08-04"),
    ("SKU-2002", "Turquoise Cuff Bracelet", 6, "2026-04-01", "2026-08-04"),
    ("SKU-3001", "Trailhead Ceramic Mug", 90, "2026-04-01", "2026-08-04"),
    ("SKU-3002", "Cast Iron Trivet", 20, "2026-04-01", "2026-08-04"),
    ("SKU-4001", "Discontinued Print Tee (Old Logo)", 0, "2026-04-01", "2026-08-04"),
]
conn.executemany(
    "INSERT INTO cogs_snapshots (item_id, item_name, quantity_sold, report_start_date, report_end_date) "
    "VALUES (?, ?, ?, ?, ?)",
    cogs,
)
conn.commit()
conn.close()
print(f"wrote {DB_PATH}")

# Wholesale marketplace order history -- deliberately includes SKU-1002
# with TWO wholesale prices on record where the price went DOWN over time
# (the exact real-world case margin_erosion_agent.py's header documents
# fixing: an older, cruder version would have kept the higher historical
# price and manufactured a false margin-erosion alert here). Also includes
# SKU-1004 with a genuine price increase, which SHOULD alert.
#
# NOTE: SKU is deliberately left blank on these sample rows so the lookup
# key falls back to Product Name (see load_wholesale_orders()), matched
# against the POS item's own `name` field in run_margin_erosion_check() --
# this is just how the sample data is shaped to demonstrate a real match;
# a production export may or may not populate SKU consistently.
wholesale_rows = [
    {"SKU": "", "Product Name": "Alpine Trail Beanie", "Wholesale Price": "$11.00", "Order Date": "January 14, 2026", "Brand Name": "Alpine Supply Co."},
    {"SKU": "", "Product Name": "Alpine Trail Beanie", "Wholesale Price": "$9.50", "Order Date": "July 02, 2026", "Brand Name": "Alpine Supply Co."},
    {"SKU": "", "Product Name": "Summit Puffer Vest", "Wholesale Price": "$34.00", "Order Date": "February 10, 2026", "Brand Name": "Summit Outfitters"},
    {"SKU": "", "Product Name": "Summit Puffer Vest", "Wholesale Price": "$39.50", "Order Date": "July 18, 2026", "Brand Name": "Summit Outfitters"},
    {"SKU": "", "Product Name": "Classic Wool Scarf", "Wholesale Price": "$14.00", "Order Date": "March 03, 2026", "Brand Name": "Heritage Woolens"},
    {"SKU": "", "Product Name": "Handforged Belt Buckle", "Wholesale Price": "$19.00", "Order Date": "April 21, 2026", "Brand Name": "Ironwood Craft"},
]
csv_path = os.path.join(SAMPLE_DIR, "wholesale-orders.csv")
with open(csv_path, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["SKU", "Product Name", "Wholesale Price", "Order Date", "Brand Name"])
    writer.writeheader()
    writer.writerows(wholesale_rows)
print(f"wrote {csv_path}")

print("\nDONE -- sample warehouse + wholesale order history written.")

