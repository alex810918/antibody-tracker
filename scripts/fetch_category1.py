"""
fetch_category1.py
Fetches all FDA-approved antibody-based therapeutics from openFDA (BLA applications).

Sources:
  - openFDA drug endpoint: https://api.fda.gov/drug/drugsfda.json
  - FDA Purple Book CSV: https://www.fda.gov/media/89589/download
"""

import json
import time
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"

ANTIBODY_KEYWORDS = [
    "mab", "monoclonal", "antibody", "antibodies",
    "bispecific", "adc", "antibody-drug conjugate",
    "fab", "scfv", "nanobody", "immunoglobulin",
]

ANTIBODY_STEMS = [
    "mab", "ximab", "zumab", "umab", "imab", "tumab", "lumab",
    "mumab", "lizumab", "tuzumab", "xizumab",
]

OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "antibody-tracker/1.0 (research project)"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_antibody(name: str) -> bool:
    name_lower = name.lower()
    if any(kw in name_lower for kw in ANTIBODY_KEYWORDS):
        return True
    if any(name_lower.endswith(stem) for stem in ANTIBODY_STEMS):
        return True
    return False


def safe_get(url: str, params: dict, retries: int = 3) -> dict:
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
            if resp.status_code == 404:
                return {}   # openFDA returns 404 for empty results — not an error
            if resp.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            if attempt == retries - 1:
                print(f"  [WARN] Failed {url}: {exc}")
                return {}
            time.sleep(2)
    return {}


# ---------------------------------------------------------------------------
# openFDA — fetch ALL BLA applications then filter for antibodies
# ---------------------------------------------------------------------------

def fetch_all_bla_products() -> list[dict]:
    """
    Page through ALL BLA (Biologics License Application) submissions in openFDA
    and return the raw result records.
    """
    all_results = []
    skip = 0
    limit = 100

    print("Fetching all BLA applications from openFDA...")
    while True:
        params = {
            "search": "application_number:BLA*",
            "limit": limit,
            "skip": skip,
        }
        data = safe_get(OPENFDA_URL, params)
        if not data:
            break

        results = data.get("results", [])
        if not results:
            break

        all_results.extend(results)
        total = data.get("meta", {}).get("results", {}).get("total", 0)
        print(f"  Fetched {len(all_results)} / {total} BLA records...")

        if len(all_results) >= total or len(results) < limit:
            break
        skip += limit
        time.sleep(0.3)

    return all_results


def parse_bla_records(records: list[dict]) -> list[dict]:
    """Filter BLA records to antibody drugs and normalise fields."""
    drugs = []
    for r in records:
        sponsor = r.get("sponsor_name", "")
        app_num = r.get("application_number", "")
        products = r.get("products", [])

        for p in products:
            brand = p.get("brand_name", "")
            ingredients = p.get("active_ingredients", [])
            inn = ingredients[0].get("name", "") if ingredients else ""

            if not is_antibody(brand) and not is_antibody(inn):
                continue

            # Find original approval date from submissions
            approval_date = ""
            for sub in r.get("submissions", []):
                if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP":
                    approval_date = sub.get("submission_status_date", "")
                    break

            # Patent / exclusivity: use marketing_status as proxy
            mkt_status = p.get("marketing_status", "")
            patent_status = "Active" if "prescription" in mkt_status.lower() else "Unknown"

            drugs.append({
                "drug_name": brand.strip(),
                "inn": inn.strip(),
                "company": sponsor.strip(),
                "approval_date": approval_date,
                "indication": "",   # not reliably in openFDA; populated manually or later
                "patent_status": patent_status,
                "revenue_2025": None,
                "application_number": app_num,
                "source": "openFDA / Drugs@FDA",
                "source_url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_num.replace('BLA', '')}",
                "last_fetched": datetime.utcnow().isoformat() + "Z",
            })

    return drugs


def deduplicate(drugs: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for drug in drugs:
        key = (drug["inn"] or drug["drug_name"]).lower()
        if key not in seen:
            seen[key] = drug
        else:
            existing = seen[key]
            for field in ["indication", "approval_date", "company"]:
                if not existing.get(field) and drug.get(field):
                    existing[field] = drug[field]
    return list(seen.values())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Fetching Category 1: Marketed Antibody Drugs ===")

    raw = fetch_all_bla_products()
    print(f"Total BLA records: {len(raw)}")

    drugs = parse_bla_records(raw)
    drugs = deduplicate(drugs)
    drugs.sort(key=lambda d: d.get("approval_date") or "", reverse=True)

    print(f"Antibody drugs found: {len(drugs)}")

    out_path = DATA_DIR / "category1.json"
    out_path.write_text(json.dumps(drugs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(drugs)} records -> {out_path}")


if __name__ == "__main__":
    main()
