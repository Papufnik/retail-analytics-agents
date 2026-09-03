"""
Shared fixture: builds the illustrative SQLite warehouse (via the repo's
own build_sample_data.py) once per test session, so the end-to-end agent
tests exercise the exact same sample data a reviewer gets from running

    python build_sample_data.py

No real business data is used or required.
"""
import os
import sys
import runpy
import shutil

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)


@pytest.fixture(scope="session", autouse=True)
def sample_warehouse():
    db_dir = os.path.join(REPO_ROOT, "db")
    dash_dir = os.path.join(REPO_ROOT, "dashboard_app")
    sample_dir = os.path.join(REPO_ROOT, "sample_data")

    runpy.run_path(os.path.join(REPO_ROOT, "build_sample_data.py"), run_name="__main__")

    yield

    # dashboard_app/*.json and db/warehouse.sqlite* are gitignored --
    # clean up after the session so a full test run leaves the repo as
    # clean as it found it.
    if os.path.exists(dash_dir):
        shutil.rmtree(dash_dir, ignore_errors=True)
    for fname in ("warehouse.sqlite", "warehouse.sqlite-journal"):
        p = os.path.join(db_dir, fname)
        if os.path.exists(p):
            os.remove(p)
