"""One-shot migration: dedupe financial_cache/analysis_cache and add unique indexes.

Run once after the UniqueConstraint was added to models.py. Safe to re-run.
Usage: python -m scripts.migrate_unique_constraints
"""
import sqlite3
import sys
from pathlib import Path

from backend.config import DATA_DIR

DB_PATH = DATA_DIR / "stocktracing.db"


def migrate():
    if not DB_PATH.exists():
        print(f"[skip] {DB_PATH} not found, nothing to migrate")
        return
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # --- financial_cache: dedupe by (symbol, report_type, fiscal_year, fiscal_quarter) ---
    print("[1/4] dedup financial_cache...")
    cur.execute("""
        DELETE FROM financial_cache
        WHERE id NOT IN (
            SELECT MAX(id) FROM financial_cache
            GROUP BY symbol, report_type, fiscal_year, fiscal_quarter
        )
    """)
    print(f"      removed {cur.rowcount} duplicate rows")

    print("[2/4] create unique index uq_financial_key...")
    cur.execute("DROP INDEX IF EXISTS uq_financial_key")
    cur.execute("DROP INDEX IF EXISTS uq_financial_key_idx")
    try:
        cur.execute("""
            CREATE UNIQUE INDEX uq_financial_key_idx ON financial_cache
            (symbol, report_type, fiscal_year, fiscal_quarter)
        """)
        print("      created uq_financial_key_idx")
    except sqlite3.IntegrityError as e:
        print(f"      [warn] {e}")

    # --- analysis_cache: dedupe by (symbol, analysis_type) ---
    print("[3/4] dedup analysis_cache...")
    cur.execute("""
        DELETE FROM analysis_cache
        WHERE id NOT IN (
            SELECT MAX(id) FROM analysis_cache
            GROUP BY symbol, analysis_type
        )
    """)
    print(f"      removed {cur.rowcount} duplicate rows")

    print("[4/4] create unique index uq_analysis_key...")
    cur.execute("DROP INDEX IF EXISTS uq_analysis_key")
    cur.execute("DROP INDEX IF EXISTS uq_analysis_key_idx")
    try:
        cur.execute("""
            CREATE UNIQUE INDEX uq_analysis_key_idx ON analysis_cache
            (symbol, analysis_type)
        """)
        print("      created uq_analysis_key_idx")
    except sqlite3.IntegrityError as e:
        print(f"      [warn] {e}")

    conn.commit()
    conn.close()
    print("[done] migration complete")


if __name__ == "__main__":
    migrate()
