/**
 * features/ai/personas.js
 * Persona 定義 + Memory Service + System Prompt 建立
 * 依賴：core/state.js, core/store.js, features/ai/providers.js
 *
 * rolePrompt / quickPrompts 外移到 personas.json，懶載入
 */

import { getNodes, getEvents, getSalesData, getDailyReports, getMonthlySalesTargets, getDocsData } from '../../core/state.js';
import { STORE } from '../../core/store.js';
import { CALC } from '../../core/calc.js';

// ── Persona config（懶載入）────────────────────────────────────────────────

const PERSONA_SKELETON = {
  assistant:  { label: '通用助理' },
  coach:      { label: '跟進教練' },
  analyst:    { label: '業績分析師' },
  strategist: { label: '人脈策略師' },
  secretary:  { label: '日報小秘書' },
  closer:     { label: '成交專家' },
  docfinder:  { label: '知識庫助理' },
};

let _personaData = null;

async function loadPersonaData() {
  if (_personaData) return _personaData;
  try {
    const res = await fetch('./src/features/ai/personas.json');
    _personaData = await res.json();
  } catch (e) {
    console.warn('[personas] 載入 personas.json 失敗，使用 fallback', e);
    _personaData = Object.fromEntries(
      Object.entries(PERSONA_SKELETON).map(([k, v]) => [k, { ...v, rolePrompt: `你是${v.label}。`, quickPrompts: [] }])
    );
  }
  return _personaData;
}

export const PERSONA_CONFIG = PERSONA_SKELETON;

// ── Persona state ─────────────────────────────────────────────────────────────

let _currentPersona = 'assistant';
let _quickPrompts   = [];

export const getCurrentPersona = () => _currentPersona;

export function setPersona(key, el) {
  _currentPersona = key;
  document.querySelectorAll('.persona-pill').forEach(p => p.classList.remove('active'));
  if (el) el.classList.add('active');
  renderQuickPrompts(key);
}

export async function renderQuickPrompts(key) {
  const bar = document.getElementById('ai-quick-prompts');
  if (!bar) return;
  const data = await loadPersonaData();
  _quickPrompts = (data[key] || data.assistant || {}).quickPrompts || [];
  bar.innerHTML = _quickPrompts.map((p, i) =>
    `<button class="quick-prompt-chip" onclick="window.__crmInjectPrompt?.(${i})">${p}</button>`
  ).join('');
}

export function injectPrompt(idx) {
  const text = typeof idx === 'number' ? (_quickPrompts[idx] || '') : idx;
  const inp = document.getElementById('chat-input');
  if (!inp) return;
  inp.value = text; inp.focus();
  inp.style.height = 'auto';
  inp.style.height = Math.min(inp.scrollHeight, 120) + 'px';
}

// ── Memory Service ─────────────────────────────────────────────────────────────

export const memoryService = {
  base: '/api/memories',

  async list(opts = {}) {
    try {
      const p = new URLSearchParams();
      if (opts.subject) p.set('subject', opts.subject);
      if (opts.type)    p.set('type',    opts.type);
      if (opts.pinned != null) p.set('pinned', opts.pinned);
      if (opts.includeArchived) p.set('includeArchived', 'true');
      const r = await fetch(`${this.base}?${p}`);
      if (!r.ok) return [];
      return (await r.json()).memories || [];
    } catch { return []; }
  },

  async create(mem) {
    try {
      const r = await fetch(this.base, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(mem) });
      return r.ok ? await r.json() : null;
    } catch { return null; }
  },

  async update(id, patch) {
    try {
      const r = await fetch(`${this.base}/${id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
      return r.ok ? await r.json() : null;
    } catch { return null; }
  },

  async delete(id) {
    try { return (await fetch(`${this.base}/${id}`, { method: 'DELETE' })).ok; }
    catch { return false; }
  },

  async retrieve(message, context = {}) {
    try {
      const r = await fetch(`${this.base}/retrieve`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, context, topK: 5 }),
      });
      return r.ok ? await r.json() : { memories: [], promptSnippet: '' };
    } catch { return { memories: [], promptSnippet: '' }; }
  },
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function buildFinanceSummary(info) {
  if (!info) return '未填';
  const parts = [];
  if (info.income)      parts.push(`月收${info.income}`);
  if (info.hasProperty) parts.push('有房');
  if (info.hasInvestment) parts.push('有投資');
  if (info.debt)        parts.push(`負債${info.debt}`);
  return parts.length ? parts.join(',') : '未填';
}

const STATUS_EMOJI = { green: '🟢高意願', yellow: '🟡觀察中', red: '🔴冷淡' };

// ── System prompt ─────────────────────────────────────────────────────────────

export async function buildSystemPrompt(personaKey, memSnippet = '') {
  const data    = await loadPersonaData();
  const persona = data[personaKey || 'assistant'] || data.assistant;
  const login      = JSON.parse(localStorage.getItem('crm-login') || '{}');
  const myRank     = STORE.getMyRank();
  const myRate     = STORE.getMyRate();
  const now        = new Date();
  const today      = now.toISOString().slice(0, 10);
  const monthPrefix = today.slice(0, 7);
  const daysLeft   = new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() - now.getDate();

  const nodes        = getNodes();
  const contactNodes = nodes.filter(n => n.parentId !== null);
  const green        = contactNodes.filter(n => n.status === 'green');
  const yellow       = contactNodes.filter(n => n.status === 'yellow');
  const red          = contactNodes.filter(n => n.status === 'red');
  const stale        = contactNodes.filter(n => {
    if (!n.info?.lastContact) return false;
    return Math.floor((new Date(today) - new Date(n.info.lastContact)) / 86400000) > 7
      && (n.status === 'green' || n.status === 'yellow');
  }).map(n => `${n.name}（${Math.floor((new Date(today) - new Date(n.info.lastContact)) / 86400000)}天）`);

  const salesData          = getSalesData();
  const dailyReports       = getDailyReports();
  const monthlySalesTargets = getMonthlySalesTargets();
  const docsData           = getDocsData();
  const events             = getEvents();

  const summary     = CALC.monthSummary(salesData, myRate, monthPrefix);
  const salesTarget = monthlySalesTargets[monthPrefix] || 300000;
  const salesPct    = salesTarget > 0 ? Math.round(summary.income / salesTarget * 100) : 0;
  const todayRpt    = dailyReports[today] || {};
  const upcoming    = events.filter(ev => ev.date >= today).slice(0, 5).map(ev => `${ev.date} ${ev.title || ev.name || ''}`);
  const rankLabels  = { director: '主任', asst_mgr: '襄理', manager: '經理', shop_partner: '店股東', shop_head: '店長' };

  const top20 = [...contactNodes]
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    .slice(0, 20);

  const contactsDetail = top20.map(n => {
    const info = n.info || {};
    const lastC = info.lastContact || '未填';
    const daysDiff = info.lastContact
      ? Math.floor((new Date(today) - new Date(info.lastContact)) / 86400000) : null;
    const daysStr = daysDiff !== null ? `（${daysDiff}天前）` : '';
    const statusStr = STATUS_EMOJI[n.status] || n.status || '未知';
    return `- ${n.name}｜${statusStr}｜電話:${info.phone || '未填'}｜最後聯繫:${lastC}${daysStr}｜備注:${info.notes || '無'}｜財務:${buildFinanceSummary(info)}`;
  }).join('\n');

  const monthSales = salesData
    .filter(s => (s.date || '').startsWith(monthPrefix))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  const salesLines = monthSales.map(s =>
    `- ${s.date || '?'} ${s.name || s.clientName || '?'} ${s.product || s.type || ''} $${(s.amount || 0).toLocaleString()}`
  ).join('\n');

  let dailyRptBlock = '';
  if (Object.keys(todayRpt).length > 0) {
    const bigThreeStr = Array.isArray(todayRpt.bigThree)
      ? todayRpt.bigThree.map((t, i) => `${i + 1}.${t}`).join(' ')
      : (todayRpt.bigThree || '');
    const lines = [];
    if (bigThreeStr)        lines.push(`三件大事: ${bigThreeStr}`);
    if (todayRpt.schedule)  lines.push(`時間安排: ${todayRpt.schedule}`);
    const kpiStr = `邀約${todayRpt['act-invite'] ?? todayRpt.invite ?? 0} 電訪${todayRpt['act-calls'] ?? todayRpt.calls ?? 0} 表單${todayRpt['act-forms'] ?? todayRpt.forms ?? 0}`;
    lines.push(`今日實績: ${kpiStr}`);
    if (todayRpt.optimize)  lines.push(`復盤: ${todayRpt.optimize}`);
    if (todayRpt.tomorrow)  lines.push(`明天計劃: ${todayRpt.tomorrow}`);
    dailyRptBlock = `\n【今日日報】\n${lines.join('\n')}`;
  }

  const studentsData = nodes.filter(n => n.type === 'student' || n.isStudent);
  let studentsBlock = '';
  if (studentsData.length > 0) {
    const recentStudents = [...studentsData]
      .sort((a, b) => (a.info?.lastContact || '').localeCompare(b.info?.lastContact || '') * -1)
      .slice(0, 5)
      .map(s => {
        const lc = s.info?.lastContact;
        const days = lc ? Math.floor((new Date(today) - new Date(lc)) / 86400000) : null;
        return `${s.name}(${days !== null ? days + '天前' : '未聯繫'})`;
      });
    studentsBlock = `\n【學員】共${studentsData.length}人｜最近聯繫: ${recentStudents.join(', ')}`;
  }

  return `${persona.rolePrompt}
${memSnippet ? '\n' + memSnippet + '\n' : ''}
【使用者】${login.name || '業務員'}｜${rankLabels[myRank] || myRank}｜佣金率 ${(myRate * 100).toFixed(0)}%
【今日】${today}，月底還有 ${daysLeft} 天
【本月業績】$${summary.income.toLocaleString()} / 目標 $${salesTarget.toLocaleString()}（${salesPct}%）稅後 $${summary.net.toLocaleString()}，成交 ${summary.newCount} 件
【人脈概況】共 ${contactNodes.length} 人｜🟢高意願 ${green.length}（${green.map(n => n.name).join('、') || '無'}）｜🟡觀察中 ${yellow.length}｜🔴冷淡 ${red.length}
⚠ 超過7天未聯繫：${stale.join('、') || '無'}
【今日活動量】邀約${todayRpt['act-invite'] ?? todayRpt.invite ?? 0} 電訪${todayRpt['act-calls'] ?? todayRpt.calls ?? 0} 表單${todayRpt['act-forms'] ?? todayRpt.forms ?? 0} 追蹤${todayRpt['act-followup'] ?? todayRpt.followup ?? 0} 成交${todayRpt['act-close'] ?? todayRpt.close ?? 0}
【近期活動】${upcoming.length ? upcoming.join('；') : '無'}

【聯絡人詳情】
${contactsDetail || '（無聯絡人）'}

【本月成交】
${salesLines || '（本月尚無成交記錄）'}
${dailyRptBlock}${studentsBlock}

【知識庫文件】${docsData.length ? docsData.map(d => {
  const icon = { poster: '🖼', form: '📋', link: '🔗', file: '📄' }[d.type] || '📄';
  return `${icon}《${d.name}》${d.url ? '→ ' + d.url : ''}`;
}).join('　') : '尚無文件'}

【可用工具】update_contact_status / add_note / log_contact / get_followup_list / search_docs / calculate_mortgage / read_calendar_events / get_contact_detail / list_contacts / add_event / update_daily_kpi / add_sale / patch_daily_report / add_student / list_students
【重要】當用戶要求「新增學員」、「加到學員頁」、「幫我把 XXX 加為學員」，必須呼叫 add_student 工具，不能只用文字回應。工具執行後才算完成。

【海報生成】當用戶要求製作活動海報，請提取時間與地點，直接回覆以下格式：
👉 [點此預覽並下載海報](https://fdd-crm.pages.dev/poster.html?time=TIME&loc=LOCATION)
然後補充：「海報已帶入時間和地點，點開後直接下載 PNG 即可。」

請用繁體中文回答，語氣專業親切，重點條列清晰。`;
}
