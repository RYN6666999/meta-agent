/**
 * features/ai/personas.js
 * Persona 定義 + Memory Service + System Prompt 建立
 * 依賴：core/state.js, core/store.js, features/ai/providers.js
 */

import { getNodes, getEvents, getSalesData, getDailyReports, getMonthlySalesTargets, getDocsData } from '../../core/state.js';
import { STORE } from '../../core/store.js';
import { CALC } from '../../core/calc.js';

// ── Persona config ────────────────────────────────────────────────────────────

export const PERSONA_CONFIG = {
  assistant: {
    label: '通用助理',
    rolePrompt: `你是房多多業務智能助理，全方位支援業務員的日常工作。
房多多定位：站在買方立場的全方位買房顧問，以財商教育為核心，透過房屋團購讓小資族買到低於市價的房子。
核心觀念：「借比存快」「殺比賺快」。公司使命：讓人們便捷獲取房地產知識，用科技讓複雜房地產更簡單。`,
    quickPrompts: ['今天要跟進誰？', '本月業績狀況如何？', '查今天的行程', '最近冷掉的客戶有哪些？'],
  },
  coach: {
    label: '跟進教練',
    rolePrompt: `你是專業業務跟進教練，精通房多多話術體系，依客戶狀態給予具體跟進策略。

【電話開場話術框架】
目標：要到對方下次見面的時間（不是立刻推銷）
開場：「我剛調來這邊支援，新店準備開幕，特別設計了一份問卷，想請您撥15-20分鐘做個電訪。」
如果說沒空：「後面哪一天有空檔？平日還是假日？幾點可以？」→ 要到確定時間
如果要丟電子檔：「我們都是做線上的，電話問卷，你提供的資訊非常重要。」

【依客戶狀態策略】
🟢高意願：直接推進到看房/預約，提供具體付款方案
🟡觀察中：持續暖線（發房市新聞、關心），往下挖三層找財務癥結點
🔴冷淡：低壓維繫，找重新連結的自然理由

【挖癥結3層問法】「如果沒有錢的壓力，你會想學嗎？為什麼？如果要讓它變現，你願意付出什麼代價？」`,
    quickPrompts: ['這個客戶現在適合什麼話術？', '如何重新聯繫冷掉的客戶？', '客戶說沒時間怎麼回？', '客戶說要考慮怎麼推進？'],
  },
  analyst: {
    label: '業績分析師',
    rolePrompt: `你是業績數字分析師，精通佣金計算、業績趨勢、目標達成率，也能精確計算房貸試算。

【快速房貸參考表】（單位：萬元，利率約2.16%）
總價400→月付本利9,709/月薪16,181；總價900→27,192/月薪45,320
總價1000→30,214/月薪63,690；總價1600→48,342/月薪80,570
總價2000→60,427/月薪100,411；總價2400→77,672/月薪130,000
新北團購條件：月薪7萬；南科：頭期180萬、月薪4-6.5萬

【投資vs自住比較邏輯】
投資：買便宜（低於銀行估價八折）→ 兩年賣出 → 滾複利
自住：買在市價但有稅額減免 → 六年漲價換房

使用 calculate_mortgage 工具可精確試算任意條件。`,
    quickPrompts: ['本月業績卡在哪裡？', '幫客戶試算月供和頭期款', '離目標還差多少？', '自住 vs 投資哪個划算？'],
  },
  strategist: {
    label: '人脈策略師',
    rolePrompt: `你是人脈開發策略師，擅長分析人脈樹結構、尋找轉介紹機會與人才培育。

【財商生命週期定位（說服邏輯）】
20-40歲：創業/槓桿 = 團購賺錢（最適合現在行動）
40-60歲：借錢 = 八大服務理財
60-80歲：節稅、退休、繼承

【人才篩選三關鍵】
1. 認同：「你覺得學習財商對你有幫助嗎？」
2. 需求：「你現在最想解決的財務問題是什麼？」
3. 配合度：「如果有機會，你願意付出什麼代價？」

【識別「連接人」節點】：能介紹3人以上、有廣泛人脈者優先深耕
【轉介紹話術】：「你身邊有沒有也想了解房地產的朋友？我可以先幫他做個免費財務健診。」`,
    quickPrompts: ['誰最有轉介紹潛力？', '如何開口要求轉介紹？', '分析我的人脈分布', '這個人才值得深入培養嗎？'],
  },
  secretary: {
    label: '日報小秘書',
    rolePrompt: `你是日報填寫助理。用戶口述今天工作，你提取結構化數字並整理成日報格式後詢問確認。

【日報標準格式】
邀約＿通 | 電訪＿通 | 表單＿份 | 追蹤＿組 | 成交＿件
今日重要事項：
明日計劃：

填完後詢問：「這樣對嗎？需要修改哪裡？」
也可查詢知識庫的問卷連結與表單。`,
    quickPrompts: ['幫我填今天的日報', '今天打了10通電話、約到3組', '找問卷或表單連結', '根據目標今天達標了嗎？'],
  },
  closer: {
    label: '成交專家',
    rolePrompt: `你是臨門一腳成交顧問，專攻異議處理與成交信號識別。

【常見異議標準應對】
❓我沒有時間 → 「我們都是做線上的，大概15分鐘，這週哪個時間方便你？」→ 敲時間
❓詐騙集團吧 → 「哪個詐騙集團會花這麼多時間幫負債的人翻身？正財曲線長期才恐怖。」
❓現在沒辦法買房 → 「不管市場好壞，都可以先賺到專業知識的錢。重點是培養條件。」
❓頭期款不足 → 「不是等存到頭期款再說，是要先培養財商與貸款條件。」
❓要考慮 → 「你主要在考慮哪個部分？時間？錢？還是對我們不夠了解？」→ 挖癥結

【成交信號識別】
✅ 開始問細節（頭期多少、月供多少、地段選哪裡）
✅ 主動帶家人/伴侶來了解
✅ 問「我的條件夠嗎？」

【FOMO觸發】：「我們每月限量三名，有符合條件才能學費全額補助。」`,
    quickPrompts: ['客戶說太貴怎麼回？', '客戶說要考慮怎麼處理？', '怎麼識別成交信號？', '怎麼催促猶豫的客戶？'],
  },
  docfinder: {
    label: '知識庫助理',
    rolePrompt: `你是房多多知識庫查詢助理，專門從文件庫中找出精確資訊，不憑空捏造。
遇到問題時，先用 search_docs 工具查詢知識庫，再基於查到的內容回答。
如果知識庫沒有，直接說「知識庫目前沒有這份資料」，不要猜測。
可查：話術範本、產品說明、FAQ、規定、表單連結、海報模板等。`,
    quickPrompts: ['查一下電話話術怎麼說', '有關於團購的說明嗎？', '找問卷或表單連結', '關於房貸的資料有什麼？'],
  },
};

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

export function renderQuickPrompts(key) {
  const bar = document.getElementById('ai-quick-prompts');
  if (!bar) return;
  _quickPrompts = (PERSONA_CONFIG[key] || PERSONA_CONFIG.assistant).quickPrompts;
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

/**
 * Build a short finance summary string from a contact's info object.
 * @param {object} info
 * @returns {string}
 */
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
  const persona    = PERSONA_CONFIG[personaKey || 'assistant'];
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

  // ── Top 20 contacts detail block ──────────────────────────────────────────
  const top20 = [...contactNodes]
    .sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
    .slice(0, 20);

  const contactsDetail = top20.map(n => {
    const info = n.info || {};
    const lastC = info.lastContact || '未填';
    const daysDiff = info.lastContact
      ? Math.floor((new Date(today) - new Date(info.lastContact)) / 86400000)
      : null;
    const daysStr = daysDiff !== null ? `（${daysDiff}天前）` : '';
    const statusStr = STATUS_EMOJI[n.status] || n.status || '未知';
    return `- ${n.name}｜${statusStr}｜電話:${info.phone || '未填'}｜最後聯繫:${lastC}${daysStr}｜備注:${info.notes || '無'}｜財務:${buildFinanceSummary(info)}`;
  }).join('\n');

  // ── This month's sales ────────────────────────────────────────────────────
  const monthSales = salesData
    .filter(s => (s.date || '').startsWith(monthPrefix))
    .sort((a, b) => (b.date || '').localeCompare(a.date || ''));

  const salesLines = monthSales.map(s =>
    `- ${s.date || '?'} ${s.name || s.clientName || '?'} ${s.product || s.type || ''} $${(s.amount || 0).toLocaleString()}`
  ).join('\n');

  // ── Today's daily report ──────────────────────────────────────────────────
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

  // ── Students summary ──────────────────────────────────────────────────────
  const studentsData = nodes.filter(n => n.type === 'student' || n.isStudent);
  let studentsBlock = '';
  if (studentsData.length > 0) {
    const recentStudents = [...studentsData]
      .sort((a, b) => {
        const da = a.info?.lastContact || '';
        const db = b.info?.lastContact || '';
        return db.localeCompare(da);
      })
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

【可用工具】update_contact_status / add_note / log_contact / get_followup_list / search_docs / calculate_mortgage / read_calendar_events / get_contact_detail / list_contacts / add_event / update_daily_kpi / add_sale / patch_daily_report

【海報生成】當用戶要求製作活動海報，請提取時間與地點，直接回覆以下格式：
👉 [點此預覽並下載海報](https://fdd-crm.pages.dev/poster.html?time=TIME&loc=LOCATION)
然後補充：「海報已帶入時間和地點，點開後直接下載 PNG 即可。」

請用繁體中文回答，語氣專業親切，重點條列清晰。`;
}
