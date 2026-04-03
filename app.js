/**
 * app.js — Antibody Drug Tracker
 * Loads JSON data files, renders filterable/sortable tables for each category.
 *
 * Extensibility: to add a new tab, add an entry to TABS below and create
 * the corresponding JSON file + HTML tab button/panel.
 */

// ============================================================
// Tab configuration
// Each entry drives both the data loaded and the columns rendered.
// ============================================================
const TABS = [
  {
    id: "cat1",
    dataFile: "data/category1.json",
    columns: [
      { key: "drug_name",         label: "Drug Name",     sortable: true },
      { key: "inn",               label: "INN",            sortable: true },
      { key: "application_number", label: "BLA",           sortable: true },
      { key: "company",           label: "Company",        sortable: true,  filter: true },
      { key: "approval_date",     label: "Approval Date",  sortable: true },
      { key: "indication",        label: "Indication",     sortable: false },
      { key: "patent_status",     label: "Patent Status",  sortable: true,  filter: true, badge: "patent" },
      { key: "source",            label: "Source",         sortable: false, sourceCol: true },
    ],
  },
  {
    id: "cat2",
    dataFile: "data/category2.json",
    columns: [
      { key: "drug_name",  label: "Drug Name",    sortable: true },
      { key: "company",    label: "Sponsor",      sortable: true,  filter: true },
      { key: "phase",      label: "Phase",        sortable: true,  filter: true, badge: "phase" },
      { key: "status",     label: "Status",       sortable: true,  filter: true },
      { key: "indication", label: "Indication",   sortable: false },
      { key: "nct_id",     label: "NCT ID",       sortable: false, nctLink: true },
      { key: "source",     label: "Source",       sortable: false, sourceCol: true },
    ],
  },
  {
    id: "cat3",
    dataFile: "data/category3.json",
    columns: [
      { key: "drug_name",     label: "Drug Name",      sortable: true },
      { key: "company",       label: "Sponsor",        sortable: true,  filter: true },
      { key: "failure_stage", label: "Failure Stage",  sortable: true,  filter: true, badge: "phase" },
      { key: "failure_type",  label: "Failure Type",   sortable: true,  filter: true, badge: "failure" },
      { key: "reason",        label: "Reason",         sortable: false },
      { key: "indication",    label: "Indication",     sortable: false },
      { key: "nct_id",        label: "NCT ID",         sortable: false, nctLink: true },
      { key: "source",        label: "Source",         sortable: false, sourceCol: true },
    ],
  },
];

// ============================================================
// State
// ============================================================
const state = {
  data:       {},   // { cat1: [...], cat2: [...], cat3: [...] }
  filtered:   {},   // { cat1: [...], ... }  after search/filter
  sort:       {},   // { cat1: { key, dir }, ... }
  activeTab:  "cat1",
};

// ============================================================
// Data loading
// ============================================================
async function loadAll() {
  const [lastUpdated, ...dataResults] = await Promise.all([
    fetch("data/last_updated.json").then(r => r.json()).catch(() => ({})),
    ...TABS.map(t => fetch(t.dataFile).then(r => r.json()).catch(() => [])),
  ]);

  TABS.forEach((tab, i) => {
    state.data[tab.id]     = dataResults[i] || [];
    state.filtered[tab.id] = state.data[tab.id];
    state.sort[tab.id]     = { key: null, dir: "asc" };
  });

  renderLastUpdated(lastUpdated.last_updated);
  TABS.forEach(tab => populateFilters(tab));
  renderActiveTab();
  updateTabCounts();
}

// ============================================================
// Rendering
// ============================================================
function renderActiveTab() {
  const tab = TABS.find(t => t.id === state.activeTab);
  if (!tab) return;
  renderTable(tab, state.filtered[tab.id]);
}

function renderTable(tab, rows) {
  const container = document.getElementById(`table-${tab.id}`);
  if (!container) return;

  if (!rows || rows.length === 0) {
    container.innerHTML = '<p class="no-data">No records found.</p>';
    updateCount(tab.id, 0);
    return;
  }

  const sort = state.sort[tab.id];

  const thead = `<thead><tr>${tab.columns.map(col => {
    const sortClass = sort.key === col.key
      ? `sorted-${sort.dir}`
      : "";
    const sortAttr = col.sortable
      ? `onclick="toggleSort('${tab.id}','${col.key}')" title="Sort by ${col.label}"`
      : "";
    return `<th class="${sortClass}" ${sortAttr}>${col.label}<span class="sort-icon"></span></th>`;
  }).join("")}</tr></thead>`;

  const tbody = `<tbody>${rows.map(row => `<tr>${tab.columns.map(col =>
    `<td>${renderCell(col, row)}</td>`
  ).join("")}</tr>`).join("")}</tbody>`;

  container.innerHTML = `<div class="table-wrap"><table>${thead}${tbody}</table></div>`;
  updateCount(tab.id, rows.length);
}

function renderCell(col, row) {
  const val = row[col.key] ?? "";

  // NCT ID → link to ClinicalTrials.gov
  if (col.nctLink && val) {
    return `<a class="source-link" href="https://clinicaltrials.gov/study/${escapeHtml(val)}" target="_blank" rel="noopener">${escapeHtml(val)}</a>`;
  }

  // Source column
  if (col.sourceCol) {
    const url = row.source_url || "";
    if (url) {
      return `<a class="source-link" href="${escapeHtml(url)}" target="_blank" rel="noopener">${escapeHtml(String(val || "Source"))}</a>`;
    }
    return `<span class="source-label">${escapeHtml(String(val))}</span>`;
  }

  // Badge columns
  if (col.badge === "phase") {
    return `<span class="badge ${phaseBadgeClass(val)}">${escapeHtml(String(val || "—"))}</span>`;
  }
  if (col.badge === "patent") {
    const cls = val === "Active" ? "badge-active" : "badge-unknown";
    return `<span class="badge ${cls}">${escapeHtml(String(val || "Unknown"))}</span>`;
  }
  if (col.badge === "failure") {
    const cls = val === "Terminated" ? "badge-terminated"
              : val === "Withdrawn"  ? "badge-withdrawn"
              : val === "Suspended"  ? "badge-suspended"
              : "badge-unknown-fail";
    return `<span class="badge ${cls}">${escapeHtml(String(val || "—"))}</span>`;
  }

  return escapeHtml(String(val || "—"));
}

function phaseBadgeClass(phase) {
  if (!phase) return "badge-unknown";
  const p = phase.toLowerCase();
  if (p.includes("3") || p.includes("iii")) return "badge-phase3";
  if (p.includes("2") || p.includes("ii"))  return "badge-phase2";
  if (p.includes("1") || p.includes("i"))   return "badge-phase1";
  if (p.includes("4") || p.includes("iv"))  return "badge-phase4";
  return "badge-unknown";
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ============================================================
// Sorting
// ============================================================
function toggleSort(tabId, key) {
  const s = state.sort[tabId];
  if (s.key === key) {
    s.dir = s.dir === "asc" ? "desc" : "asc";
  } else {
    s.key = key;
    s.dir = "asc";
  }
  applySort(tabId);
  renderActiveTab();
}

function applySort(tabId) {
  const { key, dir } = state.sort[tabId];
  if (!key) return;
  state.filtered[tabId] = [...state.filtered[tabId]].sort((a, b) => {
    const av = String(a[key] ?? "").toLowerCase();
    const bv = String(b[key] ?? "").toLowerCase();
    return dir === "asc" ? av.localeCompare(bv) : bv.localeCompare(av);
  });
}

// ============================================================
// Search & filter
// ============================================================
function applyFiltersAndSearch(tabId) {
  const tab = TABS.find(t => t.id === tabId);
  const query = (document.getElementById(`search-${tabId}`)?.value || "").toLowerCase().trim();

  // Collect active filter values
  const activeFilters = {};
  tab.columns.filter(c => c.filter).forEach(col => {
    const el = document.getElementById(`filter-${tabId}-${col.key}`);
    if (el && el.value) activeFilters[col.key] = el.value;
  });

  let rows = state.data[tabId];

  // Text search across all fields
  if (query) {
    rows = rows.filter(row =>
      Object.values(row).some(v => String(v ?? "").toLowerCase().includes(query))
    );
  }

  // Column filters (exact match)
  Object.entries(activeFilters).forEach(([key, val]) => {
    rows = rows.filter(row => String(row[key] ?? "") === val);
  });

  state.filtered[tabId] = rows;
  applySort(tabId);
  renderActiveTab();
}

function populateFilters(tab) {
  tab.columns.filter(c => c.filter).forEach(col => {
    const el = document.getElementById(`filter-${tab.id}-${col.key}`);
    if (!el) return;
    const values = [...new Set(
      (state.data[tab.id] || []).map(r => String(r[col.key] ?? "")).filter(Boolean)
    )].sort();
    el.innerHTML = `<option value="">All ${col.label}s</option>` +
      values.map(v => `<option value="${escapeHtml(v)}">${escapeHtml(v)}</option>`).join("");
  });
}

// ============================================================
// Tab switching
// ============================================================
function switchTab(tabId) {
  state.activeTab = tabId;
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.tab === tabId);
  });
  document.querySelectorAll(".tab-panel").forEach(panel => {
    panel.classList.toggle("active", panel.id === `panel-${tabId}`);
  });
  renderActiveTab();
}

// ============================================================
// Counts & metadata
// ============================================================
function updateCount(tabId, count) {
  const el = document.getElementById(`count-${tabId}`);
  if (el) el.textContent = count.toLocaleString();
}

function updateTabCounts() {
  TABS.forEach(tab => {
    const el = document.getElementById(`tab-count-${tab.id}`);
    if (el) el.textContent = (state.data[tab.id]?.length || 0).toLocaleString();
  });
}

function renderLastUpdated(ts) {
  const el = document.getElementById("last-updated");
  if (!el) return;
  if (!ts) { el.textContent = "Never"; return; }
  try {
    el.textContent = new Date(ts).toLocaleDateString("en-US", {
      year: "numeric", month: "long", day: "numeric",
    });
  } catch {
    el.textContent = ts;
  }
}

// ============================================================
// Bootstrap
// ============================================================
document.addEventListener("DOMContentLoaded", () => {
  // Tab buttons
  document.querySelectorAll(".tab-btn").forEach(btn => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  // Search boxes
  TABS.forEach(tab => {
    const searchEl = document.getElementById(`search-${tab.id}`);
    if (searchEl) {
      searchEl.addEventListener("input", () => applyFiltersAndSearch(tab.id));
    }

    // Filter selects
    tab.columns.filter(c => c.filter).forEach(col => {
      const el = document.getElementById(`filter-${tab.id}-${col.key}`);
      if (el) el.addEventListener("change", () => applyFiltersAndSearch(tab.id));
    });
  });

  // Load data
  loadAll().catch(err => {
    console.error("Failed to load data:", err);
    const msg = '<p class="error-msg">Failed to load data. Make sure to open this site via a web server, not directly as a local file.</p>';
    TABS.forEach(tab => {
      const el = document.getElementById(`table-${tab.id}`);
      if (el) el.innerHTML = msg;
    });
  });
});
