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
  crisisTypes: [],
  crisisResult: null,
  crisisSeverity: 2,
  recoveryRecords: [],
  selectedRecoveryId: null,
  selectedRecovery: null,
  isLoadingRecoveries: false,
  readiness: null,
  isLoadingReadiness: false,
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

  getCrisisTypes() {
    return this.request('/api/v1/crisis/types');
  },

  evaluateCrisis(eventId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/evaluate`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  saveRecoveryRecord(eventId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/recoveries`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  getRecoveryRecords(eventId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/recoveries`);
  },

  getRecoveryRecord(eventId, recoveryId) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/recoveries/${encodeURIComponent(recoveryId)}`);
  },

  updateRecoveryRecord(eventId, recoveryId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/recoveries/${encodeURIComponent(recoveryId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  updateRecoveryAction(eventId, recoveryId, actionId, payload) {
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/crisis/recoveries/${encodeURIComponent(recoveryId)}/actions/${encodeURIComponent(actionId)}`, {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
  },

  getReadiness(eventId, referenceDate = null) {
    const q = referenceDate ? `?reference_date=${encodeURIComponent(referenceDate)}` : '';
    return this.request(`/api/v1/events/${encodeURIComponent(eventId)}/readiness${q}`);
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
    const [profile, budgetPlan, timeline, vendors, risks, council, readiness] = await Promise.all([
      API.getEvent(state.currentEventId),
      API.getBudget(state.currentEventId).catch(() => null),
      API.getTimeline(state.currentEventId).catch(() => null),
      API.getVendors(state.currentEventId).catch(() => null),
      API.getRisks(state.currentEventId).catch(() => null),
      API.getFamilyCouncil(state.currentEventId).catch(() => null),
      API.getReadiness(state.currentEventId).catch(() => null),
    ]);

    state.currentEvent = profile;
    if (readiness) state.readiness = readiness;
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
        if (cat === 'total_budget_inr') continue;
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

      <!-- Readiness Score Banner -->
      ${readiness ? `
        <div class="overview-readiness-banner" onclick="switchView('readiness')" role="button" tabindex="0" aria-label="View Event Readiness Assessment">
          <div style="display: flex; align-items: center; gap: 1.25rem;">
            <div style="width: 54px; height: 54px; border-radius: 50%; border: 3px solid ${readiness.overall_score >= 80 ? '#10B981' : (readiness.overall_score >= 60 ? 'var(--electric-cyan)' : '#F59E0B')}; display: flex; align-items: center; justify-content: center; font-family: var(--font-mono); font-weight: 900; font-size: 1.3rem; color: var(--text-primary); background: var(--bg-surface-2);">
              ${readiness.overall_score !== null ? readiness.overall_score : '—'}
            </div>
            <div>
              <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
                <span style="font-weight: 800; font-size: 1.05rem; color: var(--text-primary);">Event Readiness Score</span>
                <span class="badge ${readiness.overall_score >= 80 ? 'badge-success' : 'badge-warning'}" style="font-size: 0.75rem;">
                  ${readiness.readiness_status.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <div style="font-size: 0.85rem; color: var(--text-muted);">
                ${readiness.critical_concerns.length > 0 
                  ? `⚠️ ${readiness.critical_concerns.length} critical concern(s) require attention · Click to view diagnostics`
                  : `${readiness.completed_items} completed items · Click to view full readiness assessment`}
              </div>
            </div>
          </div>
          <button type="button" class="btn btn-cyan btn-sm">
            View Assessment ➔
          </button>
        </div>
      ` : ''}

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
      if (cat === 'total_budget_inr') continue;
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
// 5.9 Crisis Recovery Center View & Handlers
// ==============================================================================

function highlightPlaceholders(text) {
  if (!text) return '';
  const escaped = escapeHTML(text);
  return escaped.replace(/\[([^\]]+)\]/g, '<mark>[$1]</mark>');
}

function selectCrisisSeverity(sev) {
  state.crisisSeverity = Number(sev);
  document.querySelectorAll('.crisis-severity-btn').forEach((btn, idx) => {
    const s = idx + 1;
    btn.className = `crisis-severity-btn ${s === state.crisisSeverity ? `active sev-${s}` : ''}`;
  });
}

function onCrisisTypeChange(val) {
  const typeObj = (state.crisisTypes || []).find(t => t.crisis_type === val);
  if (typeObj) {
    const areaSelect = document.getElementById('crisis-affected-area');
    if (areaSelect && typeObj.affected_area) {
      areaSelect.value = typeObj.affected_area;
    }
    if (typeObj.typical_severity) {
      selectCrisisSeverity(typeObj.typical_severity);
    }
  }
}

async function handleCrisisFormSubmit(evt) {
  if (evt) evt.preventDefault();
  if (!state.currentEventId) {
    showToast('Please select or create an event first', 'error');
    return;
  }

  const type = document.getElementById('crisis-select-type')?.value || 'rain';
  const area = document.getElementById('crisis-affected-area')?.value || 'weather';
  const phase = document.getElementById('crisis-event-phase')?.value || 'event_day';
  const desc = document.getElementById('crisis-user-desc')?.value?.trim() || null;
  const severity = state.crisisSeverity || 2;

  const btn = document.getElementById('btn-submit-crisis-eval');
  const originalText = btn ? btn.innerHTML : '';
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span>⏳</span><span>Evaluating Scenario & Playbook...</span>';
  }

  try {
    const payload = {
      crisis_type: type,
      severity: severity,
      affected_area: area,
      event_phase: phase,
      description: desc,
    };
    const response = await API.evaluateCrisis(state.currentEventId, payload);
    state.crisisResult = response;
    renderCrisis();
    showToast('Crisis recovery playbook generated successfully!', 'success');
  } catch (err) {
    console.error('Crisis evaluation failed:', err);
    showToast(err.message || 'Failed to evaluate crisis scenario', 'error');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = originalText;
    }
  }
}

function resetCrisisEvaluation() {
  state.crisisResult = null;
  renderCrisis();
}

function copyDraftById(elementId, btn) {
  const el = document.getElementById(elementId);
  if (!el) return;
  const text = el.innerText || el.textContent;
  copyDraftToClipboard(text, btn);
}

function copyDraftToClipboard(text, btn) {
  if (!text) return;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(() => {
      onCopySuccess(btn);
    }).catch(() => {
      fallbackCopy(text, btn);
    });
  } else {
    fallbackCopy(text, btn);
  }
}

function fallbackCopy(text, btn) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {
    document.execCommand('copy');
    onCopySuccess(btn);
  } catch (e) {
    showToast('Failed to copy text to clipboard', 'error');
  }
  document.body.removeChild(ta);
}

function onCopySuccess(btn) {
  if (btn) {
    const originalText = btn.innerHTML;
    btn.classList.add('copied');
    btn.innerHTML = '<span>✓</span><span>Copied to Clipboard</span>';
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = originalText;
    }, 2500);
  }
  showToast('Draft copied to clipboard!', 'success');
}

async function renderCrisis() {
  const container = document.getElementById('crisis-content');
  if (!container) return;

  if (!state.currentEvent) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🚨</div>
        <h3 class="empty-title">No Active Event Selected</h3>
        <p class="empty-desc">Select an event from the top dropdown or create a new event to activate the Crisis Recovery Center.</p>
        <button class="btn btn-cyan" onclick="openCreateEventModal()">+ Create Event</button>
      </div>
    `;
    return;
  }

  // Load crisis types if not already fetched
  if (!state.crisisTypes || state.crisisTypes.length === 0) {
    try {
      state.crisisTypes = await API.getCrisisTypes();
    } catch (err) {
      console.error('Failed to load crisis types:', err);
    }
  }

  const ev = state.currentEvent;
  const types = state.crisisTypes || [];
  const result = state.crisisResult;

  let resultHtml = '';
  if (result && result.data) {
    const d = result.data;
    const isP1Safety = d.immediate_actions && d.immediate_actions.some(a => a.category === 'immediate_safety');

    resultHtml = `
      <div class="crisis-hero-banner">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.5rem; flex-wrap: wrap;">
              <span class="badge ${d.severity === 3 ? 'badge-danger' : d.severity === 2 ? 'badge-warning' : 'badge-cyan'}">
                SEVERITY ${d.severity}: ${d.severity === 3 ? 'CRITICAL DISRUPTION' : d.severity === 2 ? 'MODERATE IMPACT' : 'MINOR ADJUSTMENT'}
              </span>
              <span class="dataset-provenance-pill ${d.matched_scenario.is_dataset_match ? '' : 'fallback'}">
                ${d.matched_scenario.is_dataset_match ? `✓ Matched Dataset Scenario: ${escapeHTML(d.matched_scenario.scenario_id)}` : '⚡ Calibrated Operational Fallback'}
              </span>
            </div>
            <h2 style="font-size: 1.4rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.35rem;">
              ${escapeHTML(d.crisis_summary)}
            </h2>
            <div style="font-size: 0.85rem; color: var(--text-secondary);">
              Affected Operational Sector: <strong style="color: var(--electric-cyan);">${escapeHTML(d.affected_area.replace('_', ' ').toUpperCase())}</strong>
              · Event Phase: <strong>${escapeHTML(d.event_phase.replace('_', ' ').toUpperCase())}</strong>
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem; flex-wrap: wrap;">
            <button class="btn btn-cyan btn-sm" id="btn-save-crisis-recovery" onclick="openSaveRecoveryModal()">
              💾 Save Plan & Track Actions
            </button>
            <button class="btn btn-secondary btn-sm" onclick="resetCrisisEvaluation()">
              🔄 Evaluate New Scenario
            </button>
          </div>
        </div>

        ${isP1Safety ? `
          <div class="safety-triage-box">
            <div class="safety-triage-icon">⚠️</div>
            <div>
              <div class="safety-triage-title">Priority 1 Immediate Life Safety & Emergency Protocol</div>
              <div class="safety-triage-desc">
                ${escapeHTML(d.immediate_actions.find(a => a.category === 'immediate_safety')?.action || 'Ensure immediate physical safety of all guests.')}
              </div>
            </div>
          </div>
        ` : ''}
      </div>

      <!-- Grid: Immediate Actions & Budget Impact -->
      <div class="grid-2" style="margin-bottom: 2rem;">
        <!-- Column 1: Immediate & Next Actions -->
        <div>
          <h3 style="font-size: 1.15rem; font-weight: 800; color: var(--text-primary); margin-bottom: 1rem; display: flex; align-items: center; gap: 0.5rem;">
            <span>⚡</span><span>Prioritized Operational Actions</span>
          </h3>

          <div style="margin-bottom: 1rem;">
            ${(d.immediate_actions || []).map(a => `
              <div class="action-item-card p${a.priority}">
                <div class="action-meta-row">
                  <span class="badge-priority p${a.priority}">Priority ${a.priority} · Immediate</span>
                  <span class="badge-responsible">👤 ${escapeHTML(a.responsible_party)}</span>
                  <span class="badge-timeframe">⏱️ ${escapeHTML(a.timeframe)}</span>
                </div>
                <div class="action-title">${escapeHTML(a.title)}</div>
                <div class="action-instruction">${escapeHTML(a.action)}</div>
              </div>
            `).join('')}
          </div>

          ${(d.next_step_actions && d.next_step_actions.length > 0) ? `
            <div style="margin-top: 1.5rem;">
              <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--text-secondary); margin-bottom: 0.75rem;">
                Secondary Continuity Steps
              </h4>
              ${d.next_step_actions.map(a => `
                <div class="action-item-card p${a.priority}">
                  <div class="action-meta-row">
                    <span class="badge-priority p${a.priority}">Priority ${a.priority} · Secondary</span>
                    <span class="badge-responsible">👤 ${escapeHTML(a.responsible_party)}</span>
                    <span class="badge-timeframe">⏱️ ${escapeHTML(a.timeframe)}</span>
                  </div>
                  <div class="action-title">${escapeHTML(a.title)}</div>
                  <div class="action-instruction">${escapeHTML(a.action)}</div>
                </div>
              `).join('')}
            </div>
          ` : ''}
        </div>

        <!-- Column 2: Budget Impact & Timeline Linkages -->
        <div>
          <!-- Budget Impact Box -->
          <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-header">
              <h3 class="card-title">💰 Budget Impact & Contingency Analysis</h3>
              <span class="badge ${d.budget_impact.buffer_sufficient ? 'badge-success' : 'badge-danger'}">
                ${d.budget_impact.buffer_sufficient ? 'Buffer Absorbs Impact' : 'Deficit / Rebalance Required'}
              </span>
            </div>
            
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: 1rem;">
              <div style="background: var(--bg-surface-2); padding: 0.85rem; border-radius: var(--radius-md); border: 1px solid var(--amethyst-border);">
                <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Estimated Rupee Impact</div>
                <div style="font-size: 1.25rem; font-weight: 800; color: ${d.budget_impact.estimated_rupee_impact > 0 ? '#ff6b6b' : 'var(--success)'}; font-family: var(--font-mono);">
                  ${d.budget_impact.estimated_rupee_impact > 0 ? '+' : ''}${formatINR(d.budget_impact.estimated_rupee_impact)}
                </div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem;">
                  ${d.budget_impact.cost_impact_pct > 0 ? '+' : ''}${d.budget_impact.cost_impact_pct.toFixed(1)}% of total budget
                </div>
              </div>

              <div style="background: var(--bg-surface-2); padding: 0.85rem; border-radius: var(--radius-md); border: 1px solid var(--amethyst-border);">
                <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">Available Contingency Buffer</div>
                <div style="font-size: 1.25rem; font-weight: 800; color: var(--electric-cyan); font-family: var(--font-mono);">
                  ${formatINR(d.budget_impact.existing_buffer_inr)}
                </div>
                <div style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 0.2rem;">
                  Emergency reserve cushion
                </div>
              </div>
            </div>

            <div style="font-size: 0.875rem; color: var(--text-primary); line-height: 1.5; background: var(--bg-surface-2); padding: 0.85rem; border-radius: var(--radius-md); margin-bottom: 0.75rem;">
              ${escapeHTML(d.budget_impact.advice)}
            </div>

            <div style="font-size: 0.8rem; color: var(--text-muted);">
              Impacted Budget Lines: ${(d.budget_impact.affected_categories || []).map(c => `<strong style="color: var(--text-secondary);">${escapeHTML(c)}</strong>`).join(', ')}
            </div>
          </div>

          <!-- Timeline & Vendor Links -->
          <div class="card" style="margin-bottom: 1.5rem;">
            <div class="card-header">
              <h3 class="card-title">🔗 Event Linkages & Checklists</h3>
            </div>

            <div style="margin-bottom: 1rem;">
              <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 0.5rem;">
                Affected Vendor Checklist Tasks (${d.relevant_vendor_checklist_ids.length})
              </div>
              ${d.relevant_vendor_checklist_ids.length > 0 ? `
                <div style="display: flex; flex-wrap: wrap; gap: 0.5rem;">
                  ${d.relevant_vendor_checklist_ids.map(id => `
                    <span style="font-family: var(--font-mono); font-size: 0.75rem; padding: 0.3rem 0.6rem; border-radius: var(--radius-sm); background: rgba(59, 10, 107, 0.4); border: 1px solid var(--amethyst-border); color: var(--text-primary);">
                      📋 ${escapeHTML(id)}
                    </span>
                  `).join('')}
                </div>
              ` : `
                <div style="font-size: 0.85rem; color: var(--text-muted); font-style: italic;">No direct vendor checklist tasks flagged.</div>
              `}
            </div>

            <div>
              <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase; margin-bottom: 0.5rem;">
                Timeline Milestone Advisory
              </div>
              <ul style="padding-left: 1.25rem; font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">
                ${(d.timeline_implications || []).map(t => `<li>${escapeHTML(t)}</li>`).join('')}
              </ul>
            </div>
          </div>

          <!-- Practical Alternatives -->
          <div class="card">
            <div class="card-header">
              <h3 class="card-title">💡 Practical Alternatives & Contingencies</h3>
            </div>
            <ul style="padding-left: 1.25rem; font-size: 0.875rem; color: var(--text-primary); line-height: 1.6;">
              ${(d.alternatives || []).map(alt => `<li>${escapeHTML(alt)}</li>`).join('')}
            </ul>
          </div>
        </div>
      </div>

      <!-- Communication Drafts -->
      <div style="margin-bottom: 2rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem;">
          <div>
            <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--text-primary);">
              📢 Stakeholder Communication Drafts
            </h3>
            <div style="font-size: 0.85rem; color: var(--text-muted);">
              Concise, respectful messaging with bracketed placeholders. Ready to copy for WhatsApp or SMS.
            </div>
          </div>
          <span class="badge badge-cyan">
            Source: ${escapeHTML(d.communication_drafts[0]?.source || 'deterministic').toUpperCase()}
          </span>
        </div>

        <div class="grid-2">
          ${(d.communication_drafts || []).map((draft, idx) => `
            <div class="crisis-draft-card">
              <div class="crisis-draft-header">
                <div>
                  <span class="crisis-draft-role">${escapeHTML(draft.recipient_role)}</span>
                  <div style="font-weight: 700; font-size: 0.95rem; color: var(--text-primary);">
                    ${escapeHTML(draft.recipient_label)}
                  </div>
                </div>
                <span class="badge ${draft.recipient_role === 'vendor' ? 'badge-danger' : draft.recipient_role === 'guests' ? 'badge-cyan' : 'badge-warning'}">
                  ${escapeHTML(draft.recipient_role.toUpperCase())}
                </span>
              </div>

              <div class="crisis-draft-text-box" id="draft-text-${idx}">${highlightPlaceholders(draft.message_text)}</div>

              <button class="btn-copy-draft" type="button" onclick="copyDraftById('draft-text-${idx}', this)">
                <span>📋</span>
                <span>Copy Message Draft</span>
              </button>
            </div>
          `).join('')}
        </div>
      </div>

      <!-- Escalation & Safety Guidance -->
      <div class="card" style="border-color: rgba(239, 68, 68, 0.4); margin-bottom: 1.5rem;">
        <div class="card-header">
          <h3 class="card-title" style="color: #ff6b6b;">🚨 Emergency Escalation Guidance</h3>
        </div>
        <div style="font-size: 0.875rem; color: var(--text-primary); line-height: 1.6; white-space: pre-wrap;">
          ${escapeHTML(d.escalation_guidance)}
        </div>
      </div>

      <!-- Disclaimer -->
      <div style="font-size: 0.8rem; color: var(--text-dim); text-align: center; margin-top: 1rem; line-height: 1.5;">
        ${escapeHTML(d.disclaimer)}
      </div>
    `;
  }

  // Render reporting intake form + results
  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1 class="view-title">🚨 Interactive Crisis Recovery Center</h1>
        <p class="view-subtitle">
          Rapid emergency response grounded in 5,000 validated crisis scenarios, deterministic budget protection, and stakeholder communication playbooks.
        </p>
      </div>
    </div>

    <!-- Crisis Intake Reporting Form -->
    <div class="crisis-form-card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; flex-wrap: wrap; gap: 0.5rem;">
        <h2 style="font-size: 1.15rem; font-weight: 800; color: var(--text-primary); display: flex; align-items: center; gap: 0.5rem;">
          <span>⚡</span><span>Report or Simulate an Event Crisis</span>
        </h2>
        <div style="font-size: 0.85rem; color: var(--text-muted);">
          Active: <strong style="color: var(--electric-cyan);">${escapeHTML(ev.event_name || ev.event_type)}</strong> (₹${(ev.total_budget_inr || 0).toLocaleString('en-IN')})
        </div>
      </div>

      <form id="form-crisis-eval" onsubmit="handleCrisisFormSubmit(event)">
        <div class="form-grid-3">
          <div class="form-group">
            <label for="crisis-select-type" class="form-label">Crisis Category</label>
            <select id="crisis-select-type" class="form-select" onchange="onCrisisTypeChange(this.value)">
              ${types.map(t => `
                <option value="${escapeHTML(t.crisis_type)}">
                  ${escapeHTML(t.title)} (${escapeHTML(t.affected_area)})
                </option>
              `).join('')}
            </select>
          </div>

          <div class="form-group">
            <label class="form-label">Disruption Severity</label>
            <div class="crisis-severity-picker">
              <button type="button" class="crisis-severity-btn ${state.crisisSeverity === 1 ? 'active sev-1' : ''}" onclick="selectCrisisSeverity(1)">
                <span>🟢</span><span>Minor (1)</span>
              </button>
              <button type="button" class="crisis-severity-btn ${state.crisisSeverity === 2 ? 'active sev-2' : ''}" onclick="selectCrisisSeverity(2)">
                <span>🟡</span><span>Moderate (2)</span>
              </button>
              <button type="button" class="crisis-severity-btn ${state.crisisSeverity === 3 ? 'active sev-3' : ''}" onclick="selectCrisisSeverity(3)">
                <span>🔴</span><span>Critical (3)</span>
              </button>
            </div>
          </div>

          <div class="form-group">
            <label for="crisis-affected-area" class="form-label">Affected Area</label>
            <select id="crisis-affected-area" class="form-select">
              <option value="catering">Catering & Food Service</option>
              <option value="venue">Venue & Facilities</option>
              <option value="weather">Weather & Lawn Outdoors</option>
              <option value="power">Power & Grid Infrastructure</option>
              <option value="sound">Sound & AV Systems</option>
              <option value="photography">Photography & Media</option>
              <option value="decor">Decor & Mandap Rigging</option>
              <option value="guest_attendance">Guest Turnout & Seating</option>
              <option value="budget">Budget & Financial Contingency</option>
              <option value="hospitality">Hospitality & VIP Protocols</option>
            </select>
          </div>
        </div>

        <div class="form-grid-2">
          <div class="form-group">
            <label for="crisis-event-phase" class="form-label">Event Lifecycle Phase</label>
            <select id="crisis-event-phase" class="form-select">
              <option value="event_day">Event Day (Active Execution)</option>
              <option value="day_before">Day Before (T-24h Final Prep)</option>
              <option value="planning">Planning Phase (Advance Weeks)</option>
            </select>
          </div>

          <div class="form-group">
            <label for="crisis-user-desc" class="form-label">Incident Details / Host Notes (Optional)</label>
            <input type="text" id="crisis-user-desc" class="form-input" placeholder="e.g. Sudden thunderstorm hitting open lawn buffet at 19:30" maxlength="300">
          </div>
        </div>

        <div style="display: flex; justify-content: flex-end; margin-top: 0.5rem;">
          <button type="submit" class="btn btn-cyan" id="btn-submit-crisis-eval">
            <span>🚨</span>
            <span>Evaluate Crisis & Generate Playbook</span>
          </button>
        </div>
      </form>
    </div>

    <!-- Crisis Results Section -->
    <div id="crisis-results-viewport">
      ${resultHtml}
    </div>
  `;
}

// ==============================================================================
// 5.10 Crisis Recovery History & Action Tracker View
// ==============================================================================

function getCrisisIcon(type) {
  const map = {
    rain: '🌧️',
    power_cut: '⚡',
    caterer_cancel: '🍽️',
    caterer_late: '⏳',
    venue_double_booked: '🏛️',
    photographer_noshow: '📸',
    sound_failure: '🔊',
    decorator_delay: '🌸',
    medical_emergency: '🚑',
    police_licensing_issue: '👮',
    transport_breakdown: '🚌',
    fire_kitchen_hazard: '🔥',
    guest_surge: '👥',
    guest_dropout: '📉',
    budget_overrun: '💸',
  };
  return map[type] || '🚨';
}

function openSaveRecoveryModal() {
  if (!state.crisisResult || !state.crisisResult.data) {
    showToast('No crisis evaluation result available to save.', 'warning');
    return;
  }
  const d = state.crisisResult.data;
  const actionsListEl = document.getElementById('save-recovery-actions-list');
  const descInput = document.getElementById('save-recovery-desc');

  if (descInput) {
    descInput.value = d.crisis_summary || '';
  }

  const allActions = [
    ...(d.immediate_actions || []),
    ...(d.next_step_actions || []),
  ];

  if (actionsListEl) {
    if (allActions.length === 0) {
      actionsListEl.innerHTML = '<div style="font-size: 0.85rem; color: var(--text-muted); padding: 0.5rem;">No actions recommended in this plan.</div>';
    } else {
      actionsListEl.innerHTML = allActions.map((act, idx) => `
        <div class="action-select-item">
          <input type="checkbox" id="check-act-${idx}" class="recovery-action-check" data-idx="${idx}" checked>
          <label for="check-act-${idx}" class="action-select-label">
            <div class="action-select-title">
              <span class="badge ${act.priority === 1 ? 'badge-danger' : 'badge-warning'}" style="font-size: 0.7rem; padding: 0.1rem 0.35rem; margin-right: 0.35rem;">P${act.priority}</span>
              ${escapeHTML(act.title)}
            </div>
            <div class="action-select-desc">${escapeHTML(act.action)}</div>
          </label>
        </div>
      `).join('');
    }
  }

  const modal = document.getElementById('modal-save-recovery');
  if (modal) modal.classList.add('open');
}

function closeSaveRecoveryModal() {
  const modal = document.getElementById('modal-save-recovery');
  if (modal) modal.classList.remove('open');
}

async function handleSaveRecoverySubmit(evt) {
  evt.preventDefault();
  if (!state.currentEventId) {
    showToast('Please select an active event first.', 'error');
    return;
  }
  if (!state.crisisResult || !state.crisisResult.data) {
    showToast('No active crisis plan found.', 'error');
    return;
  }

  const d = state.crisisResult.data;
  const desc = document.getElementById('save-recovery-desc')?.value?.trim() || d.crisis_summary;
  const allActions = [
    ...(d.immediate_actions || []),
    ...(d.next_step_actions || []),
  ];

  const selected = [];
  document.querySelectorAll('.recovery-action-check:checked').forEach(cb => {
    const idx = parseInt(cb.dataset.idx, 10);
    if (!isNaN(idx) && allActions[idx]) {
      const act = allActions[idx];
      selected.push({
        title: act.title,
        description: act.action,
        priority: act.priority || 2,
        status: 'pending',
      });
    }
  });

  const payload = {
    crisis_type: d.matched_scenario ? d.matched_scenario.crisis_type : 'rain',
    severity: d.severity,
    description: desc,
    recovery_plan: d,
    source: state.crisisResult.source || 'rules',
    status: 'open',
    actions: selected.length > 0 ? selected : undefined,
  };

  const btn = document.getElementById('btn-confirm-save-recovery');
  if (btn) btn.disabled = true;

  try {
    const saved = await API.saveRecoveryRecord(state.currentEventId, payload);
    closeSaveRecoveryModal();
    showToast('Recovery plan saved to history! Tracking initialized.', 'success');
    state.selectedRecoveryId = saved.recovery_id;
    state.selectedRecovery = saved;
    window.location.hash = 'recovery-history';
    switchView('recovery-history');
  } catch (err) {
    console.error('Failed to save recovery record:', err);
    showToast(err.message || 'Failed to save recovery record', 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function selectRecoveryRecord(recId) {
  state.selectedRecoveryId = recId;
  state.selectedRecovery = null;
  renderRecoveryHistory();
}

async function handleRecoveryStatusChange(recoveryId, newStatus) {
  try {
    const updated = await API.updateRecoveryRecord(state.currentEventId, recoveryId, { status: newStatus });
    showToast(`Recovery status updated to ${newStatus.replace('_', ' ')}.`, 'success');
    state.selectedRecovery = updated;
    renderRecoveryHistory();
  } catch (err) {
    console.error('Failed to update recovery status:', err);
    showToast(err.message || 'Failed to update recovery status', 'error');
  }
}

async function handleActionStatusChange(recoveryId, actionId, newStatus) {
  try {
    await API.updateRecoveryAction(state.currentEventId, recoveryId, actionId, { status: newStatus });
    showToast(`Action updated to ${newStatus.replace('_', ' ')}.`, 'success');
    renderRecoveryHistory();
  } catch (err) {
    console.error('Failed to update action status:', err);
    showToast(err.message || 'Failed to update action status', 'error');
  }
}

async function handleActionNotesSave(recoveryId, actionId) {
  const input = document.getElementById(`action-notes-${actionId}`);
  const notesVal = input ? input.value.trim() : null;

  try {
    await API.updateRecoveryAction(state.currentEventId, recoveryId, actionId, { notes: notesVal });
    showToast('Action notes updated successfully.', 'success');
    renderRecoveryHistory();
  } catch (err) {
    console.error('Failed to save action notes:', err);
    showToast(err.message || 'Failed to save action notes', 'error');
  }
}

async function renderRecoveryHistory() {
  const container = document.getElementById('recovery-history-content');
  if (!container) return;

  const ev = state.currentEvent;
  if (!state.currentEventId || !ev) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">📜</div>
        <h2 class="empty-title">No Active Event Selected</h2>
        <p class="empty-desc">Select an event from the top dropdown or create a new event to view recovery history and track actions.</p>
        <button class="btn btn-cyan btn-sm" onclick="openCreateEventModal()">+ Create New Event</button>
      </div>
    `;
    return;
  }

  // 1. Detail View: If a specific recovery record is selected
  if (state.selectedRecoveryId) {
    container.innerHTML = `
      <div class="view-header">
        <div>
          <button class="btn btn-secondary btn-sm" onclick="selectRecoveryRecord(null)" style="margin-bottom: 0.75rem;">
            ← Back to All Recovery Records
          </button>
          <h1 class="view-title">Loading Recovery Record...</h1>
        </div>
      </div>
      <div class="loading-state"><div class="spinner"></div></div>
    `;

    try {
      const record = await API.getRecoveryRecord(state.currentEventId, state.selectedRecoveryId);
      state.selectedRecovery = record;
      renderRecoveryDetailView(container, record);
    } catch (err) {
      console.error('Failed to load recovery record:', err);
      container.innerHTML = `
        <div class="view-header">
          <button class="btn btn-secondary btn-sm" onclick="selectRecoveryRecord(null)" style="margin-bottom: 0.75rem;">
            ← Back to All Recovery Records
          </button>
        </div>
        <div class="empty-state">
          <div class="empty-icon">⚠️</div>
          <h2 class="empty-title">Error Loading Recovery Record</h2>
          <p class="empty-desc">${escapeHTML(err.message || 'The requested recovery record could not be loaded.')}</p>
          <button class="btn btn-secondary btn-sm" onclick="selectRecoveryRecord('${escapeHTML(state.selectedRecoveryId)}')">Retry</button>
        </div>
      `;
    }
    return;
  }

  // 2. List View: Fetch all recovery records for the active event
  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1 class="view-title" id="recovery-history-heading">📜 Crisis Recovery History & Action Tracker</h1>
        <p class="view-subtitle">Review previously evaluated crisis responses, track action item completion, and monitor resolution progress.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-cyan btn-sm" onclick="switchView('crisis')">
          🚨 Evaluate New Crisis
        </button>
      </div>
    </div>
    <div class="loading-state"><div class="spinner"></div></div>
  `;

  try {
    const records = await API.getRecoveryRecords(state.currentEventId);
    state.recoveryRecords = records || [];
    renderRecoveryListView(container, state.recoveryRecords);
  } catch (err) {
    console.error('Failed to list recovery records:', err);
    container.innerHTML = `
      <div class="view-header">
        <div>
          <h1 class="view-title" id="recovery-history-heading">📜 Crisis Recovery History & Action Tracker</h1>
          <p class="view-subtitle">Review previously evaluated crisis responses, track action item completion, and monitor resolution progress.</p>
        </div>
      </div>
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <h2 class="empty-title">Failed to Load Recovery History</h2>
        <p class="empty-desc">${escapeHTML(err.message || 'Unable to retrieve recovery history from server.')}</p>
        <button class="btn btn-cyan btn-sm" onclick="renderRecoveryHistory()">Retry</button>
      </div>
    `;
  }
}

function renderRecoveryListView(container, records) {
  if (!records || records.length === 0) {
    container.innerHTML = `
      <div class="view-header">
        <div>
          <h1 class="view-title" id="recovery-history-heading">📜 Crisis Recovery History & Action Tracker</h1>
          <p class="view-subtitle">Review previously evaluated crisis responses, track action item completion, and monitor resolution progress.</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-cyan btn-sm" onclick="switchView('crisis')">
            🚨 Evaluate New Crisis
          </button>
        </div>
      </div>

      <div class="empty-state" style="background: var(--bg-surface-2); border: 1px solid var(--amethyst-border); border-radius: var(--radius-lg); padding: 3rem 1.5rem;">
        <div class="empty-icon" style="font-size: 3rem; margin-bottom: 1rem;">🛡️</div>
        <h2 class="empty-title" style="font-size: 1.25rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.5rem;">No Crisis Recovery Records Saved</h2>
        <p class="empty-desc" style="max-width: 520px; margin: 0 auto 1.5rem; color: var(--text-secondary); line-height: 1.6;">
          When unexpected disruptions occur, evaluate them in the <strong>Crisis Recovery Center</strong> and click <em>"Save Plan & Track Actions"</em> to track actionable mitigation steps here.
        </p>
        <button class="btn btn-cyan" onclick="switchView('crisis')">
          🚨 Open Crisis Recovery Center
        </button>
      </div>
    `;
    return;
  }

  const totalRecs = records.length;
  const resolvedCount = records.filter(r => r.status === 'resolved').length;
  const inProgressCount = records.filter(r => r.status === 'in_progress').length;
  const openCount = records.filter(r => r.status === 'open').length;

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1 class="view-title" id="recovery-history-heading">📜 Crisis Recovery History & Action Tracker</h1>
        <p class="view-subtitle">Review previously evaluated crisis responses, track action item completion, and monitor resolution progress.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-cyan btn-sm" onclick="switchView('crisis')">
          🚨 Evaluate New Crisis
        </button>
      </div>
    </div>

    <!-- Summary Metrics -->
    <div class="recovery-summary-metrics">
      <div class="recovery-metric-box">
        <div class="recovery-metric-val" style="color: var(--electric-cyan);">${totalRecs}</div>
        <div class="recovery-metric-label">Total Records</div>
      </div>
      <div class="recovery-metric-box">
        <div class="recovery-metric-val" style="color: #F59E0B;">${openCount}</div>
        <div class="recovery-metric-label">Open</div>
      </div>
      <div class="recovery-metric-box">
        <div class="recovery-metric-val" style="color: #00E5FF;">${inProgressCount}</div>
        <div class="recovery-metric-label">In Progress</div>
      </div>
      <div class="recovery-metric-box">
        <div class="recovery-metric-val" style="color: #10B981;">${resolvedCount}</div>
        <div class="recovery-metric-label">Resolved</div>
      </div>
    </div>

    <!-- Records List -->
    <div class="recovery-list-grid">
      ${records.map(rec => {
        const typeObj = (state.crisisTypes || []).find(t => t.crisis_type === rec.crisis_type);
        const typeTitle = typeObj ? typeObj.title : rec.crisis_type.replace(/_/g, ' ').toUpperCase();
        const icon = getCrisisIcon(rec.crisis_type);
        const createdDate = new Date(rec.created_at).toLocaleString('en-IN', {
          dateStyle: 'medium',
          timeStyle: 'short',
        });
        const statusClass = rec.status === 'resolved' ? 'resolved' : rec.status === 'in_progress' ? 'in_progress' : 'open';
        const statusLabel = rec.status === 'resolved' ? '✓ Resolved' : rec.status === 'in_progress' ? '⚡ In Progress' : '● Open';
        const prog = rec.progress || { completion_percentage: 0, completed_actions: 0, total_actions: 0 };
        const sevClass = rec.severity === 3 ? 'badge-danger' : rec.severity === 2 ? 'badge-warning' : 'badge-cyan';
        const sevLabel = rec.severity === 3 ? 'Severity 3: Critical' : rec.severity === 2 ? 'Severity 2: Moderate' : 'Severity 1: Minor';

        return `
          <div class="recovery-card" id="recovery-card-${escapeHTML(rec.recovery_id)}">
            <div class="recovery-card-header">
              <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <span style="font-size: 1.5rem;">${icon}</span>
                <div>
                  <h3 style="font-size: 1.15rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.2rem;">
                    ${escapeHTML(typeTitle)}
                  </h3>
                  <div style="font-size: 0.8rem; color: var(--text-muted);">
                    ID: <strong style="font-family: var(--font-mono); color: var(--text-secondary);">${escapeHTML(rec.recovery_id)}</strong>
                    · Evaluated: ${createdDate}
                  </div>
                </div>
              </div>

              <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                <span class="badge ${sevClass}">${sevLabel}</span>
                <span class="recovery-status-pill ${statusClass}">${statusLabel}</span>
                <span class="dataset-provenance-pill" style="font-size: 0.7rem;">source: ${escapeHTML(rec.source)}</span>
              </div>
            </div>

            ${rec.description ? `
              <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 1rem; line-height: 1.5;">
                ${escapeHTML(rec.description)}
              </div>
            ` : ''}

            <!-- Progress Bar -->
            <div style="background: rgba(0, 0, 0, 0.3); border: 1px solid rgba(255, 255, 255, 0.06); border-radius: var(--radius-md); padding: 0.85rem; margin-bottom: 1rem;">
              <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.4rem;">
                <span>Action Progress</span>
                <strong style="color: var(--electric-cyan); font-family: var(--font-mono);">${prog.completed_actions} of ${prog.total_actions} Completed (${prog.completion_percentage}%)</strong>
              </div>
              <div class="recovery-progress-bar-wrap">
                <div class="recovery-progress-bar-fill" style="width: ${prog.completion_percentage}%;"></div>
              </div>
            </div>

            <div style="display: flex; justify-content: flex-end;">
              <button class="btn btn-cyan btn-sm" onclick="selectRecoveryRecord('${escapeHTML(rec.recovery_id)}')">
                <span>View Plan & Track Actions →</span>
              </button>
            </div>
          </div>
        `;
      }).join('')}
    </div>
  `;
}

function renderRecoveryDetailView(container, record) {
  const typeObj = (state.crisisTypes || []).find(t => t.crisis_type === record.crisis_type);
  const typeTitle = typeObj ? typeObj.title : record.crisis_type.replace(/_/g, ' ').toUpperCase();
  const icon = getCrisisIcon(record.crisis_type);
  const createdDate = new Date(record.created_at).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  const updatedDate = new Date(record.updated_at).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
  const prog = record.progress || {
    total_actions: 0,
    pending_actions: 0,
    in_progress_actions: 0,
    completed_actions: 0,
    completion_percentage: 0,
  };
  const plan = record.recovery_plan || {};

  container.innerHTML = `
    <div class="view-header" style="margin-bottom: 1.25rem;">
      <div>
        <button class="btn btn-secondary btn-sm" onclick="selectRecoveryRecord(null)" style="margin-bottom: 0.75rem;">
          ← Back to All Recovery Records
        </button>
        <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
          <span style="font-size: 2rem;">${icon}</span>
          <div>
            <h1 class="view-title" style="margin-bottom: 0.25rem;">
              ${escapeHTML(typeTitle)} — Recovery Record
            </h1>
            <div style="font-size: 0.85rem; color: var(--text-muted);">
              ID: <strong style="font-family: var(--font-mono); color: var(--electric-cyan);">${escapeHTML(record.recovery_id)}</strong>
              · Created: ${createdDate} · Last Updated: ${updatedDate}
            </div>
          </div>
        </div>
      </div>

      <!-- Overall Status Control -->
      <div style="display: flex; align-items: center; gap: 0.75rem; background: var(--bg-surface-2); padding: 0.75rem 1rem; border-radius: var(--radius-md); border: 1px solid var(--amethyst-border);">
        <label for="recovery-overall-status-select" style="font-size: 0.8rem; font-weight: 700; color: var(--text-secondary); text-transform: uppercase;">
          Overall Status:
        </label>
        <select id="recovery-overall-status-select" class="form-select form-select-sm" style="width: auto; font-weight: 700;" onchange="handleRecoveryStatusChange('${escapeHTML(record.recovery_id)}', this.value)">
          <option value="open" ${record.status === 'open' ? 'selected' : ''}>● Open</option>
          <option value="in_progress" ${record.status === 'in_progress' ? 'selected' : ''}>⚡ In Progress</option>
          <option value="resolved" ${record.status === 'resolved' ? 'selected' : ''}>✓ Resolved</option>
        </select>
      </div>
    </div>

    <!-- Progress Summary Card -->
    <div class="card" style="margin-bottom: 1.5rem; background: var(--bg-surface-2); border: 1px solid var(--amethyst-border);">
      <div class="card-header" style="display: flex; justify-content: space-between; align-items: center;">
        <h3 class="card-title" style="color: var(--electric-cyan);">📊 Recovery Progress & Action Tracker</h3>
        <span class="badge ${record.severity === 3 ? 'badge-danger' : record.severity === 2 ? 'badge-warning' : 'badge-cyan'}">
          Severity ${record.severity}
        </span>
      </div>

      <div class="recovery-summary-metrics" style="margin-bottom: 1rem;">
        <div class="recovery-metric-box">
          <div class="recovery-metric-val" style="color: var(--text-primary);">${prog.total_actions}</div>
          <div class="recovery-metric-label">Total Actions</div>
        </div>
        <div class="recovery-metric-box">
          <div class="recovery-metric-val" style="color: #F59E0B;">${prog.pending_actions}</div>
          <div class="recovery-metric-label">Pending</div>
        </div>
        <div class="recovery-metric-box">
          <div class="recovery-metric-val" style="color: #00E5FF;">${prog.in_progress_actions}</div>
          <div class="recovery-metric-label">In Progress</div>
        </div>
        <div class="recovery-metric-box">
          <div class="recovery-metric-val" style="color: #10B981;">${prog.completed_actions}</div>
          <div class="recovery-metric-label">Completed</div>
        </div>
      </div>

      <div>
        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 0.35rem;">
          <span>Action Completion</span>
          <strong style="color: var(--electric-cyan); font-family: var(--font-mono);">${prog.completion_percentage}% Completed</strong>
        </div>
        <div class="recovery-progress-bar-wrap" style="height: 10px;">
          <div class="recovery-progress-bar-fill" style="width: ${prog.completion_percentage}%;"></div>
        </div>
      </div>
    </div>

    <!-- Tracked Actions List -->
    <div class="card" style="margin-bottom: 1.5rem;">
      <div class="card-header">
        <h3 class="card-title">📋 Tracked Action Items (${record.actions ? record.actions.length : 0})</h3>
      </div>

      <div class="recovery-actions-list">
        ${(!record.actions || record.actions.length === 0) ? `
          <div class="empty-state" style="padding: 2rem 1rem;">
            <p class="empty-desc">No actions are currently being tracked for this recovery record.</p>
          </div>
        ` : record.actions.map(act => {
          const pClass = act.priority === 1 ? 'recovery-priority-1' : act.priority === 2 ? 'recovery-priority-2' : 'recovery-priority-3';
          const pLabel = act.priority === 1 ? 'P1: Urgent' : act.priority === 2 ? 'P2: Operational' : 'P3: Follow-up';
          const cardStatusClass = act.status === 'completed' ? 'status-completed' : '';

          return `
            <div class="recovery-action-card ${cardStatusClass}" id="action-card-${escapeHTML(act.action_id)}">
              <div class="recovery-action-top">
                <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                  <span class="recovery-priority-badge ${pClass}">${pLabel}</span>
                  <span style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim);">${escapeHTML(act.action_id)}</span>
                  <h4 style="font-size: 1rem; font-weight: 700; color: var(--text-primary); margin: 0;">
                    ${escapeHTML(act.title)}
                  </h4>
                </div>

                <!-- Status Selector -->
                <div style="display: flex; align-items: center; gap: 0.5rem;">
                  <label for="action-status-${escapeHTML(act.action_id)}" class="sr-only">Status</label>
                  <select id="action-status-${escapeHTML(act.action_id)}" class="form-select form-select-sm" style="font-weight: 700; min-width: 130px;" onchange="handleActionStatusChange('${escapeHTML(record.recovery_id)}', '${escapeHTML(act.action_id)}', this.value)">
                    <option value="pending" ${act.status === 'pending' ? 'selected' : ''}>● Pending</option>
                    <option value="in_progress" ${act.status === 'in_progress' ? 'selected' : ''}>⚡ In Progress</option>
                    <option value="completed" ${act.status === 'completed' ? 'selected' : ''}>✓ Completed</option>
                  </select>
                </div>
              </div>

              <div style="font-size: 0.88rem; color: var(--text-secondary); line-height: 1.5; margin-bottom: 0.75rem;">
                ${escapeHTML(act.description)}
              </div>

              <!-- Notes Input Row -->
              <div class="recovery-notes-row">
                <span style="font-size: 0.8rem; color: var(--text-muted); white-space: nowrap;">Notes:</span>
                <input type="text" class="recovery-notes-input" id="action-notes-${escapeHTML(act.action_id)}" value="${escapeHTML(act.notes || '')}" placeholder="Add coordinator notes or vendor updates..." maxlength="1000">
                <button type="button" class="btn btn-secondary btn-sm" onclick="handleActionNotesSave('${escapeHTML(record.recovery_id)}', '${escapeHTML(act.action_id)}')">
                  Save Note
                </button>
              </div>
            </div>
          `;
        }).join('')}
      </div>
    </div>

    <!-- Saved Recovery Plan Reference -->
    ${plan.crisis_summary ? `
      <div class="card" style="margin-bottom: 1.5rem;">
        <div class="card-header">
          <h3 class="card-title">📖 Saved Recovery Plan Reference</h3>
        </div>

        <div style="margin-bottom: 1rem;">
          <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.35rem;">
            Root Cause & Operational Summary
          </h4>
          <p style="font-size: 0.88rem; color: var(--text-secondary); line-height: 1.5;">
            ${escapeHTML(plan.crisis_summary)}
          </p>
        </div>

        ${plan.budget_impact ? `
          <div style="background: var(--bg-surface-1); border: 1px solid var(--amethyst-border); border-radius: var(--radius-md); padding: 1rem; margin-bottom: 1rem;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 0.5rem;">
              <strong style="color: var(--electric-cyan);">Financial Impact Assessment</strong>
              <span class="badge ${plan.budget_impact.buffer_sufficient ? 'badge-cyan' : 'badge-danger'}">
                ${plan.budget_impact.buffer_sufficient ? 'Buffer Sufficient' : 'Buffer Deficit'}
              </span>
            </div>
            <div style="font-size: 0.85rem; color: var(--text-secondary); line-height: 1.5;">
              Estimated Cost Impact: <strong>₹${Number(plan.budget_impact.estimated_rupee_impact || 0).toLocaleString('en-IN')}</strong> (${plan.budget_impact.cost_impact_pct}%) · 
              Existing Contingency Buffer: <strong>₹${Number(plan.budget_impact.existing_buffer_inr || 0).toLocaleString('en-IN')}</strong>
            </div>
            <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 0.35rem;">
              ${escapeHTML(plan.budget_impact.advice || '')}
            </div>
          </div>
        ` : ''}

        ${plan.communication_drafts && plan.communication_drafts.length > 0 ? `
          <div>
            <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem;">
              Stakeholder Communication Drafts (${plan.communication_drafts.length})
            </h4>
            <div class="grid-2">
              ${plan.communication_drafts.map((draft, idx) => `
                <div class="crisis-draft-card">
                  <div class="crisis-draft-header">
                    <span class="crisis-draft-role">${escapeHTML(draft.recipient_role)}</span>
                    <span style="font-size: 0.75rem; color: var(--text-muted);">${escapeHTML(draft.recipient_label)}</span>
                  </div>
                  <div style="font-size: 0.82rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem;">
                    ${escapeHTML(draft.subject_or_header)}
                  </div>
                  <div class="crisis-draft-text-box" id="history-draft-text-${idx}">${highlightPlaceholders(draft.message_text)}</div>
                  <button type="button" class="btn-copy-draft" onclick="copyCrisisDraft('history-draft-text-${idx}', this)">
                    📋 Copy Broadcast Message
                  </button>
                </div>
              `).join('')}
            </div>
          </div>
        ` : ''}
      </div>
    ` : ''}
  `;
}

// ==============================================================================
// PROMPT 19: EVENT READINESS SCORE & PLANNING PROGRESS VIEW
// ==============================================================================

async function renderReadiness() {
  const container = document.getElementById('readiness-content');
  if (!container) return;

  if (!state.currentEventId) {
    renderEmptyEventState(container, 'Event Readiness Score');
    return;
  }

  container.innerHTML = `
    <div class="view-header">
      <div>
        <h1 class="view-title" id="readiness-heading">🎯 Event Readiness Score & Planning Progress</h1>
        <p class="view-subtitle">Deterministic evaluation of budget safety buffers, milestone timeliness, vendor bookings, and risk mitigations.</p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary btn-sm" onclick="renderReadiness()">
          🔄 Refresh Assessment
        </button>
      </div>
    </div>
    <div class="loading-state"><div class="spinner"></div></div>
  `;

  try {
    const data = await API.getReadiness(state.currentEventId);
    state.readiness = data;

    const statusMap = {
      'well_prepared': { label: 'Well Prepared', class: 'status-well_prepared', dialClass: 'dial-well_prepared', icon: '✅' },
      'in_progress': { label: 'In Progress', class: 'status-in_progress', dialClass: 'dial-in_progress', icon: '⏳' },
      'needs_attention': { label: 'Needs Attention', class: 'status-needs_attention', dialClass: 'dial-needs_attention', icon: '⚠️' },
      'not_started': { label: 'Not Started', class: 'status-not_started', dialClass: 'dial-not_started', icon: '⚪' },
      'insufficient_data': { label: 'Insufficient Data', class: 'status-insufficient_data', dialClass: 'dial-insufficient_data', icon: '❌' },
    };
    const sInfo = statusMap[data.readiness_status] || statusMap['in_progress'];
    const scoreDisplay = data.overall_score !== null ? data.overall_score : '—';

    container.innerHTML = `
      <div class="view-header">
        <div>
          <h1 class="view-title" id="readiness-heading">🎯 Event Readiness Score & Planning Progress</h1>
          <p class="view-subtitle">Deterministic evaluation of budget safety buffers, milestone timeliness, vendor bookings, and risk mitigations.</p>
        </div>
        <div class="header-actions">
          <button class="btn btn-secondary btn-sm" onclick="renderReadiness()">
            🔄 Refresh Assessment
          </button>
        </div>
      </div>

      <!-- Hero Score Card -->
      <div class="readiness-hero-card">
        <div class="readiness-hero-left">
          <div class="readiness-score-dial ${sInfo.dialClass}">
            <div class="readiness-score-num">${scoreDisplay}</div>
            <div class="readiness-score-denom">OUT OF 100</div>
          </div>
          <div class="readiness-hero-info">
            <div class="readiness-status-badge ${sInfo.class}">
              <span>${sInfo.icon}</span>
              <span>${sInfo.label}</span>
            </div>
            <p style="font-size: 0.9rem; color: var(--text-secondary); max-width: 480px; margin: 0;">
              ${data.overall_score !== null
                ? `Event readiness is evaluated at <strong>${data.overall_score}%</strong> across active planning categories.`
                : 'Missing core planning parameters prevent an authoritative readiness calculation.'}
            </p>
          </div>
        </div>
        <div class="readiness-hero-stats">
          <div class="readiness-stat-item">
            <span class="readiness-stat-val" style="color: #10B981;">${data.completed_items}</span>
            <span class="readiness-stat-lbl">Completed Items</span>
          </div>
          <div class="readiness-stat-item">
            <span class="readiness-stat-val" style="color: var(--electric-cyan);">${data.outstanding_items}</span>
            <span class="readiness-stat-lbl">Pending Items</span>
          </div>
          <div class="readiness-stat-item">
            <span class="readiness-stat-val" style="color: ${data.critical_concerns.length > 0 ? '#EF4444' : '#10B981'};">
              ${data.critical_concerns.length}
            </span>
            <span class="readiness-stat-lbl">Critical Concerns</span>
          </div>
        </div>
      </div>

      <!-- Critical Concerns Box (if any) -->
      ${data.critical_concerns && data.critical_concerns.length > 0 ? `
        <div class="readiness-concerns-box">
          <div class="readiness-concerns-title">
            <span>🚨</span>
            <span>Critical Concerns Requiring Immediate Host Attention (${data.critical_concerns.length})</span>
          </div>
          <ul class="readiness-concerns-list">
            ${data.critical_concerns.map(c => `<li>${escapeHTML(c)}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      <!-- Missing Information Box (if any) -->
      ${data.missing_information && data.missing_information.length > 0 ? `
        <div class="readiness-missing-box">
          <div class="readiness-missing-title">
            <span>ℹ️</span>
            <span>Planning Information Gaps (${data.missing_information.length})</span>
          </div>
          <ul class="readiness-concerns-list" style="color: var(--text-secondary);">
            ${data.missing_information.map(m => `<li>${escapeHTML(m)}</li>`).join('')}
          </ul>
        </div>
      ` : ''}

      <!-- Prioritized Next Actions -->
      <div class="readiness-actions-section">
        <h2 style="font-size: 1.15rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.75rem;">
          ⚡ Prioritized Next Actions (${data.recommended_next_actions.length})
        </h2>
        ${data.recommended_next_actions.length === 0 ? `
          <div class="card" style="padding: 1.25rem; color: var(--text-muted); font-size: 0.9rem;">
            No immediate pending actions detected. Your planning milestones and vendors are well aligned!
          </div>
        ` : `
          <div class="readiness-actions-list">
            ${data.recommended_next_actions.map(act => {
              const pClass = act.priority === 'critical' ? 'badge-danger' : (act.priority === 'high' ? 'badge-warning' : 'badge-secondary');
              const viewLabels = {
                'timeline': 'Open Timeline ➔',
                'vendors': 'Open Vendors ➔',
                'budget': 'Open Budget ➔',
                'risks': 'Open Risks ➔',
                'recovery-history': 'Open Crisis History ➔',
                'event-details': 'Edit Event Details ➔',
              };
              const ctaText = viewLabels[act.target_view] || 'View Section ➔';
              return `
                <div class="readiness-action-item">
                  <div class="readiness-action-left">
                    <div class="readiness-action-meta">
                      <span class="badge ${pClass}">${escapeHTML(act.priority.toUpperCase())}</span>
                      <span class="badge badge-amethyst">${escapeHTML(act.category.toUpperCase())}</span>
                      ${act.target_id ? `<span style="font-size: 0.75rem; color: var(--text-muted); font-family: var(--font-mono);">${escapeHTML(act.target_id)}</span>` : ''}
                    </div>
                    <div class="readiness-action-title">${escapeHTML(act.title)}</div>
                    <div class="readiness-action-desc">${escapeHTML(act.description)}</div>
                  </div>
                  <button type="button" class="btn btn-cyan btn-sm" style="flex-shrink: 0;" onclick="switchView('${escapeHTML(act.target_view)}')">
                    ${escapeHTML(ctaText)}
                  </button>
                </div>
              `;
            }).join('')}
          </div>
        `}
      </div>

      <!-- Domain Category Score Breakdown -->
      <div style="margin-bottom: 2rem;">
        <h2 style="font-size: 1.15rem; font-weight: 800; color: var(--text-primary); margin-bottom: 1rem;">
          📊 Planning Category Score Breakdown
        </h2>
        <div class="readiness-categories-grid">
          ${data.category_scores.map(cat => {
            const hasScore = cat.is_available && cat.score !== null;
            const scoreVal = hasScore ? cat.score : 'N/A';
            const barWidth = hasScore ? cat.score : 0;
            return `
              <div class="readiness-cat-card">
                <div>
                  <div class="readiness-cat-header">
                    <div>
                      <div class="readiness-cat-title">${escapeHTML(cat.name)}</div>
                      <div class="readiness-cat-weight">Weight: ${cat.weight_percentage}%</div>
                    </div>
                    <div class="readiness-cat-score-pill" style="${!hasScore ? 'color: var(--text-muted); background: rgba(255,255,255,0.05); border-color: rgba(255,255,255,0.1);' : ''}">
                      ${scoreVal}${hasScore ? '<span style="font-size: 0.75rem;">/100</span>' : ''}
                    </div>
                  </div>
                  <div class="readiness-cat-bar-wrap">
                    <div class="readiness-cat-bar-fill" style="width: ${barWidth}%;"></div>
                  </div>
                  <div class="readiness-cat-desc">${escapeHTML(cat.explanation)}</div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <!-- Methodology & Advisory Footer -->
      <div class="card" style="background: rgba(255,255,255,0.02); border: 1px dashed var(--amethyst-border); padding: 1.25rem;">
        <div style="font-size: 0.8rem; color: var(--text-muted); line-height: 1.6;">
          <strong style="color: var(--text-secondary);">Methodology:</strong> ${escapeHTML(data.calculation_method)}
          <br>
          <strong style="color: var(--text-secondary);">Disclaimer:</strong> ${escapeHTML(data.disclaimer)}
        </div>
      </div>
    `;
  } catch (err) {
    console.error('Failed to load readiness assessment:', err);
    container.innerHTML = `
      <div class="view-header">
        <div>
          <h1 class="view-title" id="readiness-heading">🎯 Event Readiness Score & Planning Progress</h1>
          <p class="view-subtitle">Deterministic evaluation of budget safety buffers, milestone timeliness, vendor bookings, and risk mitigations.</p>
        </div>
      </div>
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <h2 class="empty-title">Failed to Load Readiness Assessment</h2>
        <p class="empty-desc">${escapeHTML(err.message || 'Unable to retrieve readiness diagnostics from server.')}</p>
        <button class="btn btn-cyan btn-sm" onclick="renderReadiness()">Retry</button>
      </div>
    `;
  }
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
    case 'crisis':
      renderCrisis();
      break;
    case 'recovery-history':
      renderRecoveryHistory();
      break;
    case 'readiness':
      renderReadiness();
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
  state.selectedRecoveryId = null;
  state.selectedRecovery = null;
  try {
    sessionStorage.setItem('planproof_active_event_id', eventId);
  } catch (err) {
    // Graceful fallback if storage disabled
  }
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

    // Check sessionStorage for active event persistence across refreshes
    let savedId = null;
    try {
      savedId = sessionStorage.getItem('planproof_active_event_id');
    } catch (err) {
      // Storage access check
    }

    if (savedId && state.events.some(e => e.event_id === savedId)) {
      state.currentEventId = savedId;
    } else if (!state.currentEventId || !state.events.some(e => e.event_id === state.currentEventId)) {
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

  // 8. Save Recovery Plan Modal Triggers
  document.getElementById('btn-close-save-recovery-modal')?.addEventListener('click', closeSaveRecoveryModal);
  document.getElementById('btn-cancel-save-recovery')?.addEventListener('click', closeSaveRecoveryModal);
  document.getElementById('btn-select-all-actions')?.addEventListener('click', () => {
    document.querySelectorAll('.recovery-action-check').forEach(cb => { cb.checked = true; });
  });
  document.getElementById('btn-deselect-all-actions')?.addEventListener('click', () => {
    document.querySelectorAll('.recovery-action-check').forEach(cb => { cb.checked = false; });
  });
  document.getElementById('form-save-recovery')?.addEventListener('submit', handleSaveRecoverySubmit);

  // 9. Bootstrap Initial State
  await loadSystemStatus();
  await loadEventsList();

  const initialHash = window.location.hash.replace('#', '') || 'overview';
  switchView(initialHash);
});
