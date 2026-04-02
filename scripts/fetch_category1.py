"""
fetch_category1.py
Fetches all FDA-approved antibody-based therapeutics from the FDA Purple Book
(biologics license applications) and Drugs@FDA API.

Sources:
  - FDA Purple Book: https://purplebooksearch.fda.gov/
  - openFDA drug endpoint: https://api.fda.gov/drug/drugsfda.json
"""

import json
import re
import time
from datetime import datetime
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = Path(__file__).parent.parent / "data"

# Keywords that identify antibody-based biologics in product name / ingredient
ANTIBODY_KEYWORDS = [
    "mab", "monoclonal", "antibody", "antibodies",
    "bispecific", "adc", "antibody-drug conjugate",
    "fab", "scfv", "nanobody", "immunoglobulin",
    "bevacizumab", "trastuzumab",  # catch well-known stems
]

# INN stems that identify monoclonal antibodies (WHO nomenclature)
ANTIBODY_STEMS = [
    "mab", "ximab", "zumab", "umab", "imab", "tumab", "lumab",
    "mumab", "nab", "lizumab", "ximab",
]

OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
PURPLE_BOOK_URL = "https://purplebooksearch.fda.gov/api/v1/drugs"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "antibody-tracker/1.0 (research project)"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_antibody(name: str) -> bool:
    """Return True if the drug name looks like an antibody therapeutic."""
    name_lower = name.lower()
    if any(kw in name_lower for kw in ANTIBODY_KEYWORDS):
        return True
    # Check INN stem (last 3–6 chars)
    if any(name_lower.endswith(stem) for stem in ANTIBODY_STEMS):
        return True
    return False


def safe_get(url: str, params: dict, retries: int = 3) -> dict:
    """GET with simple retry and rate-limit back-off."""
    for attempt in range(retries):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
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
# Purple Book fetch  (primary: FDA biologics database)
# ---------------------------------------------------------------------------

def fetch_purple_book() -> list[dict]:
    """
    Query the FDA Purple Book search API for biologics.
    Returns a list of raw product records.
    """
    records = []
    page = 1
    page_size = 100

    print("Fetching FDA Purple Book...")
    while True:
        data = safe_get(PURPLE_BOOK_URL, {"page": page, "pageSize": page_size})
        if not data:
            break

        items = data.get("data", data.get("results", []))
        if not items:
            break

        records.extend(items)
        total = data.get("totalCount", data.get("total", 0))
        print(f"  Page {page}: {len(items)} records (total so far: {len(records)} / {total})")

        if len(records) >= total or len(items) < page_size:
            break
        page += 1
        time.sleep(0.5)  # be polite

    return records


def parse_purple_book(records: list[dict]) -> list[dict]:
    """Filter and normalise Purple Book records to antibody drugs."""
    drugs = []
    for r in records:
        # Purple Book field names vary — try common variants
        name = (
            r.get("proprietaryName") or r.get("brandName") or
            r.get("productName") or r.get("ProprietaryName") or ""
        )
        inn = (
            r.get("nonproprietaryName") or r.get("inn") or
            r.get("activeIngredient") or r.get("NonproprietaryName") or ""
        )

        if not is_antibody(name) and not is_antibody(inn):
            continue

        approval_date = (
            r.get("approvalDate") or r.get("ApprovalDate") or
            r.get("originalApprovalDate") or ""
        )
        company = (
            r.get("applicantFullName") or r.get("applicant") or
            r.get("Applicant") or r.get("sponsor") or ""
        )
        indication = r.get("indication") or r.get("Indication") or ""
        patent_status = _parse_patent_status(r)

        drugs.append({
            "drug_name": name.strip(),
            "inn": inn.strip(),
            "company": company.strip(),
            "approval_date": approval_date,
            "indication": indication.strip(),
            "patent_status": patent_status,
            "revenue_2025": None,  # populated later by fetch_revenue.py
            "source": "FDA Purple Book",
            "last_fetched": datetime.utcnow().isoformat() + "Z",
        })
    return drugs


def _parse_patent_status(record: dict) -> str:
    """Derive a simple Active / Expired string from patent fields."""
    expiry = (
        record.get("patentExpirationDate") or
        record.get("patentExpiry") or
        record.get("exclusivityDate") or ""
    )
    if not expiry:
        return "Unknown"
    try:
        exp_date = datetime.strptime(expiry[:10], "%Y-%m-%d")
        return "Expired" if exp_date < datetime.utcnow() else "Active"
    except ValueError:
        return expiry  # return raw value if unparseable


# ---------------------------------------------------------------------------
# openFDA fallback / supplement
# ---------------------------------------------------------------------------

def fetch_openfda_antibodies() -> list[dict]:
    """
    Supplement with openFDA drug@FDA endpoint.
    Searches BLA application type with antibody keyword in product name.
    """
    drugs = []
    search_terms = ["mab", "monoclonal+antibody", "bispecific", "antibody-drug+conjugate"]

    for term in search_terms:
        params = {
            "search": f'application_number:"BLA"+AND+openfda.brand_name:"{term}"',
            "limit": 100,
        }
        data = safe_get(OPENFDA_URL, params)
        results = data.get("results", [])
        print(f"  openFDA '{term}': {len(results)} results")

        for r in results:
            products = r.get("products", [{}])
            p = products[0] if products else {}
            brand = p.get("brand_name", "")
            inn = p.get("active_ingredients", [{}])[0].get("name", "") if p.get("active_ingredients") else ""

            if not is_antibody(brand) and not is_antibody(inn):
                continue

            sponsor = r.get("sponsor_name", "")
            app_num = r.get("application_number", "")
            submissions = r.get("submissions", [])
            approval_date = ""
            for sub in submissions:
                if sub.get("submission_type") == "ORIG" and sub.get("submission_status") == "AP":
                    approval_date = sub.get("submission_status_date", "")
                    break

            drugs.append({
                "drug_name": brand.strip(),
                "inn": inn.strip(),
                "company": sponsor.strip(),
                "approval_date": approval_date,
                "indication": "",  # not reliably available in openFDA
                "patent_status": "Unknown",
                "revenue_2025": None,
                "application_number": app_num,
                "source": "openFDA / Drugs@FDA",
                "last_fetched": datetime.utcnow().isoformat() + "Z",
            })
        time.sleep(0.3)

    return drugs


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

def deduplicate(drugs: list[dict]) -> list[dict]:
    """Merge records with the same INN, preferring Purple Book data."""
    seen: dict[str, dict] = {}
    for drug in drugs:
        key = drug["inn"].lower() or drug["drug_name"].lower()
        if key not in seen:
            seen[key] = drug
        else:
            # Keep existing (Purple Book preferred) but fill missing fields
            existing = seen[key]
            for field in ["indication", "approval_date", "patent_status", "company"]:
                if not existing.get(field) and drug.get(field):
                    existing[field] = drug[field]
    return list(seen.values())


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Fetching Category 1: Marketed Antibody Drugs ===")

    # 1. FDA Purple Book (primary)
    raw = fetch_purple_book()
    drugs = parse_purple_book(raw)
    print(f"Purple Book antibodies found: {len(drugs)}")

    # 2. openFDA supplement
    openfda_drugs = fetch_openfda_antibodies()
    print(f"openFDA antibodies found: {len(openfda_drugs)}")

    # 3. Merge & deduplicate
    all_drugs = deduplicate(drugs + openfda_drugs)
    all_drugs.sort(key=lambda d: d.get("approval_date") or "", reverse=True)
    print(f"Total unique antibody drugs after dedup: {len(all_drugs)}")

    # 4. Save
    out_path = DATA_DIR / "category1.json"
    out_path.write_text(json.dumps(all_drugs, indent=2, ensure_ascii=False))
    print(f"Saved {len(all_drugs)} records → {out_path}")


if __name__ == "__main__":
    main()
