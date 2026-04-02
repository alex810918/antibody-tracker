"""
fetch_category2.py
Fetches antibody-based drugs currently in active clinical trials
from ClinicalTrials.gov API v2.

Source: https://clinicaltrials.gov/api/v2/studies
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
CT_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Statuses that mean "currently active"
ACTIVE_STATUSES = [
    "RECRUITING",
    "ACTIVE_NOT_RECRUITING",
    "NOT_YET_RECRUITING",
    "ENROLLING_BY_INVITATION",
]

# Antibody-related search query for ClinicalTrials.gov
ANTIBODY_QUERY = (
    "monoclonal antibody OR bispecific antibody OR antibody-drug conjugate "
    "OR ADC OR mAb OR nanobody OR immunoglobulin therapy"
)

PAGE_SIZE = 100  # max allowed by API

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "antibody-tracker/1.0 (research project)"})


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

def fetch_active_trials() -> list[dict]:
    """Page through ClinicalTrials.gov and return all matching study records."""
    all_studies = []
    next_page_token = None

    print("Fetching ClinicalTrials.gov active trials...")

    while True:
        params = {
            "query.intr": ANTIBODY_QUERY,
            "filter.overallStatus": "|".join(ACTIVE_STATUSES),
            "filter.advanced": "AREA[InterventionType]BIOLOGICAL",
            "fields": (
                "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,"
                "LeadSponsorName,Condition,InterventionName,InterventionType,"
                "StartDate,PrimaryCompletionDate"
            ),
            "pageSize": PAGE_SIZE,
            "format": "json",
        }
        if next_page_token:
            params["pageToken"] = next_page_token

        try:
            resp = SESSION.get(CT_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            print(f"  [WARN] ClinicalTrials.gov request failed: {exc}")
            break

        studies = data.get("studies", [])
        all_studies.extend(studies)
        print(f"  Fetched {len(all_studies)} studies so far...")

        next_page_token = data.get("nextPageToken")
        if not next_page_token or not studies:
            break
        time.sleep(0.3)

    return all_studies


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_study(study: dict) -> dict | None:
    """Extract the fields we need from a ClinicalTrials.gov v2 study record."""
    proto = study.get("protocolSection", {})
    id_mod = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    cond_mod = proto.get("conditionsModule", {})
    design_mod = proto.get("designModule", {})
    intr_mod = proto.get("armsInterventionsModule", {})

    nct_id = id_mod.get("nctId", "")
    title = id_mod.get("briefTitle", id_mod.get("officialTitle", ""))
    status = status_mod.get("overallStatus", "")

    # Phase
    phases = design_mod.get("phases", [])
    phase = phases[0] if phases else "Not specified"
    phase = phase.replace("PHASE", "Phase ").strip()

    # Sponsor
    lead = sponsor_mod.get("leadSponsor", {})
    company = lead.get("name", "")

    # Indication (conditions)
    conditions = cond_mod.get("conditions", [])
    indication = "; ".join(conditions[:3])  # top 3 conditions

    # Drug name from interventions
    interventions = intr_mod.get("interventions", [])
    drug_names = [
        i.get("name", "") for i in interventions
        if i.get("type", "").upper() == "BIOLOGICAL"
    ]
    drug_name = "; ".join(drug_names[:2]) if drug_names else title

    return {
        "drug_name": drug_name.strip(),
        "nct_id": nct_id,
        "company": company.strip(),
        "phase": phase,
        "status": status,
        "indication": indication,
        "source": "ClinicalTrials.gov",
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_fetched": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Fetching Category 2: Antibody Drugs in Active Clinical Trials ===")

    raw_studies = fetch_active_trials()
    print(f"Raw studies fetched: {len(raw_studies)}")

    parsed = [parse_study(s) for s in raw_studies]
    parsed = [p for p in parsed if p and p["drug_name"]]

    # Sort by phase descending (Phase 3 first)
    phase_order = {"Phase 3": 0, "Phase 2": 1, "Phase 1": 2, "Phase 4": 3}
    parsed.sort(key=lambda d: phase_order.get(d["phase"], 9))

    print(f"Parsed records: {len(parsed)}")

    out_path = DATA_DIR / "category2.json"
    out_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(parsed)} records -> {out_path}")


if __name__ == "__main__":
    main()
