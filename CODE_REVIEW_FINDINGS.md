# Code Review Findings — Antibody Tracker

Reviewed on: 2026-04-03  
Reviewer: Claude Code (code-reviewer skill)  
Scope: All Python scripts, app.js, GitHub Actions workflow

---

## Priority Summary

| # | Severity | File | Issue |
|---|---|---|---|
| 1 | Medium | `app.js:152` | XSS: badge `val` not escaped |
| 2 | Low | `app.js:132` | XSS: NCT link text not escaped |
| 3 | Low | `app.js:139` | XSS: `source_url` href not escaped |
| 4 | Low | `fetch_category1.py:137` | `patent_status` never returns "Expired" |
| 5 | Low | `app.js:318` | Error message only shown on cat1 panel |
| 6 | Low | `update_all.py:55` | Missing `encoding="utf-8"` |
| 7 | Info | `fetch_revenue.py:31–35` | 3 unused constants |

---

## Security Issues

### Issue 1 — XSS in badge rendering (Medium)
**File:** `app.js`  
**Lines:** 152–158 (badge `"failure"`), also 145–150 (badge `"phase"` and `"patent"`)

`val` is interpolated directly into HTML without HTML-escaping:

```js
// Current (unsafe)
return `<span class="badge ${cls}">${val || "—"}</span>`;

// Fix: wrap val with escapeHtml()
return `<span class="badge ${cls}">${escapeHtml(String(val || "—"))}</span>`;
```

**Applies to all three badge types:** `"phase"` (line 146), `"patent"` (line 148), `"failure"` (line 152).  
`escapeHtml()` is already defined in the file at line 172 — just needs to be called here.

---

### Issue 2 — XSS in NCT ID link display text (Low)
**File:** `app.js`  
**Line:** 132

The displayed text `val` is not escaped:

```js
// Current (unsafe)
return `<a class="source-link" href="https://clinicaltrials.gov/study/${val}" target="_blank" rel="noopener">${val}</a>`;

// Fix: escape both the href path segment and the display text
return `<a class="source-link" href="https://clinicaltrials.gov/study/${escapeHtml(val)}" target="_blank" rel="noopener">${escapeHtml(val)}</a>`;
```

---

### Issue 3 — Unescaped `source_url` in href attribute (Low)
**File:** `app.js`  
**Line:** 139

`url` comes from `row.source_url` (JSON data) and is placed directly into an `href` attribute without escaping:

```js
// Current (unsafe)
return `<a class="source-link" href="${url}" target="_blank" rel="noopener">${val || "Source"}</a>`;

// Fix: escape both the href and the display text
return `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(String(val || "Source"))}</a>`;
```

---

## Bugs

### Issue 4 — `patent_status` never produces "Expired" (Low)
**File:** `scripts/fetch_category1.py`  
**Line:** 137

```python
# Current — only outputs "Active" or "Unknown", never "Expired"
patent_status = "Active" if "prescription" in mkt_status.lower() else "Unknown"
```

`app.js:149` has a badge style for `"Expired"` that will never be used. This is a known data limitation (openFDA doesn't expose patent expiry dates), but the dead badge code in `app.js` should either be removed or a comment added to explain why "Expired" is intentionally unreachable.

**Suggested fix:** Add a comment in `app.js` near the `"Expired"` badge branch explaining the limitation, or remove the `"Expired"` branch entirely since it is never reached.

---

### Issue 5 — Error fallback message hardcoded to `table-cat1` (Low)
**File:** `app.js`  
**Line:** 318

```js
// Current — only cat1 panel shows the error; cat2 and cat3 panels are blank
document.getElementById("table-cat1").innerHTML =
  '<p class="error-msg">Failed to load data...</p>';

// Fix — show the error on all tab panels
TABS.forEach(tab => {
  const el = document.getElementById(`table-${tab.id}`);
  if (el) el.innerHTML = '<p class="error-msg">Failed to load data. Make sure to open this site via a web server, not directly as a local file.</p>';
});
```

---

### Issue 6 — Missing `encoding="utf-8"` in `write_last_updated()` (Low)
**File:** `scripts/update_all.py`  
**Line:** 55

```python
# Current — no encoding specified (uses system default on Windows)
path.write_text(json.dumps({"last_updated": now}, indent=2))

# Fix — consistent with all other file writes in the project
path.write_text(json.dumps({"last_updated": now}, indent=2), encoding="utf-8")
```

---

## Dead Code

### Issue 7 — Unused constants in `fetch_revenue.py` (Info)
**File:** `scripts/fetch_revenue.py`  
**Lines:** 31–35

The following three constants are defined but never referenced anywhere in the file:

```python
EDGAR_COMPANY_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={company}&..."  # line 31 — also has a broken {company} placeholder
EDGAR_SUBMISSIONS    = "https://data.sec.gov/submissions/CIK{cik:010d}.json"        # line 33
EDGAR_COMPANY_SEARCH_API = "https://efts.sec.gov/LATEST/search-index?q=%22{name}%22&forms=10-K"  # line 35
```

**Fix:** Delete all three lines.

---

## Minor Observations (no fix required)

- **`fetch_category2.py:94`** — `parse_study()` is annotated `-> dict | None` but never returns `None`. The caller's `None` filter is harmless. Can leave as-is.
- **`fetch_category3.py:186`** — `fetch_fda_rejections()` handles the 404-means-no-results case via a blanket `except Exception` rather than checking the status code explicitly like `safe_get()` does. Works correctly but is inconsistent style.
- **`app.js:165–166`** — `phaseBadgeClass()` checks for roman numerals (`"iii"`, `"ii"`, `"i"`, `"iv"`) but the Python normalization only ever produces `"Phase 1"` / `"Phase 2"` / `"Phase 3"` format. The roman numeral branches are unreachable but harmless.
