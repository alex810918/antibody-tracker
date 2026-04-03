# Changelog

## v1.1.0 — 2026-04-03

### Bug Fixes
- **Failed Programs — Drug Name** (`fetch_category3.py`): Drug name now falls back to any intervention name instead of the full study title, which was showing long protocol titles instead of the actual drug name.
- **Failed Programs — Failure Type** (`fetch_category3.py`): Replaced inaccurate keyword-guessing classification with the authoritative ClinicalTrials.gov recruitment status. Values are now `Terminated`, `Withdrawn`, or `Suspended`.
- **Failed Programs — Suspended studies** (`fetch_category3.py`): Added `SUSPENDED` to the fetched study statuses so suspended programs now appear in the tab.
- **Marketed Drugs — 2025 Revenue** (`app.js`, `update_all.py`): Removed the Revenue column and the `fetch_revenue` pipeline step. SEC EDGAR product-level revenue lookup had a 0% hit rate across all drugs and is removed until a better data source is available.

### New Features
- **Marketed Drugs — BLA column** (`app.js`): Added a `BLA` column displaying the FDA Biologics License Application number for each marketed drug.
- **Marketed Drugs — Indication** (`fetch_category1.py`): Indication is now auto-populated by querying the openFDA drug label endpoint (`/drug/label.json`) using each drug's BLA number. Returns the first sentence of the FDA-approved indication text.
- **Weekly auto-update** (`update-data.yml`): Changed GitHub Actions schedule from the 1st and 15th of each month to every Monday at 6:00 AM UTC.
- **Email notification** (`update-data.yml`): After each weekly run, an email is sent to syuanting918@gmail.com with the job status and a link to the site. Requires `GMAIL_APP_PASSWORD` set as a GitHub repository secret.

### Security Fixes
- **XSS in badge rendering** (`app.js`): All badge columns (phase, patent status, failure type) now HTML-escape values before rendering.
- **XSS in NCT ID links** (`app.js`): NCT ID display text and href are now HTML-escaped.
- **XSS in source URL links** (`app.js`): `source_url` href values are now HTML-escaped.
- **Error message visibility** (`app.js`): On data load failure, the error message now appears on all three tab panels instead of only the first tab.

### Code Quality
- **`update_all.py`**: Added `encoding="utf-8"` to `write_last_updated()` for consistency with all other file writes.
- **`fetch_revenue.py`**: Removed three unused constants (`EDGAR_COMPANY_SEARCH`, `EDGAR_SUBMISSIONS`, `EDGAR_COMPANY_SEARCH_API`).
- **`style.css`**: Replaced old failure badge classes with `badge-terminated` (red), `badge-withdrawn` (orange), `badge-suspended` (yellow) to match the new failure type values.
- **`index.html`**: Removed SEC EDGAR from footer data sources since revenue enrichment is no longer part of the pipeline.

---

## v1.0.0 — 2026-03-01

Initial release. Three-tab website tracking:
- **Marketed Drugs** — FDA-approved antibody therapeutics via openFDA BLA records
- **In Clinical Trials** — Active antibody studies from ClinicalTrials.gov API v2
- **Failed Programs** — Terminated/withdrawn antibody studies (2021–2026) from ClinicalTrials.gov
