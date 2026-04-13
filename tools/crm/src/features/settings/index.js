/**
 * features/settings/index.js
 * 設定頁：主題、快捷鍵說明、資料匯入匯出、帳號資料
 * 依賴：core/state.js, core/store.js, core/toast.js
 */

import { getNodes, getEvents, getSalesData, getDailyReports, getMonthlySalesTargets, getDocsData, dispatch } from '../../core/state.js';
import { STORE, K } from '../../core/store.js';
import { toast } from '../../core/toast.js';

// ── Theme ─────────────────────────────────────────────────────────────────────

export function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  localStorage.setItem('crm-theme', theme);
}

export function initTheme() {
  const saved = localStorage.getItem('crm-theme') || 'dark';
  applyTheme(saved);
  const sel = document.getElementById('theme-select');
  if (sel) sel.value = saved;
}

export function onThemeChange() {
  const sel = document.getElementById('theme-select');
  if (sel) applyTheme(sel.value);
}

// ── Login / account ───────────────────────────────────────────────────────────

export function renderLoginCard() {
  const login = JSON.parse(localStorage.getItem('crm-login') || '{}');
  const nameEl = document.getElementById('settings-name-input');
  const rankEl = document.getElementById('settings-rank-select');
  if (nameEl) nameEl.value = login.name || '';
  if (rankEl) rankEl.value = login.rank || 'director';
}

export function saveLogin() {
  const name = document.getElementById('settings-name-input')?.value.trim() || '';
  const rank = document.getElementById('settings-rank-select')?.value || 'director';
  localStorage.setItem('crm-login', JSON.stringify({ name, rank }));
  // Sync rank into STORE so CALC picks it up
  localStorage.setItem(K.profileRank, rank);
  toast('帳號資料已儲存');
}

// ── Export ────────────────────────────────────────────────────────────────────

export function exportData() {
  const data = {
    exportedAt: new Date().toISOString(),
    nodes:       getNodes(),
    events:      getEvents(),
    salesData:   getSalesData(),
    dailyReports: getDailyReports(),
    monthlySalesTargets: getMonthlySalesTargets(),
    docsData:    getDocsData(),
    login:       JSON.parse(localStorage.getItem('crm-login') || '{}'),
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `crm-backup-${new Date().toISOString().slice(0, 10)}.json`;
  a.click();
  URL.revokeObjectURL(url);
  toast('資料已匯出');
}

// ── Import ────────────────────────────────────────────────────────────────────

export function importData(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      if (!data.nodes) throw new Error('格式不正確');
      if (!confirm(`確定匯入？這會覆蓋現有資料（${data.nodes.length} 個節點）`)) return;

      if (data.nodes)        dispatch({ type: 'NODES_LOAD',    payload: data.nodes });
      if (data.events)       dispatch({ type: 'EVENTS_SET',   payload: data.events });
      if (data.salesData)    dispatch({ type: 'SALES_SET',                 payload: data.salesData });
      if (data.dailyReports) dispatch({ type: 'DAILY_REPORTS_SET',        payload: data.dailyReports });
      if (data.monthlySalesTargets) dispatch({ type: 'MONTHLY_SALES_TARGETS_SET', payload: data.monthlySalesTargets });
      if (data.docsData)     dispatch({ type: 'DOCS_SET',                 payload: data.docsData });
      if (data.login)        localStorage.setItem('crm-login', JSON.stringify(data.login));

      toast(`匯入完成（${data.nodes.length} 個節點）`);
      window.__crmFullRefresh?.();
    } catch (err) {
      toast('匯入失敗：' + err.message);
    }
  };
  reader.readAsText(file);
}

// ── Keyboard shortcuts help ───────────────────────────────────────────────────

export const SHORTCUTS_HELP = [
  { keys: 'Ctrl/⌘ + Z',   desc: '復原（Undo）' },
  { keys: 'Ctrl/⌘ + C',   desc: '複製選取節點' },
  { keys: 'Ctrl/⌘ + X',   desc: '剪下選取節點' },
  { keys: 'Ctrl/⌘ + V',   desc: '貼上節點' },
  { keys: 'Delete / ⌫',   desc: '刪除選取節點' },
  { keys: 'Tab',           desc: '新增子節點' },
  { keys: 'Enter',         desc: '新增兄弟節點' },
  { keys: 'Escape',        desc: '關閉面板 / 取消選取' },
  { keys: 'F',             desc: 'Fit View（自動縮放）' },
  { keys: '+/-',           desc: '放大 / 縮小' },
];

export function renderShortcutsHelp() {
  const el = document.getElementById('shortcuts-help-list');
  if (!el) return;
  el.innerHTML = SHORTCUTS_HELP.map(s =>
    `<div class="shortcut-row"><kbd>${s.keys}</kbd><span>${s.desc}</span></div>`
  ).join('');
}

// ── Clear all data ────────────────────────────────────────────────────────────

export function clearAllData() {
  if (!confirm('確定清除所有資料？此操作無法復原！')) return;
  if (!confirm('再次確認：這將刪除所有人脈、活動、業績記錄！')) return;
  dispatch({ type: 'NODES_LOAD',    payload: [] });
  dispatch({ type: 'EVENTS_SET',   payload: [] });
  dispatch({ type: 'SALES_SET',                 payload: {} });
  dispatch({ type: 'DAILY_REPORTS_SET',         payload: {} });
  dispatch({ type: 'MONTHLY_SALES_TARGETS_SET', payload: {} });
  dispatch({ type: 'DOCS_SET',                  payload: [] });
  toast('所有資料已清除');
  window.__crmFullRefresh?.();
}
