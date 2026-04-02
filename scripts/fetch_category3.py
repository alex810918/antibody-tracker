"""
fetch_category3.py
Fetches antibody-based drugs that failed clinical trials between 2021–2026.
Covers both sponsor withdrawals (TERMINATED/WITHDRAWN) and FDA rejections (CRL).

Sources:
  - ClinicalTrials.gov API v2 (terminated/withdrawn studies)
  - openFDA (Complete Response Letters / BLA refusals)
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
OPENFDA_URL = "https://api.fda.gov/drug/drugsfda.json"

FAILURE_STATUSES = ["TERMINATED", "WITHDRAWN"]
FAILURE_YEAR_START = 2021
FAILURE_YEAR_END = 2026

ANTIBODY_QUERY = (
    "monoclonal antibody OR bispecific antibody OR antibody-drug conjugate "
    "OR ADC OR mAb OR nanobody OR immunoglobulin therapy"
)

PAGE_SIZE = 100

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "antibody-tracker/1.0 (research project)"})


# ---------------------------------------------------------------------------
# ClinicalTrials.gov — terminated/withdrawn studies
# ---------------------------------------------------------------------------

def fetch_failed_trials() -> list[dict]:
    """Fetch TERMINATED and WITHDRAWN antibody studies from 2021–2026."""
    all_studies = []
    next_page_token = None

    print("Fetching ClinicalTrials.gov failed/withdrawn trials...")

    while True:
        params = {
            "query.intr": ANTIBODY_QUERY,
            "filter.overallStatus": "|".join(FAILURE_STATUSES),
            "fields": (
                "NCTId,BriefTitle,OfficialTitle,OverallStatus,Phase,"
                "LeadSponsorName,Condition,InterventionName,InterventionType,"
                "WhyStopped,StartDate,CompletionDate,LastUpdatePostDate"
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


def _classify_reason(why_stopped: str, status: str) -> tuple[str, str]:
    """
    Returns (failure_type, reason) based on why_stopped text and status.
    failure_type: 'Sponsor withdrawal' | 'FDA rejection (CRL)' | 'Unknown'
    """
    if not why_stopped:
        return "Sponsor withdrawal" if status == "WITHDRAWN" else "Unknown", \
               "Reason not publicly disclosed"

    ws_lower = why_stopped.lower()

    # FDA-related keywords
    if any(kw in ws_lower for kw in ["fda", "crl", "complete response", "refuse to file",
                                      "rtf", "regulatory", "agency"]):
        return "FDA rejection (CRL)", why_stopped

    # Safety signals
    if any(kw in ws_lower for kw in ["safety", "adverse", "toxicity", "death", "serious"]):
        return "Sponsor withdrawal", f"Safety concerns: {why_stopped}"

    # Efficacy
    if any(kw in ws_lower for kw in ["efficacy", "futility", "interim analysis",
                                      "did not meet", "failed to", "lack of"]):
        return "Sponsor withdrawal", f"Efficacy failure: {why_stopped}"

    # Business
    if any(kw in ws_lower for kw in ["business", "financial", "funding", "commercial",
                                      "strategic", "portfolio"]):
        return "Sponsor withdrawal", f"Business decision: {why_stopped}"

    # Enrollment
    if any(kw in ws_lower for kw in ["enroll", "recruitment", "accrual", "feasibility"]):
        return "Sponsor withdrawal", f"Enrollment issues: {why_stopped}"

    return "Sponsor withdrawal", why_stopped


def parse_failed_study(study: dict) -> dict | None:
    """Extract fields from a terminated/withdrawn ClinicalTrials.gov study."""
    proto = study.get("protocolSection", {})
    id_mod = proto.get("identificationModule", {})
    status_mod = proto.get("statusModule", {})
    sponsor_mod = proto.get("sponsorCollaboratorsModule", {})
    cond_mod = proto.get("conditionsModule", {})
    design_mod = proto.get("designModule", {})
    intr_mod = proto.get("armsInterventionsModule", {})

    nct_id = id_mod.get("nctId", "")
    status = status_mod.get("overallStatus", "")
    why_stopped = status_mod.get("whyStopped", "")

    # Filter by date range
    last_update = status_mod.get("lastUpdatePostDateStruct", {}).get("date", "")
    if last_update:
        try:
            year = int(last_update[:4])
            if not (FAILURE_YEAR_START <= year <= FAILURE_YEAR_END):
                return None
        except (ValueError, TypeError):
            pass

    phases = design_mod.get("phases", [])
    phase = phases[0] if phases else "Not specified"
    phase = phase.replace("PHASE", "Phase ").strip()

    lead = sponsor_mod.get("leadSponsor", {})
    company = lead.get("name", "")

    conditions = cond_mod.get("conditions", [])
    indication = "; ".join(conditions[:3])

    interventions = intr_mod.get("interventions", [])
    drug_names = [
        i.get("name", "") for i in interventions
        if i.get("type", "").upper() == "BIOLOGICAL"
    ]
    title = id_mod.get("briefTitle", id_mod.get("officialTitle", ""))
    drug_name = "; ".join(drug_names[:2]) if drug_names else title

    failure_type, reason = _classify_reason(why_stopped, status)

    return {
        "drug_name": drug_name.strip(),
        "nct_id": nct_id,
        "company": company.strip(),
        "failure_stage": phase,
        "failure_type": failure_type,
        "reason": reason or "Reason not publicly disclosed",
        "indication": indication,
        "source": "ClinicalTrials.gov",
        "source_url": f"https://clinicaltrials.gov/study/{nct_id}",
        "last_fetched": datetime.utcnow().isoformat() + "Z",
    }


# ---------------------------------------------------------------------------
# openFDA — Complete Response Letters (FDA rejections)
# ---------------------------------------------------------------------------

def fetch_fda_rejections() -> list[dict]:
    """
    Fetch BLA submissions with action_type = 'CRL' (Complete Response Letter)
    from openFDA to supplement with formal FDA rejections.
    """
    rejections = []
    params = {
        "search": "application_number:BLA* AND submissions.action_type:CRL",
        "limit": 100,
    }

    print("Fetching FDA Complete Response Letters (CRL)...")
    try:
        resp = SESSION.get(OPENFDA_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  [WARN] openFDA CRL fetch failed: {exc}")
        return []

    for r in data.get("results", []):
        products = r.get("products", [{}])
        p = products[0] if products else {}
        brand = p.get("brand_name", "")
        inn_list = p.get("active_ingredients", [])
        inn = inn_list[0].get("name", "") if inn_list else ""

        sponsor = r.get("sponsor_name", "")
        app_num = r.get("application_number", "")

        # Find CRL submission details
        for sub in r.get("submissions", []):
            if sub.get("action_type") != "CRL":
                continue
            sub_date = sub.get("submission_status_date", "")
            try:
                year = int(sub_date[:4])
                if not (FAILURE_YEAR_START <= year <= FAILURE_YEAR_END):
                    continue
            except (ValueError, TypeError):
                continue

            rejections.append({
                "drug_name": brand.strip(),
                "inn": inn.strip(),
                "nct_id": "",
                "company": sponsor.strip(),
                "failure_stage": "BLA Submission",
                "failure_type": "FDA rejection (CRL)",
                "reason": "Complete Response Letter issued by FDA",
                "indication": "",
                "application_number": app_num,
                "source": "openFDA / Drugs@FDA",
                "source_url": f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_num.replace('BLA', '')}",
                "last_fetched": datetime.utcnow().isoformat() + "Z",
            })

    print(f"  FDA CRL records found: {len(rejections)}")
    return rejections


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=== Fetching Category 3: Failed Antibody Programs (2021–2026) ===")

    # 1. Terminated/withdrawn from ClinicalTrials.gov
    raw_studies = fetch_failed_trials()
    print(f"Raw terminated/withdrawn studies: {len(raw_studies)}")

    parsed_trials = [parse_failed_study(s) for s in raw_studies]
    parsed_trials = [p for p in parsed_trials if p and p["drug_name"]]
    print(f"Parsed trial failures: {len(parsed_trials)}")

    # 2. FDA Complete Response Letters
    fda_rejections = fetch_fda_rejections()

    # 3. Combine
    all_failures = parsed_trials + fda_rejections

    # Sort by failure_type (FDA rejections first), then drug name
    all_failures.sort(key=lambda d: (
        0 if d["failure_type"] == "FDA rejection (CRL)" else 1,
        d["drug_name"]
    ))

    print(f"Total failure records: {len(all_failures)}")

    out_path = DATA_DIR / "category3.json"
    out_path.write_text(json.dumps(all_failures, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {len(all_failures)} records -> {out_path}")


if __name__ == "__main__":
    main()
