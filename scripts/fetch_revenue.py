"""
fetch_revenue.py
Enriches category1.json with 2025 product-level revenue from SEC EDGAR filings.

This is a SEPARATE, EXTENSIBLE module. It reads category1.json, looks up each
drug's parent company in SEC EDGAR, then attempts to extract 2025 revenue figures
from 10-K / 10-Q filings.

Source: https://data.sec.gov  (free, no API key required)

Limitations:
  - Only works for US-listed public companies (SEC filers)
  - Product-level revenue is only disclosed when material; many drugs are
    bundled into therapeutic area totals.
  - If not found, the field is set to "Not available from public filings".
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
EDGAR_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={company}&dateRange=custom&startdt=2025-01-01&enddt=2025-12-31&forms=10-K,10-Q"
EDGAR_FULL_TEXT = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
EDGAR_COMPANY_FACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
EDGAR_COMPANY_SEARCH_API = "https://efts.sec.gov/LATEST/search-index?q=%22{name}%22&forms=10-K"

# Well-known company name → SEC ticker overrides (avoids ambiguous searches)
COMPANY_TICKER_MAP = {
    "genentech": "RHHBY",       # Roche subsidiary
    "roche": "RHHBY",
    "abbvie": "ABBV",
    "johnson & johnson": "JNJ",
    "janssen": "JNJ",
    "merck": "MRK",
    "bristol-myers squibb": "BMY",
    "bms": "BMY",
    "pfizer": "PFE",
    "astrazeneca": "AZN",
    "novartis": "NVS",
    "eli lilly": "LLY",
    "lilly": "LLY",
    "amgen": "AMGN",
    "regeneron": "REGN",
    "sanofi": "SNY",
    "biogen": "BIIB",
    "gilead": "GILD",
    "seagen": "SGEN",
    "daiichi sankyo": None,     # Japanese company, EDGAR limited
}

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "antibody-tracker research@example.com",  # EDGAR requires user-agent
    "Accept": "application/json",
})


# ---------------------------------------------------------------------------
# SEC EDGAR lookup
# ---------------------------------------------------------------------------

def search_cik(company_name: str) -> int | None:
    """Find the SEC CIK number for a company by name."""
    # Normalise name
    name_clean = company_name.lower().strip()

    # Check override map first
    ticker = None
    for key, val in COMPANY_TICKER_MAP.items():
        if key in name_clean:
            ticker = val
            break

    if ticker:
        # Resolve ticker → CIK via EDGAR tickers file
        try:
            resp = SESSION.get(
                "https://www.sec.gov/files/company_tickers.json", timeout=15
            )
            resp.raise_for_status()
            tickers = resp.json()
            for entry in tickers.values():
                if entry.get("ticker", "").upper() == ticker.upper():
                    return int(entry["cik_str"])
        except Exception:
            pass

    # Full-text search fallback
    try:
        resp = SESSION.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={"q": f'"{company_name}"', "forms": "10-K"},
            timeout=15,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
        if hits:
            entity = hits[0].get("_source", {}).get("entity_name", "")
            cik_str = hits[0].get("_source", {}).get("file_num", "")
            # Try entity_id field
            eid = hits[0].get("_source", {}).get("entity_id")
            if eid:
                return int(eid)
    except Exception:
        pass

    return None


def get_revenue_from_facts(cik: int, drug_name: str) -> str | None:
    """
    Pull XBRL company facts for the CIK and search for the drug's revenue.
    SEC EDGAR XBRL facts include segment revenue when reported.
    """
    try:
        url = EDGAR_COMPANY_FACTS.format(cik=cik)
        resp = SESSION.get(url, timeout=30)
        resp.raise_for_status()
        facts = resp.json()
    except Exception as exc:
        print(f"    [WARN] EDGAR facts fetch failed for CIK {cik}: {exc}")
        return None

    # Look in us-gaap facts for revenue concepts
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    revenue_concepts = [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
    ]

    drug_lower = drug_name.lower()

    for concept in revenue_concepts:
        if concept not in us_gaap:
            continue
        units = us_gaap[concept].get("units", {})
        usd_entries = units.get("USD", [])

        for entry in usd_entries:
            # Match 2025 annual filings (form 10-K, period ending in 2025)
            if entry.get("form") not in ("10-K", "10-K/A"):
                continue
            period = entry.get("end", "")
            if not period.startswith("2025"):
                continue

            # Check if this entry's label/description mentions the drug
            label = entry.get("accn", "") + " " + str(entry.get("val", ""))
            # XBRL segment data sometimes includes product names in the label
            if drug_lower in label.lower():
                val = entry.get("val", 0)
                return f"${val / 1_000_000:.0f}M (2025, 10-K)"

    return None


def get_revenue_from_filing_text(cik: int, drug_name: str) -> str | None:
    """
    Search the full text of 2025 10-K filings for revenue figures near the drug name.
    Uses EDGAR full-text search.
    """
    try:
        resp = SESSION.get(
            "https://efts.sec.gov/LATEST/search-index",
            params={
                "q": f'"{drug_name}" revenue',
                "dateRange": "custom",
                "startdt": "2025-01-01",
                "enddt": "2025-12-31",
                "forms": "10-K,10-Q",
                "entity": str(cik),
            },
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])
    except Exception:
        return None

    if not hits:
        return None

    # Extract revenue figures from the text snippet
    for hit in hits[:3]:
        snippet = (hit.get("_source", {}).get("file_description") or "") + \
                  (hit.get("highlight", {}).get("file_description", [""])[0] or "")
        # Look for dollar amounts near the drug name
        matches = re.findall(
            r"\$\s*([\d,\.]+)\s*(billion|million|B|M)\b",
            snippet,
            re.IGNORECASE,
        )
        if matches:
            amount_str, unit = matches[0]
            amount = float(amount_str.replace(",", ""))
            if unit.lower() in ("billion", "b"):
                amount *= 1000  # convert to millions
            return f"${amount:.0f}M (2025, SEC filing)"

    return None


# ---------------------------------------------------------------------------
# Main enrichment loop
# ---------------------------------------------------------------------------

def main():
    print("=== Enriching Category 1 with 2025 Revenue (SEC EDGAR) ===")

    cat1_path = DATA_DIR / "category1.json"
    if not cat1_path.exists():
        print("[ERROR] category1.json not found. Run fetch_category1.py first.")
        return

    drugs = json.loads(cat1_path.read_text(encoding="utf-8"))
    print(f"Loaded {len(drugs)} drugs from category1.json")

    # Group by company to avoid redundant CIK lookups
    company_cik_cache: dict[str, int | None] = {}
    updated = 0

    for i, drug in enumerate(drugs):
        company = drug.get("company", "")
        drug_name = drug.get("drug_name", drug.get("inn", ""))

        if not company or not drug_name:
            continue

        print(f"  [{i+1}/{len(drugs)}] {drug_name} ({company})")

        # Lookup CIK (cached)
        if company not in company_cik_cache:
            cik = search_cik(company)
            company_cik_cache[company] = cik
            if cik:
                print(f"    CIK found: {cik}")
            else:
                print(f"    CIK not found for '{company}'")
            time.sleep(0.5)

        cik = company_cik_cache[company]
        if not cik:
            drug["revenue_2025"] = "Not available from public filings"
            continue

        # Try XBRL facts first (structured data)
        revenue = get_revenue_from_facts(cik, drug_name)

        # Fall back to full-text search
        if not revenue:
            revenue = get_revenue_from_filing_text(cik, drug_name)

        drug["revenue_2025"] = revenue or "Not available from public filings"
        if revenue:
            print(f"    Revenue found: {revenue}")
            updated += 1

        time.sleep(0.3)

    # Save enriched data back
    cat1_path.write_text(json.dumps(drugs, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRevenue enrichment complete. {updated}/{len(drugs)} drugs had revenue data.")
    print(f"Saved → {cat1_path}")


if __name__ == "__main__":
    main()
