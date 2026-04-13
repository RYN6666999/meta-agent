/**
 * features/daily/index.js
 * 日報頁：活動量記錄、每日目標追蹤、月報彙整
 * 依賴：core/state.js, core/toast.js, core/calc.js, core/store.js
 */

import { getDailyReports, getMonthlySalesTargets, getSalesData, dispatch } from '../../core/state.js';
import { STORE } from '../../core/store.js';
import { CALC } from '../../core/calc.js';
import { toast } from '../../core/toast.js';

// ── Date navigation state ─────────────────────────────────────────────────────

let _viewDate = new Date().toISOString().slice(0, 10);

export function dailyToday() {
  _viewDate = new Date().toISOString().slice(0, 10);
  const inp = document.getElementById('daily-date-input');
  if (inp) inp.value = _viewDate;
  renderDailyPage();
}

export function dailyPrev() {
  const d = new Date(_viewDate);
  d.setDate(d.getDate() - 1);
  _viewDate = d.toISOString().slice(0, 10);
  const inp = document.getElementById('daily-date-input');
  if (inp) inp.value = _viewDate;
  renderDailyPage();
}

export function dailyNext() {
  const d = new Date(_viewDate);
  d.setDate(d.getDate() + 1);
  _viewDate = d.toISOString().slice(0, 10);
  const inp = document.getElementById('daily-date-input');
  if (inp) inp.value = _viewDate;
  renderDailyPage();
}

// ── KPI field definitions ─────────────────────────────────────────────────────

const DAILY_KPIS = [
  { id: 'invite',   label: '邀約' },
  { id: 'calls',    label: '電訪' },
  { id: 'forms',    label: '表單' },
  { id: 'followup', label: '追蹤' },
  { id: 'close',    label: '成交' },
];

// ── Daily report render ───────────────────────────────────────────────────────

export function renderDailyPage() {
  const inp = document.getElementById('daily-date-input');
  if (inp) {
    if (inp.value) _viewDate = inp.value;
    else inp.value = _viewDate;
  }
  const today       = _viewDate;
  const monthPrefix = today.slice(0, 7);
  const reports     = getDailyReports();
  const r           = reports[today] || {};

  const body = document.getElementById('daily-body');
  if (!body) return;

  body.innerHTML = `
    <div class="daily-section">
      <div class="daily-section-header"><span>📞 今日實績</span></div>
      <div class="daily-section-body">
        <div class="daily-activity-grid">
          ${DAILY_KPIS.map(k => `
            <div class="daily-act-item">
              <div class="daily-act-label">${k.label}</div>
              <input class="daily-act-input" id="daily-${k.id}" type="number" min="0"
                value="${r[k.id] ?? ''}" placeholder="0">
            </div>`).join('')}
        </div>
      </div>
    </div>
    <div class="daily-section">
      <div class="daily-section-header"><span>📝 今日筆記</span></div>
      <div class="daily-section-body">
        <textarea class="daily-notes-input" id="daily-notes"
          placeholder="今天做了什麼？有什麼收穫？明天重點是什麼？">${r.notes || ''}</textarea>
      </div>
    </div>
    <div class="daily-section">
      <div class="daily-section-header">
        <span>📅 ${monthPrefix.slice(0, 4)}年${parseInt(monthPrefix.slice(5))}月 業績進度</span>
      </div>
      <div class="daily-section-body" id="daily-month-summary"></div>
    </div>
    <div class="daily-section">
      <div class="daily-section-header"><span>📋 本月活動量</span></div>
      <div class="daily-section-body" id="daily-monthly-table"></div>
    </div>`;

  renderDailySummary(today, monthPrefix);
  renderMonthlyTable(monthPrefix);
}

export function saveDailyReport() {
  const today = _viewDate;
  const r = {
    invite:   Number(document.getElementById('daily-invite')?.value)   || 0,
    calls:    Number(document.getElementById('daily-calls')?.value)    || 0,
    forms:    Number(document.getElementById('daily-forms')?.value)    || 0,
    followup: Number(document.getElementById('daily-followup')?.value) || 0,
    close:    Number(document.getElementById('daily-close')?.value)    || 0,
    notes:    document.getElementById('daily-notes')?.value            || '',
  };
  dispatch({ type: 'DAILY_REPORT_PATCH', payload: { date: today, patch: r } });
  toast('日報已儲存');
  renderDailySummary(today, today.slice(0, 7));
  renderMonthlyTable(today.slice(0, 7));
}

function renderDailySummary(today, monthPrefix) {
  const reports = getDailyReports();
  const salesData = getSalesData();
  const myRate  = STORE.getMyRate();
  const targets = getMonthlySalesTargets();
  const summary = CALC.monthSummary(salesData, myRate, monthPrefix);
  const target  = targets[monthPrefix] || 300000;
  const pct     = target > 0 ? Math.round(summary.income / target * 100) : 0;

  const el = document.getElementById('daily-month-summary');
  if (!el) return;
  el.innerHTML = `
    <div class="stat-row">
      <span>本月業績</span>
      <strong>$${summary.income.toLocaleString()} / $${target.toLocaleString()} (${pct}%)</strong>
    </div>
    <div class="stat-row">
      <span>稅後收入</span>
      <strong>$${summary.net.toLocaleString()}</strong>
    </div>
    <div class="stat-row">
      <span>成交件數</span>
      <strong>${summary.newCount} 件</strong>
    </div>`;
}

function renderMonthlyTable(monthPrefix) {
  const reports = getDailyReports();
  const el = document.getElementById('daily-monthly-table');
  if (!el) return;

  const rows = Object.entries(reports)
    .filter(([d]) => d.startsWith(monthPrefix))
    .sort(([a], [b]) => b.localeCompare(a))
    .slice(0, 31);

  if (!rows.length) { el.innerHTML = '<div style="color:var(--text-muted);font-size:12px;padding:8px">本月尚無日報</div>'; return; }

  el.innerHTML = `<table class="data-table">
    <thead><tr><th>日期</th><th>邀約</th><th>電訪</th><th>表單</th><th>追蹤</th><th>成交</th></tr></thead>
    <tbody>${rows.map(([d, r]) => `
      <tr>
        <td>${d.slice(5)}</td>
        <td>${r.invite || 0}</td>
        <td>${r.calls  || 0}</td>
        <td>${r.forms  || 0}</td>
        <td>${r.followup || 0}</td>
        <td>${r.close  || 0}</td>
      </tr>`).join('')}
    </tbody>
  </table>`;
}

// ── Monthly target ────────────────────────────────────────────────────────────

export function saveMonthlyTarget() {
  const monthPrefix = new Date().toISOString().slice(0, 7);
  const val = Number(document.getElementById('monthly-target-input')?.value) || 0;
  dispatch({ type: 'MONTHLY_SALES_TARGETS_PATCH', payload: { [monthPrefix]: val } });
  toast('月目標已儲存');
  renderDailyPage();
}

export function renderMonthlyTargetInput() {
  const monthPrefix = new Date().toISOString().slice(0, 7);
  const targets = getMonthlySalesTargets();
  const el = document.getElementById('monthly-target-input');
  if (el) el.value = targets[monthPrefix] || '';
}
