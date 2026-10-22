/**
 * PlanProof AI — Frontend Console Controller
 * Connects vanilla JS UI to the 18 FastAPI backend endpoints.
 */

'use strict';

// ==============================================================================
// 1. Application State
// ==============================================================================

const state = {
  currentEventId: null,
  currentEvent: null,
  events: [],
  activeView: 'overview',
  aiStatus: { configured: false, mode: 'auto', model: 'gemini-2.5-flash' },
  dataStatus: null,
  health: null,
  cache: {},
  filter: {
    vendorStatus: 'all',
    vendorCategory: 'all',
    ideaCategory: 'all',
    riskSeverity: 'all',
    milestoneStatus: 'all',
  },
};

// ==============================================================================
// 2. API Communication Layer
// ==============================================================================

const API = {
  baseUrl: '',

  async request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    const config = {
      ...options,
      headers: { ...defaultHeaders, ...options.headers },
    };

    try {
      const response = await fetch(url, config);
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        const errorMsg = data?.error?.message || data?.detail || `HTTP ${response.status}: Request failed`;
        throw new Error(errorMsg);
      }
      return data;
    } catch (err) {
      console.error(`API Error [${options.method || 'GET'} ${path}]:`, err);
      throw err;
    }
  },

  getHealth() {
    return this.request('/health');
  },

  getDataStatus() {
    return this.request('/api/v1/data-status');
  },

  getAIStatus() {
    return this.request('/api/v1/ai/status');
  },

  listEvents() {
    return this.request('/api/v1/events?limit=50');
  },

  createEvent(payload) {
    return this.request('/api/v1/events', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getEvent(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}`);
  },

  updateEvent(eventId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  getBudget(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/budget`);
  },

  rebalanceBudget(eventId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/budget/rebalance`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getTimeline(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/timeline`);
  },

  updateMilestone(eventId, milestoneId, status) {
    return this.request(
      `/api/v1/events/${encodeURIComponent(eventId)}/timeline/milestones/${encodeURIComponent(milestoneId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify({ status }),
      }
    );
  },

  getVendors(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/vendors/checklist`);
  },

  updateVendorItem(eventId, itemId, payload) {
    return this.request(
      `/api/v1/events/${encodeURIComponent(eventId)}/vendors/checklist/${encodeURIComponent(itemId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(payload),
      }
    );
  },

  getIdeas(eventId, category = null) {
    const q = category && category !== 'all' ? `?category=${encodeURIComponent(category)}&limit=20` : '?limit=20';
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/ideas${q}`);
  },

  getRisks(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/risks`);
  },

  getFamilyCouncil(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/family-council`);
  },
};

// ==============================================================================
// 3. UI Helpers & Formatters
// ==============================================================================

function formatINR(val) {
  if (val === null || val === undefined || isNaN(val)) return '₹0';
  return '₹' + Number(val).toLocaleString('en-IN');
}

function formatDate(isoStr) {
  if (!isoStr) return 'Not Scheduled';
  const d = new Date(isoStr);
  if (isNaN(d.getTime())) return isoStr;
  return d.toLocaleDateString('en-IN', { year: 'numeric', month: 'short', day: 'numeric' });
}

function calculateDaysRemaining(dateStr) {
  if (!dateStr) return null;
  const target = new Date(dateStr);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diffTime = target - today;
  return Math.ceil(diffTime / (1000 * 60 * 60 * 24));
}

function escapeHTML(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span>
    <div>${escapeHTML(message)}</div>
  `;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Category Color Palette for Budget Breakdown
const BUDGET_COLORS = {
  venue: '#3B0A6B',
  catering: '#00E5FF',
  decor: '#8B5CF6',
  photo_video: '#10B981',
  attire_beauty: '#EC4899',
  entertainment: '#F59E0B',
  logistics: '#3B82F6',
  buffer: '#14B8A6',
};

const CATEGORY_NAMES = {
  venue: 'Venue & Hall',
  catering: 'Catering & Dining',
  decor: 'Decoration & Stage',
  photo_video: 'Photography & Cinema',
  attire_beauty: 'Attire & Beauty',
  entertainment: 'Music & Entertainment',
  logistics: 'Logistics & Transit',
  buffer: 'Emergency Contingency Buffer',
};

// ==============================================================================
// 4. View Rendering Controllers
// ==============================================================================

/** Render Empty State When No Event Exists */
function renderEmptyEventState(targetEl, viewTitle) {
  targetEl.innerHTML = `
    <div class="empty-state">
      <div class="empty-state-icon">📅</div>
      <h2 class="empty-state-title">No Event Selected</h2>
      <p class="empty-state-desc">
        Create an event profile or select one from the top header to explore ${escapeHTML(viewTitle)}.
      </p>
      <button class="btn btn-cyan" onclick="openCreateEventModal()">
        + Create Event Profile
      </button>
    </div>
  `;
}

/** 1. Render Overview Dashboard */
async function renderOverview() {
  const container = document.getElementById('overview-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Event Overview');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Loading event overview...</p></div>`;

  try {
    const [profile, budgetPlan, timeline, vendors, risks, council] = await Promise.all([
      API.getEvent(state.currentEventId),
      API.getBudget(state.currentEventId).catch(() => null),
      API.getTimeline(state.currentEventId).catch(() => null),
      API.getVendors(state.currentEventId).catch(() => null),
      API.getRisks(state.currentEventId).catch(() => null),
      API.getFamilyCouncil(state.currentEventId).catch(() => null),
    ]);

    state.currentEvent = profile;
    updateActiveEventBadge(profile);

    const daysRemaining = calculateDaysRemaining(profile.event_date);
    const daysLabel = daysRemaining !== null
      ? (daysRemaining >= 0 ? `${daysRemaining} days remaining` : `${Math.abs(daysRemaining)} days ago`)
      : 'Date unscheduled';

    const completedMilestones = timeline?.milestones?.filter(m => m.status === 'completed').length || 0;
    const totalMilestones = timeline?.milestones?.length || 0;
    const completedTasks = vendors?.summary?.completed || 0;
    const totalTasks = vendors?.summary?.total_items || 0;
    const criticalRisksCount = risks?.data?.summary?.critical_risks || 0;
    const totalRisksCount = risks?.data?.total_risks || 0;

    let budgetAllocationsHTML = '';
    let stackedBarHTML = '';
    if (budgetPlan?.allocations) {
      const total = budgetPlan.total_budget_inr || 1;
      for (const [cat, amt] of Object.entries(budgetPlan.allocations)) {
        const pct = ((amt / total) * 100).toFixed(1);
        const color = BUDGET_COLORS[cat] || '#8b5cf6';
        stackedBarHTML += `<div class="budget-bar-segment" style="width: ${pct}%; background-color: ${color};" title="${CATEGORY_NAMES[cat] || cat}: ${pct}% (${formatINR(amt)})"></div>`;
      }
    }

    container.innerHTML = `
      <!-- Hero Event Banner -->
      <div class="card" style="margin-bottom: 1.5rem; background: linear-gradient(135deg, rgba(59, 10, 107, 0.4) 0%, rgba(18, 7, 34, 0.9) 100%); border-left: 4px solid var(--electric-cyan);">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.5rem;">
              <span class="badge badge-cyan">${escapeHTML(profile.event_type.toUpperCase())}</span>
              <span class="badge badge-amethyst">${escapeHTML(profile.city_tier.toUpperCase())}</span>
              ${profile.city ? `<span class="badge badge-amethyst">📍 ${escapeHTML(profile.city)}</span>` : ''}
              <span class="badge badge-success">ID: ${escapeHTML(profile.event_id)}</span>
            </div>
            <h1 style="font-size: 1.75rem; font-weight: 800; letter-spacing: -0.02em; margin-bottom: 0.35rem;">
              ${escapeHTML(profile.event_name || `${profile.event_type.charAt(0).toUpperCase() + profile.event_type.slice(1)} Plan`)}
            </h1>
            <p style="color: var(--text-muted); font-size: 0.9rem;">
              ${escapeHTML(profile.theme_notes || 'No specific theme notes recorded.')}
            </p>
          </div>
          <div style="text-align: right;">
            <div class="badge badge-amethyst" style="font-size: 0.9rem; padding: 0.45rem 1rem;">
              📅 ${formatDate(profile.event_date)}
            </div>
            <div style="font-size: 0.85rem; color: var(--electric-cyan); font-weight: 700; margin-top: 0.35rem;">
              ${daysLabel}
            </div>
          </div>
        </div>
      </div>

      <!-- Quick Metric Tiles -->
      <div class="grid-4" style="margin-bottom: 1.5rem;">
        <div class="stat-tile">
          <span class="stat-label">Total Budget</span>
          <span class="stat-value">${formatINR(profile.total_budget_inr)}</span>
          <span class="stat-sub">INR (${formatINR(Math.round(profile.total_budget_inr / profile.guest_count))}/guest)</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Headcount</span>
          <span class="stat-value">${profile.guest_count.toLocaleString()}</span>
          <span class="stat-sub">Expected Guests</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Milestones Done</span>
          <span class="stat-value">${completedMilestones}/${totalMilestones}</span>
          <span class="stat-sub">${totalMilestones > 0 ? Math.round((completedMilestones / totalMilestones) * 100) : 0}% scheduled</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Active Risks</span>
          <span class="stat-value" style="color: ${criticalRisksCount > 0 ? 'var(--danger)' : 'var(--warning)'};">${totalRisksCount}</span>
          <span class="stat-sub">${criticalRisksCount} Critical Alerts</span>
        </div>
      </div>

      <!-- Main Overview Cards Grid -->
      <div class="grid-2" style="margin-bottom: 1.5rem;">
        <!-- Budget Breakdown Summary -->
        <div class="card">
          <div class="card-header">
            <div class="card-title-wrap">
              <div class="card-icon">💰</div>
              <div>
                <h2 class="card-title">Budget Allocation Summary</h2>
                <p class="card-subtitle">Deterministic 8-category allocation</p>
              </div>
            </div>
            <a href="#budget" class="btn btn-secondary btn-sm">Full Planner →</a>
          </div>
          <div class="budget-stacked-bar">${stackedBarHTML}</div>
          <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; font-size: 0.85rem;">
            <div><span style="color: var(--electric-cyan);">●</span> Catering: <strong>${formatINR(profile.budget?.catering)}</strong></div>
            <div><span style="color: #3B0A6B;">●</span> Venue: <strong>${formatINR(profile.budget?.venue)}</strong></div>
            <div><span style="color: #8B5CF6;">●</span> Decor: <strong>${formatINR(profile.budget?.decor)}</strong></div>
            <div><span style="color: #14B8A6;">●</span> Buffer (Contingency): <strong>${formatINR(profile.budget?.buffer)}</strong></div>
          </div>
        </div>

        <!-- Vendor Checklist Summary -->
        <div class="card">
          <div class="card-header">
            <div class="card-title-wrap">
              <div class="card-icon">🤝</div>
              <div>
                <h2 class="card-title">Vendor & Tasks Progress</h2>
                <p class="card-subtitle">${completedTasks} of ${totalTasks} tasks completed</p>
              </div>
            </div>
            <a href="#vendors" class="btn btn-secondary btn-sm">View Checklist →</a>
          </div>
          <div style="display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <span class="badge badge-success">✓ ${vendors?.summary?.completed || 0} Completed</span>
            <span class="badge badge-warning">⚡ ${vendors?.summary?.in_progress || 0} In Progress</span>
            <span class="badge badge-cyan">⌛ ${vendors?.summary?.pending || 0} Pending</span>
            <span class="badge badge-amethyst">★ ${vendors?.summary?.booked_vendors || 0} Booked</span>
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted);">
            Immediate Next Step: Finalize core venue contract and locking in catering plate numbers.
          </div>
        </div>
      </div>

      <!-- Council & Risk Teasers -->
      <div class="grid-2" style="margin-bottom: 1.5rem;">
        <!-- Pre-Mortem Risk Alert -->
        <div class="card">
          <div class="card-header">
            <div class="card-title-wrap">
              <div class="card-icon">🛡️</div>
              <div>
                <h2 class="card-title">Risk Analysis Preview</h2>
                <p class="card-subtitle">${totalRisksCount} evaluated failure modes</p>
              </div>
            </div>
            <a href="#risks" class="btn btn-secondary btn-sm">Risk Matrix →</a>
          </div>
          ${
            risks?.data?.risks?.slice(0, 2).map(r => `
              <div style="background: var(--bg-surface-3); border-radius: var(--radius-md); padding: 0.75rem 1rem; margin-bottom: 0.5rem; border-left: 3px solid ${r.impact === 'critical' ? 'var(--danger)' : 'var(--warning)'};">
                <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary); margin-bottom: 0.2rem;">${escapeHTML(r.title)}</div>
                <div style="font-size: 0.8rem; color: var(--text-muted);">${escapeHTML(r.contingency_plan)}</div>
              </div>
            `).join('') || '<p style="color: var(--text-muted); font-size: 0.85rem;">No active risks detected.</p>'
          }
        </div>

        <!-- Family Council Teaser -->
        <div class="card">
          <div class="card-header">
            <div class="card-title-wrap">
              <div class="card-icon">👥</div>
              <div>
                <h2 class="card-title">Four-Persona Family Council</h2>
                <p class="card-subtitle">Multilateral planning oversight</p>
              </div>
            </div>
            <a href="#council" class="btn btn-secondary btn-sm">Council Room →</a>
          </div>
          <p style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.75rem; font-style: italic;">
            "${escapeHTML(council?.data?.summary?.overall_verdict || 'Balanced deliberation active across budget, logistics, guest comfort, and traditions.')}"
          </p>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <span class="badge badge-cyan">🛡️ Budget Guardian</span>
            <span class="badge badge-amethyst">❤️ Guest Comfort</span>
            <span class="badge badge-warning">⭐ Tradition Keeper</span>
            <span class="badge badge-success">⚙️ Logistics Planner</span>
          </div>
        </div>
      </div>

      <!-- Foundation Service Status (Preserved from Milestone 1) -->
      <div class="card" style="background: rgba(10, 4, 20, 0.4); border-color: rgba(91, 20, 160, 0.2);">
        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem;">
          <div>
            <span style="font-size: 0.825rem; font-weight: 700; color: var(--text-muted);">BACKEND ENGINE STATUS</span>
            <span style="font-size: 0.825rem; color: var(--text-dim); margin-left: 0.5rem;">FastAPI · 5,000 Verified Crisis Scenarios Loaded · Offline Fallback Ready</span>
          </div>
          <a href="/docs" target="_blank" rel="noopener" class="btn btn-secondary btn-sm" style="font-size: 0.775rem;">
            Interactive Swagger Docs (OpenAPI) ↗
          </a>
        </div>
      </div>
    `;
  } catch (err) {
    container.innerHTML = `
      <div class="card" style="border-color: var(--danger);">
        <h3 style="color: var(--danger); margin-bottom: 0.5rem;">Failed to load overview</h3>
        <p style="color: var(--text-muted);">${escapeHTML(err.message)}</p>
      </div>
    `;
  }
}

/** 2. Render Event Details View */
async function renderEventDetails() {
  const container = document.getElementById('event-details-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Event Details');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Loading event profile...</p></div>`;

  try {
    const profile = await API.getEvent(state.currentEventId);
    state.currentEvent = profile;

    container.innerHTML = `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">📋</div>
            <div>
              <h2 class="card-title">Event Profile: ${escapeHTML(profile.event_id)}</h2>
              <p class="card-subtitle">Created on ${new Date(profile.created_at).toLocaleString('en-IN')}</p>
            </div>
          </div>
          <button class="btn btn-cyan btn-sm" onclick="openCreateEventModal()">+ Create Another Event</button>
        </div>

        <form id="form-edit-event-details">
          <div class="form-grid-3">
            <div class="form-group">
              <label class="form-label">Event Category</label>
              <input type="text" class="form-input" value="${escapeHTML(profile.event_type.toUpperCase())}" disabled>
            </div>
            <div class="form-group">
              <label class="form-label">Event Name</label>
              <input type="text" id="edit-event-name" class="form-input" value="${escapeHTML(profile.event_name || '')}" maxlength="150" placeholder="e.g. Diya & Kabir's Wedding">
            </div>
            <div class="form-group">
              <label class="form-label">City Location</label>
              <input type="text" id="edit-event-city" class="form-input" value="${escapeHTML(profile.city || '')}" maxlength="100">
            </div>
          </div>

          <div class="form-grid-3">
            <div class="form-group">
              <label class="form-label">City Tier</label>
              <select id="edit-event-tier" class="form-select">
                <option value="metro" ${profile.city_tier === 'metro' ? 'selected' : ''}>Metro (Tier 1)</option>
                <option value="tier2" ${profile.city_tier === 'tier2' ? 'selected' : ''}>Tier 2</option>
                <option value="tier3" ${profile.city_tier === 'tier3' ? 'selected' : ''}>Tier 3</option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">Scheduled Date</label>
              <input type="date" id="edit-event-date" class="form-input" value="${profile.event_date || ''}">
            </div>
            <div class="form-group">
              <label class="form-label">Guest Count (1 - 2,000)</label>
              <input type="number" id="edit-event-guests" class="form-input" min="1" max="2000" value="${profile.guest_count}">
            </div>
          </div>

          <div class="form-group">
            <label class="form-label">Theme, Style, or Cultural Notes</label>
            <textarea id="edit-event-notes" class="form-textarea" maxlength="1000">${escapeHTML(profile.theme_notes || '')}</textarea>
          </div>

          <div style="display: flex; justify-content: flex-end; gap: 0.75rem;">
            <button type="submit" class="btn btn-primary" id="btn-save-event-details">Save Profile Changes</button>
          </div>
        </form>
      </div>

      <!-- All Events in Ephemeral Storage -->
      <div class="card">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">🗂️</div>
            <div>
              <h2 class="card-title">All Stored Event Profiles</h2>
              <p class="card-subtitle">Quickly switch between active plans</p>
            </div>
          </div>
        </div>

        <div style="display: flex; flex-direction: column; gap: 0.65rem;">
          ${
            state.events.map(ev => `
              <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; background: var(--bg-surface-3); border-radius: var(--radius-md); border: 1px solid ${ev.event_id === state.currentEventId ? 'var(--electric-cyan)' : 'var(--amethyst-border)'};">
                <div>
                  <span class="badge ${ev.event_id === state.currentEventId ? 'badge-cyan' : 'badge-amethyst'}">${escapeHTML(ev.event_id)}</span>
                  <strong style="margin-left: 0.5rem; color: var(--text-primary);">${escapeHTML(ev.event_name || ev.event_type)}</strong>
                  <span style="color: var(--text-muted); font-size: 0.85rem; margin-left: 0.5rem;">📍 ${escapeHTML(ev.city || 'India')} · 👥 ${ev.guest_count} guests · ${formatINR(ev.total_budget_inr)}</span>
                </div>
                <div>
                  ${ev.event_id === state.currentEventId 
                    ? '<span class="badge badge-success">ACTIVE EVENT</span>' 
                    : `<button class="btn btn-secondary btn-sm" onclick="selectEvent('${escapeHTML(ev.event_id)}')">Select Event</button>`
                  }
                </div>
              </div>
            `).join('')
          }
        </div>
      </div>
    `;

    document.getElementById('form-edit-event-details')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn-save-event-details');
      btn.textContent = 'Saving...';
      btn.disabled = true;

      const payload = {
        event_name: document.getElementById('edit-event-name').value.trim() || null,
        city: document.getElementById('edit-event-city').value.trim() || null,
        city_tier: document.getElementById('edit-event-tier').value,
        event_date: document.getElementById('edit-event-date').value || null,
        guest_count: parseInt(document.getElementById('edit-event-guests').value, 10),
        theme_notes: document.getElementById('edit-event-notes').value.trim() || null,
      };

      try {
        const updated = await API.updateEvent(state.currentEventId, payload);
        state.currentEvent = updated;
        showToast('Event profile updated successfully', 'success');
        await loadEventsList();
        renderEventDetails();
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.textContent = 'Save Profile Changes';
        btn.disabled = false;
      }
    });

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

/** 3. Render Budget Planner View */
async function renderBudget() {
  const container = document.getElementById('budget-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Budget Planner');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Calculating deterministic budget allocations...</p></div>`;

  try {
    const budgetPlan = await API.getBudget(state.currentEventId);
    const profile = state.currentEvent || (await API.getEvent(state.currentEventId));

    const total = budgetPlan.total_budget_inr;
    const perGuest = Math.round(total / (profile.guest_count || 1));
    const bufferAmount = budgetPlan.allocations.buffer || 0;
    const bufferPct = ((bufferAmount / total) * 100).toFixed(1);
    const isBufferHealthy = bufferPct >= 5.0;

    let categoriesGridHTML = '';
    let stackedBarHTML = '';

    for (const [cat, amt] of Object.entries(budgetPlan.allocations)) {
      const pct = ((amt / total) * 100).toFixed(1);
      const color = BUDGET_COLORS[cat] || '#8B5CF6';
      stackedBarHTML += `<div class="budget-bar-segment" style="width: ${pct}%; background-color: ${color};" title="${CATEGORY_NAMES[cat] || cat}: ${pct}% (${formatINR(amt)})"></div>`;

      categoriesGridHTML += `
        <div class="budget-category-row">
          <div class="budget-cat-info">
            <div class="budget-cat-indicator" style="background-color: ${color};"></div>
            <div>
              <div class="budget-cat-name">${CATEGORY_NAMES[cat] || cat}</div>
              <div style="font-size: 0.775rem; color: var(--text-dim);">Hamilton-Hare integer allocation</div>
            </div>
          </div>
          <div class="budget-cat-numbers">
            <div class="budget-cat-amount">${formatINR(amt)}</div>
            <div class="budget-cat-pct">${pct}% of budget</div>
          </div>
        </div>
      `;
    }

    container.innerHTML = `
      <!-- Top Budget Summary Card -->
      <div class="grid-3" style="margin-bottom: 1.5rem;">
        <div class="stat-tile">
          <span class="stat-label">Total Allocated Budget</span>
          <span class="stat-value">${formatINR(total)}</span>
          <span class="stat-sub">Deterministic 100% split</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Spend Per Guest</span>
          <span class="stat-value">${formatINR(perGuest)}</span>
          <span class="stat-sub">Across ${profile.guest_count} guests</span>
        </div>
        <div class="stat-tile" style="border-left: 4px solid ${isBufferHealthy ? 'var(--success)' : 'var(--danger)'};">
          <span class="stat-label">Contingency Safety Buffer</span>
          <span class="stat-value" style="color: ${isBufferHealthy ? 'var(--electric-cyan)' : 'var(--danger)'};">${formatINR(bufferAmount)}</span>
          <span class="stat-sub">${bufferPct}% ${isBufferHealthy ? '(Healthy ≥ 5%)' : '(Underfunded < 5%)'}</span>
        </div>
      </div>

      <!-- Visual Breakdown -->
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">📊</div>
            <div>
              <h2 class="card-title">8-Category Allocation Breakdown</h2>
              <p class="card-subtitle">No penny lost · Hamilton-Hare largest-remainder quota</p>
            </div>
          </div>
        </div>
        <div class="budget-stacked-bar">${stackedBarHTML}</div>
        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.75rem;">
          ${categoriesGridHTML}
        </div>
      </div>

      <!-- Interactive Budget Rebalancer -->
      <div class="card">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">⚖️</div>
            <div>
              <h2 class="card-title">Rebalance Event Budget</h2>
              <p class="card-subtitle">Scale budget up or down while strictly preserving essential categories</p>
            </div>
          </div>
        </div>

        <form id="form-rebalance-budget">
          <div class="form-grid-2">
            <div class="form-group">
              <label for="input-rebalance-amount" class="form-label">New Total Budget (INR) *</label>
              <input type="number" id="input-rebalance-amount" class="form-input" min="10000" max="50000000" step="10000" value="${total}" required>
            </div>
            <div class="form-group" style="display: flex; align-items: center; gap: 0.5rem; padding-top: 1.8rem;">
              <input type="checkbox" id="check-strict-protect" style="width: 18px; height: 18px; accent-color: var(--electric-cyan);">
              <label for="check-strict-protect" class="form-label" style="margin: 0; cursor: pointer;">
                Strict Protect (Prevent reductions to catering & contingency buffer)
              </label>
            </div>
          </div>

          <div id="rebalance-delta-box" style="display: none; margin-bottom: 1rem; padding: 1rem; background: var(--bg-surface-3); border-radius: var(--radius-md);"></div>

          <div style="display: flex; justify-content: flex-end;">
            <button type="submit" class="btn btn-cyan" id="btn-rebalance-submit">Execute Deterministic Rebalance</button>
          </div>
        </form>
      </div>
    `;

    document.getElementById('form-rebalance-budget')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = document.getElementById('btn-rebalance-submit');
      btn.textContent = 'Rebalancing...';
      btn.disabled = true;

      const newBudget = parseInt(document.getElementById('input-rebalance-amount').value, 10);
      const strictProtect = document.getElementById('check-strict-protect').checked;

      try {
        const res = await API.rebalanceBudget(state.currentEventId, {
          new_total_budget_inr: newBudget,
          strict_protect: strictProtect,
        });
        showToast('Budget successfully rebalanced', 'success');
        renderBudget();
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.textContent = 'Execute Deterministic Rebalance';
        btn.disabled = false;
      }
    });

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

/** 4. Render Timeline View */
async function renderTimeline() {
  const container = document.getElementById('timeline-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Event Timeline');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Loading chronological milestone schedule...</p></div>`;

  try {
    const timeline = await API.getTimeline(state.currentEventId);
    const milestones = timeline.milestones || [];

    const total = milestones.length;
    const completed = milestones.filter(m => m.status === 'completed').length;
    const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

    const filtered = milestones.filter(m => {
      if (state.filter.milestoneStatus === 'pending') return m.status === 'pending';
      if (state.filter.milestoneStatus === 'completed') return m.status === 'completed';
      return true;
    });

    container.innerHTML = `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">⏳</div>
            <div>
              <h2 class="card-title">Chronological Event Timeline</h2>
              <p class="card-subtitle">${completed} of ${total} milestones achieved (${pct}%)</p>
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem;">
            <button class="btn btn-sm ${state.filter.milestoneStatus === 'all' ? 'btn-primary' : 'btn-secondary'}" onclick="setMilestoneFilter('all')">All</button>
            <button class="btn btn-sm ${state.filter.milestoneStatus === 'pending' ? 'btn-primary' : 'btn-secondary'}" onclick="setMilestoneFilter('pending')">Pending</button>
            <button class="btn btn-sm ${state.filter.milestoneStatus === 'completed' ? 'btn-primary' : 'btn-secondary'}" onclick="setMilestoneFilter('completed')">Completed</button>
          </div>
        </div>

        <div style="height: 8px; background: var(--bg-surface-3); border-radius: var(--radius-full); overflow: hidden; margin-bottom: 1.5rem;">
          <div style="height: 100%; width: ${pct}%; background: linear-gradient(90deg, var(--royal-amethyst), var(--electric-cyan));"></div>
        </div>

        <div class="timeline-list">
          ${
            filtered.map(m => `
              <div class="timeline-item ${m.status === 'completed' ? 'completed' : ''}" id="milestone-${escapeHTML(m.milestone_id)}">
                <div class="timeline-node">
                  ${m.status === 'completed' ? '✓' : ''}
                </div>
                <div class="timeline-card">
                  <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.35rem;">
                    <div>
                      <div class="timeline-meta">
                        <span class="badge badge-cyan">${escapeHTML(m.milestone_id)}</span>
                        <span class="badge badge-amethyst">${escapeHTML(m.category)}</span>
                        <span class="badge ${m.priority === 'high' ? 'badge-danger' : m.priority === 'medium' ? 'badge-warning' : 'badge-cyan'}">${escapeHTML(m.priority.toUpperCase())}</span>
                        ${m.is_overdue ? '<span class="badge badge-danger">OVERDUE</span>' : ''}
                      </div>
                      <h3 class="timeline-title">${escapeHTML(m.title)}</h3>
                    </div>
                    <button class="btn ${m.status === 'completed' ? 'btn-secondary' : 'btn-cyan'} btn-sm" onclick="toggleMilestoneStatus('${escapeHTML(m.milestone_id)}', '${m.status}')">
                      ${m.status === 'completed' ? '↺ Mark Pending' : '✓ Mark Complete'}
                    </button>
                  </div>
                  <p class="timeline-desc">${escapeHTML(m.description)}</p>
                  <div style="font-size: 0.8rem; color: var(--text-dim); display: flex; gap: 1rem;">
                    <span>📅 Due: <strong>${formatDate(m.due_date)}</strong></span>
                    <span>⏱ Lead Time: <strong>T-${m.days_before_event} days</strong></span>
                  </div>
                </div>
              </div>
            `).join('') || '<p style="color: var(--text-muted);">No milestones match the selected filter.</p>'
          }
        </div>
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

async function toggleMilestoneStatus(milestoneId, currentStatus) {
  const newStatus = currentStatus === 'completed' ? 'pending' : 'completed';
  try {
    await API.updateMilestone(state.currentEventId, milestoneId, newStatus);
    showToast(`Milestone marked as ${newStatus}`, 'success');
    renderTimeline();
  } catch (err) {
    showToast(err.message, 'error');
  }
}

function setMilestoneFilter(f) {
  state.filter.milestoneStatus = f;
  renderTimeline();
}

/** 5. Render Vendor Checklist View */
async function renderVendors() {
  const container = document.getElementById('vendors-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Vendor Checklist');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Loading vendor checklist & booking progress...</p></div>`;

  try {
    const res = await API.getVendors(state.currentEventId);
    const items = res.items || [];
    const summary = res.summary || {};

    const filtered = items.filter(item => {
      if (state.filter.vendorStatus !== 'all' && item.status !== state.filter.vendorStatus) return false;
      if (state.filter.vendorCategory !== 'all' && item.category !== state.filter.vendorCategory) return false;
      return true;
    });

    container.innerHTML = `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">🤝</div>
            <div>
              <h2 class="card-title">Event Vendor Coordination Checklist</h2>
              <p class="card-subtitle">${summary.completed || 0} completed · ${summary.booked_vendors || 0} booked contracts</p>
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <select class="form-select" style="width: auto; padding: 0.35rem 0.75rem; font-size: 0.825rem;" onchange="setVendorStatusFilter(this.value)">
              <option value="all" ${state.filter.vendorStatus === 'all' ? 'selected' : ''}>All Statuses</option>
              <option value="pending" ${state.filter.vendorStatus === 'pending' ? 'selected' : ''}>Pending</option>
              <option value="in_progress" ${state.filter.vendorStatus === 'in_progress' ? 'selected' : ''}>In Progress</option>
              <option value="completed" ${state.filter.vendorStatus === 'completed' ? 'selected' : ''}>Completed</option>
              <option value="skipped" ${state.filter.vendorStatus === 'skipped' ? 'selected' : ''}>Skipped</option>
            </select>
          </div>
        </div>

        <div class="grid-3">
          ${
            filtered.map(item => `
              <div class="vendor-card">
                <div>
                  <div class="vendor-card-header">
                    <span class="badge badge-cyan">${escapeHTML(item.id)}</span>
                    <span class="badge ${item.priority === 'high' ? 'badge-danger' : item.priority === 'medium' ? 'badge-warning' : 'badge-cyan'}">${escapeHTML(item.priority.toUpperCase())}</span>
                  </div>
                  <h3 style="font-size: 1rem; font-weight: 700; color: var(--text-primary); margin: 0.4rem 0;">${escapeHTML(item.title)}</h3>
                  <p style="font-size: 0.825rem; color: var(--text-muted); line-height: 1.4; margin-bottom: 0.65rem;">${escapeHTML(item.description)}</p>
                </div>

                <div>
                  <div style="background: var(--bg-surface-3); padding: 0.65rem; border-radius: var(--radius-sm); margin-bottom: 0.65rem; font-size: 0.8rem;">
                    <div>Task Status: <strong style="color: var(--electric-cyan);">${escapeHTML(item.status.toUpperCase())}</strong></div>
                    <div>Booking State: <strong style="color: #c7d2fe;">${escapeHTML((item.booking_status || 'not_started').toUpperCase())}</strong></div>
                    ${item.vendor_name ? `<div>Vendor: <strong>${escapeHTML(item.vendor_name)}</strong></div>` : ''}
                    ${item.due_date ? `<div>Due Date: <strong>${formatDate(item.due_date)}</strong></div>` : ''}
                    ${item.notes ? `<div style="margin-top: 0.35rem; color: var(--text-secondary); font-style: italic;">"${escapeHTML(item.notes)}"</div>` : ''}
                  </div>

                  <button class="btn btn-secondary btn-sm" style="width: 100%;" onclick="openEditVendorModal('${escapeHTML(item.id)}')">
                    ✏️ Update Details & Vendor
                  </button>
                </div>
              </div>
            `).join('') || '<p style="color: var(--text-muted);">No vendor tasks match the active filters.</p>'
          }
        </div>
      </div>
    `;

    // Cache items for modal lookups
    state.cache.vendorItems = items;

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

function setVendorStatusFilter(val) {
  state.filter.vendorStatus = val;
  renderVendors();
}

/** 6. Render Event Ideas View */
async function renderIdeas() {
  const container = document.getElementById('ideas-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Event Ideas');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Curating personalized event recommendations...</p></div>`;

  try {
    const envelope = await API.getIdeas(state.currentEventId, state.filter.ideaCategory);
    const ideas = envelope?.data?.ideas || [];
    const source = envelope?.source || 'rules';

    container.innerHTML = `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">💡</div>
            <div>
              <h2 class="card-title">Personalized Event Ideas & Experiences</h2>
              <p class="card-subtitle">Budget-fit concepts tailored to your scale and preferences</p>
            </div>
          </div>
          <span class="badge ${source === 'gemini' ? 'badge-cyan' : 'badge-amethyst'}">SOURCE: ${escapeHTML(source.toUpperCase())}</span>
        </div>

        <div style="display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1.5rem;">
          ${['all', 'theme_atmosphere', 'catering_dining', 'entertainment_activities', 'decor_styling', 'guest_experience', 'logistics_timing', 'budget_optimization'].map(cat => `
            <button class="btn btn-sm ${state.filter.ideaCategory === cat ? 'btn-primary' : 'btn-secondary'}" onclick="setIdeaCategoryFilter('${cat}')">
              ${cat.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
            </button>
          `).join('')}
        </div>

        <div class="grid-2">
          ${
            ideas.map(item => `
              <div class="idea-card">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                  <div>
                    <span class="badge badge-amethyst">${escapeHTML(item.category.replace(/_/g, ' ').toUpperCase())}</span>
                    <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--text-primary); margin-top: 0.4rem;">${escapeHTML(item.title)}</h3>
                  </div>
                  <span class="badge badge-cyan">${escapeHTML(item.budget_fit.replace(/_/g, ' ').toUpperCase())}</span>
                </div>

                <p style="font-size: 0.875rem; color: var(--text-secondary); line-height: 1.4;">${escapeHTML(item.description)}</p>

                <div class="idea-reason-box">
                  <strong>Why it fits:</strong> ${escapeHTML(item.reason)}
                </div>

                <div>
                  <div style="font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.35rem;">Execution Tips</div>
                  <ul class="idea-tips-list">
                    ${(item.implementation_tips || []).map(tip => `<li>${escapeHTML(tip)}</li>`).join('')}
                  </ul>
                </div>

                ${item.alternatives?.length ? `
                  <div style="font-size: 0.8rem; color: var(--electric-cyan); margin-top: 0.25rem;">
                    💡 <em>Lower-cost alternative:</em> ${escapeHTML(item.alternatives[0])}
                  </div>
                ` : ''}
              </div>
            `).join('') || '<p style="color: var(--text-muted);">No ideas match the selected category.</p>'
          }
        </div>
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

function setIdeaCategoryFilter(cat) {
  state.filter.ideaCategory = cat;
  renderIdeas();
}

/** 7. Render Pre-Mortem Risk Analysis View */
async function renderRisks() {
  const container = document.getElementById('risks-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Risk Analysis');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Evaluating pre-mortem operational failure modes...</p></div>`;

  try {
    const envelope = await API.getRisks(state.currentEventId);
    const data = envelope?.data || {};
    const risks = data.risks || [];
    const summary = data.summary || {};

    container.innerHTML = `
      <!-- Risk Metrics Tiles -->
      <div class="grid-4" style="margin-bottom: 1.5rem;">
        <div class="stat-tile" style="border-left: 4px solid var(--danger);">
          <span class="stat-label">Critical Risks</span>
          <span class="stat-value" style="color: var(--danger);">${summary.critical_risks || 0}</span>
          <span class="stat-sub">Immediate focus needed</span>
        </div>
        <div class="stat-tile" style="border-left: 4px solid var(--warning);">
          <span class="stat-label">High Severity</span>
          <span class="stat-value" style="color: var(--warning);">${summary.high_risks || 0}</span>
          <span class="stat-sub">Requires active mitigation</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Medium & Low</span>
          <span class="stat-value">${(summary.medium_risks || 0) + (summary.low_risks || 0)}</span>
          <span class="stat-sub">Monitor periodically</span>
        </div>
        <div class="stat-tile">
          <span class="stat-label">Highest Priority Score</span>
          <span class="stat-value" style="color: var(--electric-cyan);">${summary.highest_priority_score || 0}/12</span>
          <span class="stat-sub">Heuristic priority weight</span>
        </div>
      </div>

      <!-- Risk Matrix Card -->
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">🛡️</div>
            <div>
              <h2 class="card-title">Pre-Mortem Failure Mode Analysis</h2>
              <p class="card-subtitle">Identifying and resolving vulnerabilities before event day</p>
            </div>
          </div>
          <span class="badge badge-amethyst">SOURCE: ${escapeHTML((envelope.source || 'rules').toUpperCase())}</span>
        </div>

        <div class="grid-2">
          ${
            risks.map(r => `
              <div class="risk-card ${r.impact === 'critical' ? 'critical' : r.impact === 'high' ? 'high' : r.impact === 'medium' ? 'medium' : 'low'}">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem;">
                  <div>
                    <span class="badge ${r.impact === 'critical' ? 'badge-danger' : 'badge-warning'}">IMPACT: ${escapeHTML(r.impact.toUpperCase())}</span>
                    <span class="badge badge-amethyst">LIKELIHOOD: ${escapeHTML(r.likelihood.toUpperCase())}</span>
                    <h3 style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary); margin-top: 0.4rem;">${escapeHTML(r.title)}</h3>
                  </div>
                  <div style="text-align: right;">
                    <span class="badge badge-cyan" style="font-size: 0.9rem; font-family: var(--font-mono); font-weight: 800;">Score: ${r.priority_score}</span>
                  </div>
                </div>

                <p style="font-size: 0.875rem; color: var(--text-secondary); line-height: 1.4;">${escapeHTML(r.description)}</p>

                ${r.warning_signs?.length ? `
                  <div style="font-size: 0.825rem;">
                    <div style="font-weight: 700; color: var(--text-muted); margin-bottom: 0.25rem;">Early Warning Signs:</div>
                    <ul style="list-style: none; padding-left: 0.5rem; color: var(--text-secondary);">
                      ${r.warning_signs.map(w => `<li>• ${escapeHTML(w)}</li>`).join('')}
                    </ul>
                  </div>
                ` : ''}

                ${r.mitigations?.length ? `
                  <div style="font-size: 0.825rem;">
                    <div style="font-weight: 700; color: var(--text-muted); margin-bottom: 0.25rem;">Recommended Mitigations:</div>
                    <ul style="list-style: none; padding-left: 0.5rem; color: #a7f3d0;">
                      ${r.mitigations.map(m => `<li>✓ ${escapeHTML(m)}</li>`).join('')}
                    </ul>
                  </div>
                ` : ''}

                <div class="contingency-box">
                  <div style="font-size: 0.775rem; font-weight: 700; text-transform: uppercase; color: var(--danger); margin-bottom: 0.2rem;">Contingency Plan</div>
                  <div style="font-size: 0.85rem; color: var(--text-primary);">${escapeHTML(r.contingency_plan)}</div>
                </div>
              </div>
            `).join('') || '<p style="color: var(--text-muted);">No risk factors detected.</p>'
          }
        </div>
      </div>

      <!-- Planning Estimates Disclaimer -->
      <div style="font-size: 0.8rem; color: var(--text-dim); text-align: center; padding: 0.5rem 1rem;">
        * ${escapeHTML(data.disclaimer || 'Risk scores and assessments are qualitative planning estimates based on current event profile parameters, not statistically calibrated probabilities or guaranteed predictions.')}
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

/** 8. Render Four-Persona Family Council View */
async function renderCouncil() {
  const container = document.getElementById('council-content');
  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Family Council');
    return;
  }

  container.innerHTML = `<div class="empty-state"><div class="empty-state-icon">⏳</div><p>Convening four-persona simulated family council...</p></div>`;

  try {
    const envelope = await API.getFamilyCouncil(state.currentEventId);
    const data = envelope?.data || {};
    const personas = data.personas || [];
    const summary = data.summary || {};

    const personaIcons = {
      budget_guardian: '🛡️',
      guest_comfort_advocate: '❤️',
      tradition_experience_keeper: '⭐',
      logistics_risk_planner: '⚙️',
    };

    container.innerHTML = `
      <!-- Council Summary Header -->
      <div class="card" style="margin-bottom: 1.5rem; background: linear-gradient(135deg, rgba(59, 10, 107, 0.4) 0%, rgba(18, 7, 34, 0.9) 100%); border-left: 4px solid var(--electric-cyan);">
        <div class="card-header">
          <div class="card-title-wrap">
            <div class="card-icon">👥</div>
            <div>
              <h2 class="card-title">Family Council Deliberation Summary</h2>
              <p class="card-subtitle">Constructive review across four distinct viewpoints without false consensus</p>
            </div>
          </div>
          <span class="badge badge-cyan">SOURCE: ${escapeHTML((envelope.source || 'rules').toUpperCase())}</span>
        </div>

        <p style="font-size: 1rem; color: var(--text-primary); margin-bottom: 1rem; line-height: 1.5;">
          ${escapeHTML(summary.overall_verdict || 'Council review in progress.')}
        </p>

        <div class="grid-3" style="font-size: 0.85rem;">
          <div style="background: var(--bg-surface-3); padding: 0.85rem; border-radius: var(--radius-md);">
            <div style="font-weight: 700; color: var(--success); margin-bottom: 0.35rem;">✓ Strongest Aspects</div>
            <ul style="list-style: none; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.25rem;">
              ${(summary.strongest_aspects || []).map(s => `<li>• ${escapeHTML(s)}</li>`).join('')}
            </ul>
          </div>

          <div style="background: var(--bg-surface-3); padding: 0.85rem; border-radius: var(--radius-md);">
            <div style="font-weight: 700; color: var(--warning); margin-bottom: 0.35rem;">⚠ Critical Concerns</div>
            <ul style="list-style: none; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.25rem;">
              ${(summary.critical_concerns || []).map(c => `<li>• ${escapeHTML(c)}</li>`).join('')}
            </ul>
          </div>

          <div style="background: var(--bg-surface-3); padding: 0.85rem; border-radius: var(--radius-md);">
            <div style="font-weight: 700; color: var(--electric-cyan); margin-bottom: 0.35rem;">→ Recommended Actions</div>
            <ul style="list-style: none; color: var(--text-secondary); display: flex; flex-direction: column; gap: 0.25rem;">
              ${(summary.next_actions || []).map(a => `<li>• ${escapeHTML(a)}</li>`).join('')}
            </ul>
          </div>
        </div>

        ${summary.trade_offs?.length ? `
          <div style="margin-top: 1.25rem; padding-top: 1rem; border-top: 1px solid var(--amethyst-border);">
            <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-primary); margin-bottom: 0.65rem;">
              Creative Trade-Offs (No False Consensus)
            </div>
            <div style="display: flex; flex-direction: column; gap: 0.65rem;">
              ${summary.trade_offs.map(t => `
                <div style="background: rgba(10, 4, 20, 0.6); padding: 0.75rem 1rem; border-radius: var(--radius-md); border-left: 3px solid var(--electric-cyan);">
                  <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: 700; margin-bottom: 0.25rem;">
                    <span style="color: var(--text-primary);">${escapeHTML(t.title)}</span>
                    <span style="color: var(--electric-cyan);">${escapeHTML(t.perspective_a)} vs. ${escapeHTML(t.perspective_b)}</span>
                  </div>
                  <div style="font-size: 0.825rem; color: var(--text-secondary); margin-bottom: 0.35rem;">${escapeHTML(t.description)}</div>
                  <div style="font-size: 0.825rem; color: #a7f3d0;"><strong>Suggested Compromise:</strong> ${escapeHTML(t.suggested_compromise)}</div>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>

      <!-- Four Distinct Persona Cards -->
      <div class="grid-2">
        ${
          personas.map(p => `
            <div class="persona-card">
              <div class="persona-header">
                <div class="persona-avatar">${personaIcons[p.persona_id] || '👤'}</div>
                <div style="flex: 1;">
                  <div style="display: flex; justify-content: space-between; align-items: center;">
                    <h3 class="persona-title">${escapeHTML(p.persona_name)}</h3>
                    <span class="badge ${p.priority === 'high' ? 'badge-danger' : p.priority === 'medium' ? 'badge-warning' : 'badge-cyan'}">
                      ${escapeHTML(p.priority.toUpperCase())}
                    </span>
                  </div>
                  <div class="persona-perspective">${escapeHTML(p.perspective)}</div>
                </div>
              </div>

              <div style="font-size: 0.875rem; color: var(--text-primary); background: var(--bg-surface-3); padding: 0.65rem 0.85rem; border-radius: var(--radius-sm); font-style: italic;">
                "${escapeHTML(p.overall_assessment)}"
              </div>

              <div>
                <div class="persona-section-title">Grounded Strengths</div>
                <ul class="persona-list strengths">
                  ${(p.strengths || []).map(s => `<li>${escapeHTML(s)}</li>`).join('')}
                </ul>
              </div>

              <div>
                <div class="persona-section-title">Concerns & Gaps</div>
                <ul class="persona-list concerns">
                  ${(p.concerns || []).map(c => `<li>${escapeHTML(c)}</li>`).join('')}
                </ul>
              </div>

              <div>
                <div class="persona-section-title">Actionable Recommendations</div>
                <ul class="persona-list recommendations">
                  ${(p.recommendations || []).map(r => `<li>${escapeHTML(r)}</li>`).join('')}
                </ul>
              </div>
            </div>
          `).join('')
        }
      </div>

      <!-- Simulated Council Disclaimer -->
      <div style="font-size: 0.8rem; color: var(--text-dim); text-align: center; margin-top: 1.5rem;">
        * ${escapeHTML(data.disclaimer || 'The Family Council provides simulated planning perspectives for exploration and discussion. It does not replace professional event planning, legal, financial, or real family decisions.')}
      </div>
    `;

  } catch (err) {
    container.innerHTML = `<div class="card" style="border-color: var(--danger);"><p style="color: var(--danger);">${escapeHTML(err.message)}</p></div>`;
  }
}

// ==============================================================================
// 5. Modals & Interactive Workflows
// ==============================================================================

function openCreateEventModal() {
  const modal = document.getElementById('modal-create-event');
  if (modal) {
    modal.classList.add('open');
    document.getElementById('create-event-name')?.focus();
  }
}

function closeCreateEventModal() {
  const modal = document.getElementById('modal-create-event');
  if (modal) modal.classList.remove('open');
}

function openEditVendorModal(itemId) {
  const modal = document.getElementById('modal-edit-vendor');
  const items = state.cache.vendorItems || [];
  const item = items.find(i => i.id === itemId);
  if (!modal || !item) return;

  document.getElementById('edit-vendor-item-id').value = item.id;
  document.getElementById('edit-vendor-task-title').textContent = `${item.id}: ${item.title}`;
  document.getElementById('edit-vendor-task-desc').textContent = item.description || '';
  document.getElementById('edit-vendor-status').value = item.status;
  document.getElementById('edit-vendor-priority').value = item.priority;
  document.getElementById('edit-vendor-booking').value = item.booking_status || 'not_started';
  document.getElementById('edit-vendor-name').value = item.vendor_name || '';
  document.getElementById('edit-vendor-notes').value = item.notes || '';

  modal.classList.add('open');
}

function closeEditVendorModal() {
  const modal = document.getElementById('modal-edit-vendor');
  if (modal) modal.classList.remove('open');
}

// ==============================================================================
// 6. Navigation & Routing
// ==============================================================================

function switchView(viewName) {
  state.activeView = viewName;

  // Update nav links
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.dataset.view === viewName);
  });

  // Update section containers
  document.querySelectorAll('.view-section').forEach(sec => {
    sec.classList.toggle('active', sec.id === `view-${viewName}`);
  });

  // Close mobile sidebar if open
  document.getElementById('sidebar')?.classList.remove('open');

  // Trigger relevant render
  switch (viewName) {
    case 'overview':
      renderOverview();
      break;
    case 'event-details':
      renderEventDetails();
      break;
    case 'budget':
      renderBudget();
      break;
    case 'timeline':
      renderTimeline();
      break;
    case 'vendors':
      renderVendors();
      break;
    case 'ideas':
      renderIdeas();
      break;
    case 'risks':
      renderRisks();
      break;
    case 'council':
      renderCouncil();
      break;
    default:
      renderOverview();
  }
}

function updateActiveEventBadge(profile) {
  const badge = document.getElementById('active-event-badge');
  const text = document.getElementById('active-event-title-text');
  if (!badge || !text) return;

  if (profile) {
    text.textContent = `${profile.event_name || profile.event_type} (${profile.event_id})`;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }
}

async function selectEvent(eventId) {
  state.currentEventId = eventId;
  const select = document.getElementById('event-select-dropdown');
  if (select) select.value = eventId;

  try {
    const profile = await API.getEvent(eventId);
    state.currentEvent = profile;
    updateActiveEventBadge(profile);
    switchView(state.activeView);
  } catch (err) {
    showToast(`Failed to select event ${eventId}`, 'error');
  }
}

async function loadEventsList() {
  const select = document.getElementById('event-select-dropdown');
  if (!select) return;

  try {
    const res = await API.listEvents();
    state.events = res.events || [];

    select.innerHTML = '';
    if (state.events.length === 0) {
      select.innerHTML = '<option value="" disabled selected>No events created yet</option>';
      state.currentEventId = null;
      updateActiveEventBadge(null);
      return;
    }

    state.events.forEach(ev => {
      const opt = document.createElement('option');
      opt.value = ev.event_id;
      opt.textContent = `${ev.event_name || ev.event_type} (${ev.event_id})`;
      select.appendChild(opt);
    });

    // Default select first if not selected
    if (!state.currentEventId || !state.events.find(e => e.event_id === state.currentEventId)) {
      state.currentEventId = state.events[0].event_id;
    }

    select.value = state.currentEventId;
    state.currentEvent = state.events.find(e => e.event_id === state.currentEventId);
    updateActiveEventBadge(state.currentEvent);

  } catch (err) {
    console.error('Error loading events:', err);
    select.innerHTML = '<option value="" disabled>Error loading events</option>';
  }
}

async function loadSystemStatus() {
  try {
    const [health, aiStatus, dataStatus] = await Promise.all([
      API.getHealth().catch(() => null),
      API.getAIStatus().catch(() => null),
      API.getDataStatus().catch(() => null),
    ]);

    state.health = health;
    state.aiStatus = aiStatus;
    state.dataStatus = dataStatus;

    // Update AI pill
    const aiPill = document.getElementById('ai-status-badge');
    const aiText = document.getElementById('ai-status-text');
    if (aiPill && aiText && aiStatus) {
      aiText.textContent = `AI: ${aiStatus.mode.toUpperCase()}${aiStatus.configured ? ' (CONNECTED)' : ''}`;
      aiPill.className = `ai-status-pill ${aiStatus.mode === 'demo' ? 'demo' : aiStatus.configured ? '' : 'offline'}`;
    }
  } catch (err) {
    console.error('System status fetch failed:', err);
  }
}

// ==============================================================================
// 7. Initialization & Event Listeners
// ==============================================================================

document.addEventListener('DOMContentLoaded', async () => {
  // 1. Sidebar navigation click bindings
  document.querySelectorAll('.nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      const view = link.dataset.view;
      window.location.hash = view;
      switchView(view);
    });
  });

  // 2. Hash routing
  window.addEventListener('hashchange', () => {
    const hash = window.location.hash.replace('#', '') || 'overview';
    switchView(hash);
  });

  // 3. Mobile sidebar toggle
  document.getElementById('btn-sidebar-toggle')?.addEventListener('click', () => {
    document.getElementById('sidebar')?.classList.toggle('open');
  });

  // 4. Event Selector Dropdown
  document.getElementById('event-select-dropdown')?.addEventListener('change', (e) => {
    selectEvent(e.target.value);
  });

  // 5. Create Event Modal triggers
  document.getElementById('btn-open-create-event')?.addEventListener('click', openCreateEventModal);
  document.getElementById('btn-close-create-modal')?.addEventListener('click', closeCreateEventModal);
  document.getElementById('btn-cancel-create-modal')?.addEventListener('click', closeCreateEventModal);

  // 6. Create Event Form Submit
  document.getElementById('form-create-event')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-create-event');
    btn.textContent = 'Creating...';
    btn.disabled = true;

    const payload = {
      event_type: document.getElementById('create-event-type').value,
      event_name: document.getElementById('create-event-name').value.trim() || null,
      city: document.getElementById('create-city').value.trim() || null,
      city_tier: document.getElementById('create-city-tier').value,
      event_date: document.getElementById('create-event-date').value || null,
      guest_count: parseInt(document.getElementById('create-guest-count').value, 10),
      total_budget_inr: parseInt(document.getElementById('create-budget').value, 10),
      language: document.getElementById('create-language').value,
      is_in_progress: document.getElementById('create-in-progress').checked,
      theme_notes: document.getElementById('create-theme-notes').value.trim(),
    };

    try {
      const created = await API.createEvent(payload);
      showToast(`Event profile '${created.event_id}' created successfully!`, 'success');
      closeCreateEventModal();
      document.getElementById('form-create-event').reset();

      await loadEventsList();
      await selectEvent(created.event_id);
      window.location.hash = 'overview';
      switchView('overview');
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.textContent = 'Create & Plan Event';
      btn.disabled = false;
    }
  });

  // 7. Edit Vendor Checklist Item Modal triggers
  document.getElementById('btn-close-vendor-modal')?.addEventListener('click', closeEditVendorModal);
  document.getElementById('btn-cancel-vendor-modal')?.addEventListener('click', closeEditVendorModal);

  document.getElementById('form-edit-vendor')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('btn-submit-edit-vendor');
    btn.textContent = 'Saving...';
    btn.disabled = true;

    const itemId = document.getElementById('edit-vendor-item-id').value;
    const payload = {
      status: document.getElementById('edit-vendor-status').value,
      priority: document.getElementById('edit-vendor-priority').value,
      booking_status: document.getElementById('edit-vendor-booking').value,
      vendor_name: document.getElementById('edit-vendor-name').value.trim() || null,
      notes: document.getElementById('edit-vendor-notes').value.trim() || null,
    };

    try {
      await API.updateVendorItem(state.currentEventId, itemId, payload);
      showToast('Vendor task updated', 'success');
      closeEditVendorModal();
      renderVendors();
    } catch (err) {
      showToast(err.message, 'error');
    } finally {
      btn.textContent = 'Save Changes';
      btn.disabled = false;
    }
  });

  // 8. Bootstrap Initial State
  await loadSystemStatus();
  await loadEventsList();

  const initialHash = window.location.hash.replace('#', '') || 'overview';
  switchView(initialHash);
});
