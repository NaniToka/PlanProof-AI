/**
 * PlanProof AI - System Status Client (Milestone 1)
 */

async function fetchHealth() {
  const healthPill = document.getElementById('health-status');
  const envVal = document.getElementById('env-val');
  const verVal = document.getElementById('ver-val');

  try {
    const res = await fetch('/health');
    if (!res.ok) throw new Error(`Health HTTP ${res.status}`);
    const data = await res.json();

    healthPill.className = 'pill pill-success';
    healthPill.textContent = 'ONLINE';
    envVal.textContent = data.environment || 'development';
    verVal.textContent = `v${data.version || '0.1.0'}`;
  } catch (err) {
    healthPill.className = 'pill pill-error';
    healthPill.textContent = 'OFFLINE';
    envVal.textContent = 'Unavailable';
    verVal.textContent = '—';
  }
}

async function fetchDataStatus() {
  const datasetPill = document.getElementById('dataset-status');
  const countEl = document.getElementById('scenarios-count');
  const severityEl = document.getElementById('severity-range');
  const budgetEl = document.getElementById('budget-status');
  const vendorEl = document.getElementById('vendor-status');
  const tagCloud = document.getElementById('crisis-types-cloud');

  try {
    const res = await fetch('/api/v1/data-status');
    const data = await res.json();

    if (res.ok && data.dataset_loaded) {
      datasetPill.className = 'pill pill-success';
      datasetPill.textContent = 'LOADED & VERIFIED';
      countEl.textContent = Number(data.row_count).toLocaleString();
      severityEl.textContent = `Level ${data.severity_range.min} – ${data.severity_range.max}`;
      budgetEl.textContent = data.budget_splits_loaded ? 'Verified (100% Splits)' : 'Missing';
      vendorEl.textContent = data.vendor_checklists_loaded ? 'Verified' : 'Missing';

      // Render crisis category badges
      tagCloud.innerHTML = '';
      (data.available_crisis_types || []).forEach((type) => {
        const tag = document.createElement('span');
        tag.className = 'tag';
        tag.textContent = type.replace(/_/g, ' ');
        tagCloud.appendChild(tag);
      });
    } else {
      datasetPill.className = 'pill pill-error';
      datasetPill.textContent = data.status ? data.status.toUpperCase() : 'ERROR';
      countEl.textContent = '0';
      severityEl.textContent = '—';
      budgetEl.textContent = data.budget_splits_loaded ? 'Loaded' : 'Unavailable';
      vendorEl.textContent = data.vendor_checklists_loaded ? 'Loaded' : 'Unavailable';
      tagCloud.innerHTML = '<span class="tag-skeleton">No crisis scenarios loaded.</span>';
    }
  } catch (err) {
    datasetPill.className = 'pill pill-error';
    datasetPill.textContent = 'DISCONNECTED';
    countEl.textContent = '—';
    severityEl.textContent = '—';
    tagCloud.innerHTML = '<span class="tag-skeleton">Failed to connect to API.</span>';
  }
}

async function refreshAll() {
  await Promise.all([fetchHealth(), fetchDataStatus()]);
}

document.addEventListener('DOMContentLoaded', () => {
  refreshAll();
  const btn = document.getElementById('btn-refresh');
  if (btn) {
    btn.addEventListener('click', () => {
      btn.textContent = 'Checking...';
      refreshAll().finally(() => {
        btn.textContent = 'Refresh Status';
      });
    });
  }
});
