/**
 * core/store.js
 * localStorage 存取層 — 單一真理源
 * 依賴：contracts/types.js (STORE_KEYS), contracts/types.js (RANK_RATES)
 * FORBIDDEN: no DOM, no calculations, no business logic
 */

import { STORE_KEYS, RANK_RATES } from '../contracts/types.js';

// Re-export for convenience
export const K = STORE_KEYS;

// ── Generic helpers ──────────────────────────────────────────────────────────

/** 從 localStorage 讀取 JSON，失敗回傳 fallback */
export function loadJSON(key, fallback) {
  try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; }
  catch { return fallback; }
}

/** 將值序列化寫入 localStorage */
export function saveJSON(key, val) {
  localStorage.setItem(key, JSON.stringify(val));
}

// ── Typed save helpers（供 state.js / features 呼叫）────────────────────────

export const STORE = {
  K,

  // ── Readers ──
  getMyRank() { return localStorage.getItem(K.profileRank) || 'director'; },
  getMyRate() { return RANK_RATES[STORE.getMyRank()] || 0.15; },

  // ── Writers（接收當下值，不自行存取全域狀態）──
  saveNodes(nodes)                 { saveJSON(K.nodes,               nodes); },
  saveEvents(events)               { saveJSON(K.events,              events); },
  saveTasks(tasks)                 { saveJSON(K.tasks,               tasks); },
  saveChat(chatHistory)            { saveJSON(K.chat,                chatHistory); },
  saveSales(salesData)             { saveJSON(K.sales,               salesData); },
  saveDailyReports(dailyReports)   { saveJSON(K.dailyReports,        dailyReports); },
  saveMonthlyGoals(monthlyGoals)   { saveJSON(K.monthlyGoals,        monthlyGoals); },
  saveMonthlySalesTargets(targets) { saveJSON(K.monthlySalesTargets, targets); },
  saveShortcuts(sk)                { saveJSON(K.shortcuts,           sk); },
  saveDocs(docsData)               { saveJSON(K.docs,                docsData); },
  saveStudents(studentsData)       { saveJSON(K.students,            studentsData); },

  saveCmd(mode, white, black) {
    localStorage.setItem(K.cmdMode,  mode);
    saveJSON(K.cmdWhite, [...white]);
    saveJSON(K.cmdBlack, [...black]);
  },

  // ── Loaders（回傳解析後資料，失敗回傳安全預設）──
  loadNodes()                { return loadJSON(K.nodes,               null); },
  loadEvents()               { return loadJSON(K.events,              []); },
  loadTasks()                { return loadJSON(K.tasks,               []); },
  loadChat()                 { return loadJSON(K.chat,                []); },
  loadSales()                { return loadJSON(K.sales,               []); },
  loadDailyReports()         { return loadJSON(K.dailyReports,        {}); },
  loadMonthlyGoals()         { return loadJSON(K.monthlyGoals,        {}); },
  loadMonthlySalesTargets()  { return loadJSON(K.monthlySalesTargets, {}); },
  loadShortcuts()            { return loadJSON(K.shortcuts,           null); },
  loadDocs()                 { return loadJSON(K.docs,                []); },
  loadStudents()             { return loadJSON(K.students,            []); },
  loadDrafts()               { return loadJSON(K.drafts,              {}); },

  loadCmdMode()  { return localStorage.getItem(K.cmdMode)  || 'blacklist'; },
  loadCmdWhite() { return new Set(loadJSON(K.cmdWhite, [])); },
  loadCmdBlack() { return new Set(loadJSON(K.cmdBlack, [])); },
};
