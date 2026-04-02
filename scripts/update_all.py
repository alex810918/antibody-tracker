"""
update_all.py
Orchestrator script — runs all data fetching scripts in order and records
the last-updated timestamp.

To add a new data source in the future:
  1. Create a new script in scripts/  (e.g., fetch_category4.py)
  2. Add it to the SCRIPTS list below
  3. That's it — GitHub Actions will pick it up automatically
"""

import importlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Script pipeline — edit this list to add/remove/reorder data sources
# ---------------------------------------------------------------------------

SCRIPTS = [
    "fetch_category1",   # FDA Purple Book → data/category1.json
    "fetch_category2",   # ClinicalTrials.gov active → data/category2.json
    "fetch_category3",   # ClinicalTrials.gov failed → data/category3.json
    "fetch_revenue",     # SEC EDGAR → enriches category1.json with 2025 revenue
]

DATA_DIR = Path(__file__).parent.parent / "data"

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_script(name: str) -> bool:
    """Dynamically import and run a script's main() function."""
    print(f"\n{'='*60}")
    print(f"  Running: {name}")
    print(f"{'='*60}")
    try:
        mod = importlib.import_module(name)
        mod.main()
        return True
    except Exception as exc:
        print(f"\n[ERROR] {name} failed: {exc}")
        import traceback
        traceback.print_exc()
        return False


def write_last_updated():
    """Write the current UTC timestamp to data/last_updated.json."""
    now = datetime.now(timezone.utc).isoformat()
    path = DATA_DIR / "last_updated.json"
    path.write_text(json.dumps({"last_updated": now}, indent=2))
    print(f"\nTimestamp written: {now}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("Antibody Tracker — Data Update Pipeline")
    print(f"Started at: {datetime.now(timezone.utc).isoformat()}")

    failures = []
    for script_name in SCRIPTS:
        success = run_script(script_name)
        if not success:
            failures.append(script_name)

    write_last_updated()

    if failures:
        print(f"\n[WARN] The following scripts failed: {', '.join(failures)}")
        print("Partial data may have been saved. Check logs above for details.")
        sys.exit(1)  # non-zero exit so GitHub Actions marks the run as failed
    else:
        print("\nAll scripts completed successfully.")


if __name__ == "__main__":
    # Ensure scripts directory is on the path so imports work
    import os
    scripts_dir = Path(__file__).parent
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    main()
