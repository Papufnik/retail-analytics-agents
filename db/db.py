"""
db.py -- shared SQLite connection helper for the retail analytics
warehouse. One shared module every agent imports, instead of each script
reinventing its own connection/path logic.

Usage:
    from db.db import get_connection
    conn = get_connection()
    cur = conn.execute("SELECT * FROM item_current LIMIT 5")

(Anonymized portfolio version -- in production this sits alongside real
ingestion scripts that populate item_current and cogs_snapshots from POS
and inventory exports on a schedule. Here it points at a small illustrative
sample warehouse built by build_sample_data.py so the three agent scripts
in this repo can run standalone.)
"""

import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "warehouse.sqlite")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

