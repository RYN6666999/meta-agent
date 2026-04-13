/**
 * main.js
 * CRM 應用程式進入點：初始化、導覽、資料載入、window bridge
 * 依賴：commands.js + 所有 features/*
 */

// ── Core ──────────────────────────────────────────────────────────────────────
import { STORE } from './core/store.js';
import { dispatch, getNodes, gatherSubtree, isHidden } from './core/state.js';
import { toast } from './core/toast.js';
import { undoLast, pushUndo } from './core/undo.js';

// ── Commands ──────────────────────────────────────────────────────────────────
import { CMD, DRAFT } from './commands.js';

// ── Canvas ────────────────────────────────────────────────────────────────────
import { renderNodes, setUpdateStatsFn } from './features/canvas/render.js';
import { drawEdges } from './features/canvas/edges.js';
import { initCanvas, fitView, zoomBy, applyTransform, updateZoomLabel } from './features/canvas/interact.js';
import { setClosePanelFn, setOpenPanelFn } from './features/canvas/interact.js';
import { getSelId, selectNode, deselect } from './features/canvas/select.js';
import { autoLayout, forceLayout } from './features/canvas/layout.js';
import {
  cycleStatus, toggleCollapse, promptDel, copySelected, cutSelected, pasteClipboard,
  headerAddNode, headerAddNote, setNoteColor, setNoteFontSize, saveNoteContent,
  setOpenPanelFn as crudSetOpenPanel, setClosePanelFn as crudSetClosePanel,
  setGetPanelNodeIdFn,
} from './features/canvas/crud.js';

// ── Panel ─────────────────────────────────────────────────────────────────────
import {
  openPanel, closePanel, savePanel, updateStats,
  markContactedToday, toggleNeed, toggleRegion, toggleAcc,
  copyCSheet, getPanelNodeId, setRenderNodesFn as panelSetRenderNodes,
} from './features/panel/index.js';

// ── Events ────────────────────────────────────────────────────────────────────
import {
  renderCalendar, openEventModal, closeEventModal, saveEvent, deleteEvent,
  calPrev, calNext, calGoToday, setCMD as evSetCMD,
} from './features/events/index.js';

// ── AI ────────────────────────────────────────────────────────────────────────
import { renderAiSettingsCard, saveAiSettings, onAiProviderChange, fetchDynamicModels, updateAiModelBadge } from './features/ai/providers.js';
import { setPersona, renderQuickPrompts, injectPrompt, getCurrentPersona } from './features/ai/personas.js';
import { sendChat, renderChat, clearChat, extractAndSaveMemories, renderMemoryList, deleteMemory } from './features/ai/chat.js';

// ── Daily ─────────────────────────────────────────────────────────────────────
import { renderDailyPage, saveDailyReport, saveMonthlyTarget, renderMonthlyTargetInput } from './features/daily/index.js';

// ── Docs ──────────────────────────────────────────────────────────────────────
import { renderDocsPage, openDocModal, closeDocModal, saveDoc, deleteDoc, setDocsSearch } from './features/docs/index.js';

// ── Students ──────────────────────────────────────────────────────────────────
import { renderStudentsPage, openStudentModal, closeStudentModal, saveStudent, deleteStudent, logStudentContact, setStudentsSearch } from './features/students/index.js';

// ── Settings ──────────────────────────────────────────────────────────────────
import { initTheme, onThemeChange, renderLoginCard, saveLogin, exportData, importData, clearAllData, renderShortcutsHelp } from './features/settings/index.js';

// ── Sales ─────────────────────────────────────────────────────────────────────
import {
  renderSalesPage, salesPrevMonth, salesNextMonth, salesGoToday,
  openSaleModal, closeSaleModal, saveSale, deleteSale,
  onSaleTypeChange, onSaleProductChange, onSaleAmountFocus, onSaleAmountBlur, onSaleAmountInput,
} from './features/sales/index.js';

// ── Canvas Views ──────────────────────────────────────────────────────────────
import { setCrmView, toggleCrmSortDir, renderListView } from './features/canvas/views.js';

// ── Daily navigation ──────────────────────────────────────────────────────────
import { dailyToday, dailyPrev, dailyNext } from './features/daily/index.js';

// ── Google Calendar ───────────────────────────────────────────────────────────
import { renderGcalCard, startGcalOAuth, disconnectGcal, fetchGcalEvents } from './integrations/gcal.js';

// ─────────────────────────────────────────────────────────────────────────────
// Navigation
// ─────────────────────────────────────────────────────────────────────────────

let _currentPage = 'canvas';

export function navigate(page) {
  _currentPage = page;
  document.querySelectorAll('.page-section').forEach(s => s.classList.remove('active'));
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));

  const section = document.getElementById(`page-${page}`);
  if (section) section.classList.add('active');
  const navEl = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (navEl) navEl.classList.add('active');

  switch (page) {
    case 'canvas':
    case 'crm':      setCrmView('tree'); break;
    case 'calendar':
    case 'events':   renderCalendar(); break;
    case 'daily':    renderDailyPage(); renderMonthlyTargetInput(); break;
    case 'docs':     renderDocsPage(); break;
    case 'sales':    renderSalesPage(); break;
    case 'students': renderStudentsPage(); break;
    case 'ai':       renderChat(); renderQuickPrompts(getCurrentPersona()); updateAiModelBadge(); break;
    case 'settings': renderLoginCard(); renderAiSettingsCard(); renderGcalCard(); renderShortcutsHelp(); break;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Data bootstrap
// ─────────────────────────────────────────────────────────────────────────────

function loadData() {
  dispatch({ type: 'NODES_LOAD',                payload: STORE.loadNodes() || [] });
  dispatch({ type: 'EVENTS_SET',                payload: STORE.loadEvents() });
  dispatch({ type: 'SALES_SET',                 payload: STORE.loadSales() });
  dispatch({ type: 'DAILY_REPORTS_SET',         payload: STORE.loadDailyReports() });
  dispatch({ type: 'MONTHLY_SALES_TARGETS_SET', payload: STORE.loadMonthlySalesTargets() });
  dispatch({ type: 'DOCS_SET',                  payload: STORE.loadDocs() });
  dispatch({ type: 'STUDENTS_SET',              payload: STORE.loadStudents() });
}

// ─────────────────────────────────────────────────────────────────────────────
// Window bridge (HTML inline onclick handlers → ES modules)
// ─────────────────────────────────────────────────────────────────────────────

function registerWindowBridge() {
  // Canvas
  window.__crmSelectNode      = id => selectNode(id);
  window.__crmOpenPanel       = id => openPanel(id);
  window.__crmClosePanel      = () => closePanel();
  window.__crmCycleStatus     = id => cycleStatus(id);
  window.__crmToggleCollapse  = id => toggleCollapse(id);
  window.__crmPromptDel       = id => promptDel(id);
  window.__crmGatherSubtree   = id => gatherSubtree(id);
  window.__crmIsHidden        = id => isHidden(id);
  window.__crmSetNoteColor    = (id, c) => setNoteColor(id, c);
  window.__crmSetNoteFontSize = (id, s) => setNoteFontSize(id, s);
  window.__crmSaveNoteContent = id => saveNoteContent(id);

  // Events
  window.__crmOpenEventModal  = (id, date) => openEventModal(id, date);
  window.__crmCloseEventModal = () => closeEventModal();
  window.__crmSaveEvent       = () => saveEvent();
  window.__crmDeleteEvent     = id => deleteEvent(id);

  // Docs
  window.__crmOpenDocModal    = id => openDocModal(id);
  window.__crmCloseDocModal   = () => closeDocModal();
  window.__crmSaveDoc         = () => saveDoc();
  window.__crmDeleteDoc       = id => deleteDoc(id);

  // Students
  window.__crmOpenStudentModal  = id => openStudentModal(id);
  window.__crmCloseStudentModal = () => closeStudentModal();
  window.__crmSaveStudent       = () => saveStudent();
  window.__crmDeleteStudent     = id => deleteStudent(id);
  window.__crmLogStudentContact = id => logStudentContact(id);

  // Panel
  window.__crmSavePanel         = () => savePanel();
  window.__crmMarkContacted     = () => markContactedToday();
  window.__crmToggleNeed        = el => toggleNeed(el);
  window.__crmToggleRegion      = el => toggleRegion(el);
  window.__crmToggleAcc         = h => toggleAcc(h);
  window.__crmCopyCSheet        = () => copyCSheet();

  // AI
  window.__crmInjectPrompt      = idx => injectPrompt(idx);
  window.__crmExtractMemories   = c => extractAndSaveMemories(c);
  window.__crmDeleteMemory      = id => deleteMemory(id);

  // Navigation
  window.__crmNavigate          = page => navigate(page);

  // Full refresh (used by import/clear)
  window.__crmFullRefresh = () => {
    loadData();
    navigate(_currentPage);
  };
}

// ─────────────────────────────────────────────────────────────────────────────
// Keyboard shortcuts
// ─────────────────────────────────────────────────────────────────────────────

function initKeyboard() {
  document.addEventListener('keydown', e => {
    const tag = document.activeElement?.tagName;
    const inInput = ['INPUT', 'TEXTAREA', 'SELECT'].includes(tag);
    const meta  = e.metaKey || e.ctrlKey;

    if (meta && e.key === 'z') { e.preventDefault(); undoLast(renderNodes, deselect); return; }
    if (meta && e.key === 'c') { e.preventDefault(); copySelected(); return; }
    if (meta && e.key === 'x') { e.preventDefault(); cutSelected();  return; }
    if (meta && e.key === 'v') { e.preventDefault(); pasteClipboard(); return; }

    if (inInput) return;

    switch (e.key) {
      case 'Delete': case 'Backspace': {
        const sid = getSelId();
        if (sid) { e.preventDefault(); promptDel(sid); }
        break;
      }
      case 'Tab': {
        const sid = getSelId();
        if (sid) { e.preventDefault(); import('./features/canvas/crud.js').then(m => m.addChild(sid)); }
        break;
      }
      case 'Enter': {
        const sid = getSelId();
        if (sid) { e.preventDefault(); import('./features/canvas/crud.js').then(m => m.addSibling(sid)); }
        break;
      }
      case 'Escape':
        deselect(); closePanel();
        break;
      case 'f': case 'F':
        fitView(); break;
      case '+': case '=':
        zoomBy(1.2); break;
      case '-':
        zoomBy(1 / 1.2); break;
    }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Chat input auto-resize + Enter to send
// ─────────────────────────────────────────────────────────────────────────────

function initChatInput() {
  const inp = document.getElementById('chat-input');
  if (!inp) return;
  inp.addEventListener('input', () => {
    inp.style.height = 'auto';
    inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
  });
  inp.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Dependency injection wiring
// ─────────────────────────────────────────────────────────────────────────────

function wireDependencies() {
  // canvas/interact needs open/close panel
  setClosePanelFn(closePanel);
  setOpenPanelFn(openPanel);

  // canvas/crud needs panel fns
  crudSetOpenPanel(openPanel);
  crudSetClosePanel(closePanel);
  setGetPanelNodeIdFn(getPanelNodeId);

  // panel needs renderNodes for after-save refresh
  panelSetRenderNodes(renderNodes);

  // canvas/render needs updateStats
  setUpdateStatsFn(updateStats);

  // events CMD guard
  evSetCMD(CMD);
}

// ─────────────────────────────────────────────────────────────────────────────
// init()
// ─────────────────────────────────────────────────────────────────────────────

export async function init() {
  initTheme();
  loadData();
  wireDependencies();
  registerWindowBridge();
  initCanvas();
  initKeyboard();
  initChatInput();

  // Initial render
  renderNodes();
  drawEdges();
  fitView();
  updateStats();

  // Restore last page
  const lastPage = localStorage.getItem('crm-last-page') || 'canvas';
  navigate(lastPage);

  // Persist current page on nav clicks
  document.querySelectorAll('.nav-item[data-page]').forEach(el => {
    el.addEventListener('click', () => {
      const p = el.dataset.page;
      localStorage.setItem('crm-last-page', p);
      navigate(p);
    });
  });

  console.log('[CRM] init complete');
}

// ─────────────────────────────────────────────────────────────────────────────
// Boot
// ─────────────────────────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
