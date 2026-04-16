/**
 * features/ai/tools.js
 * CRM 工具定義 (Claude tool-use) + 執行邏輯
 * 依賴：core/state.js, core/store.js, core/calc.js
 */

import { getNodes, getEvents, getSalesData, getDailyReports, getDocsData, findNode, dispatch } from '../../core/state.js';
import { CALC } from '../../core/calc.js';
import { uid } from '../../core/uid.js';

// ── Tool schemas (Claude tool_use format) ─────────────────────────────────────

export const CRM_TOOLS = [
  {
    name: 'update_contact_status',
    description: '更新聯繫人的跟進狀態（綠/黃/紅）',
    input_schema: {
      type: 'object',
      properties: {
        name:   { type: 'string', description: '聯繫人姓名（模糊匹配）' },
        status: { type: 'string', enum: ['green', 'yellow', 'red'], description: '新狀態' },
      },
      required: ['name', 'status'],
    },
  },
  {
    name: 'add_note',
    description: '為聯繫人新增備注或跟進記錄',
    input_schema: {
      type: 'object',
      properties: {
        name: { type: 'string', description: '聯繫人姓名（模糊匹配）' },
        note: { type: 'string', description: '備注內容' },
      },
      required: ['name', 'note'],
    },
  },
  {
    name: 'log_contact',
    description: '記錄今日聯繫紀錄（方式、結果、備注）',
    input_schema: {
      type: 'object',
      properties: {
        name:   { type: 'string', description: '聯繫人姓名' },
        method: { type: 'string', description: '聯繫方式（電話/Line/面談等）' },
        result: { type: 'string', description: '聯繫結果' },
        note:   { type: 'string', description: '備注' },
      },
      required: ['name'],
    },
  },
  {
    name: 'get_followup_list',
    description: '取得需要跟進的聯繫人清單，依狀態與最後聯繫時間排序',
    input_schema: {
      type: 'object',
      properties: {
        status:   { type: 'string', enum: ['green', 'yellow', 'red', 'all'], description: '篩選狀態，預設all' },
        stale_days: { type: 'number', description: '超過幾天未聯繫才列出，預設7' },
      },
    },
  },
  {
    name: 'search_docs',
    description: '搜尋知識庫文件（話術、表單、FAQ等）',
    input_schema: {
      type: 'object',
      properties: {
        query: { type: 'string', description: '搜尋關鍵字' },
      },
      required: ['query'],
    },
  },
  {
    name: 'calculate_mortgage',
    description: '計算房貸月供、頭期款、所需月薪',
    input_schema: {
      type: 'object',
      properties: {
        price:      { type: 'number', description: '總價（萬元）' },
        down_pct:   { type: 'number', description: '頭期款成數（0-1，預設0.2）' },
        rate:       { type: 'number', description: '年利率（預設0.0216）' },
        years:      { type: 'number', description: '貸款年限（預設30）' },
        income_pct: { type: 'number', description: '月供佔月薪比例上限（預設0.6）' },
      },
      required: ['price'],
    },
  },
  {
    name: 'read_calendar_events',
    description: '讀取近期活動行程',
    input_schema: {
      type: 'object',
      properties: {
        days: { type: 'number', description: '查詢未來幾天的活動，預設14' },
      },
    },
  },
  {
    name: 'get_contact_detail',
    description: '取得聯絡人完整資料（財務、背景、所有 info 欄位）',
    input_schema: {
      type: 'object',
      properties: { name: { type: 'string' } },
      required: ['name'],
    },
  },
  {
    name: 'list_contacts',
    description: '列出所有聯絡人，可按狀態篩選',
    input_schema: {
      type: 'object',
      properties: {
        status: { type: 'string', description: 'green/yellow/red/all' },
        limit:  { type: 'number' },
      },
    },
  },
  {
    name: 'add_event',
    description: '新增行事曆事件',
    input_schema: {
      type: 'object',
      required: ['title', 'date'],
      properties: {
        title: { type: 'string' },
        date:  { type: 'string', description: 'YYYY-MM-DD' },
        time:  { type: 'string' },
        notes: { type: 'string' },
      },
    },
  },
  {
    name: 'update_daily_kpi',
    description: '更新今日活動量實績（邀約/電訪/表單/追蹤/成交）',
    input_schema: {
      type: 'object',
      properties: {
        invite:  { type: 'number' },
        calls:   { type: 'number' },
        forms:   { type: 'number' },
        followup:{ type: 'number' },
        close:   { type: 'number' },
      },
    },
  },
  {
    name: 'add_sale',
    description: '記錄新成交',
    input_schema: {
      type: 'object',
      required: ['name', 'product'],
      properties: {
        name:    { type: 'string', description: '客戶姓名' },
        product: { type: 'string', description: '產品' },
        amount:  { type: 'number' },
        date:    { type: 'string', description: 'YYYY-MM-DD' },
        notes:   { type: 'string' },
      },
    },
  },
  {
    name: 'patch_daily_report',
    description: '修改今日日報表任意欄位（三件大事、復盤、明天計劃等）',
    input_schema: {
      type: 'object',
      properties: {
        bigThree:  { type: 'array', items: { type: 'string' } },
        optimize:  { type: 'string' },
        tomorrow:  { type: 'string' },
        gratitude: { type: 'string' },
      },
    },
  },
];

// ── Helpers ───────────────────────────────────────────────────────────────────

function fuzzyFind(name) {
  const nodes = getNodes();
  const q = name.trim().toLowerCase();
  return nodes.find(n => n.name && n.name.toLowerCase().includes(q) && n.parentId !== null) || null;
}

// ── executeToolCall ───────────────────────────────────────────────────────────

export async function executeToolCall(name, input = {}) {
  switch (name) {
    case 'update_contact_status': {
      const n = fuzzyFind(input.name || '');
      if (!n) return { ok: false, error: `找不到聯繫人：${input.name}` };
      dispatch({ type: 'NODE_UPDATE', payload: { id: n.id, patch: { status: input.status } } });
      return { ok: true, message: `已將 ${n.name} 狀態更新為 ${input.status}` };
    }

    case 'add_note': {
      const n = fuzzyFind(input.name || '');
      if (!n) return { ok: false, error: `找不到聯繫人：${input.name}` };
      const prev = n.info?.notes || '';
      const today = new Date().toISOString().slice(0, 10);
      const updated = prev ? `${prev}\n[${today}] ${input.note}` : `[${today}] ${input.note}`;
      dispatch({ type: 'NODE_UPDATE', payload: { id: n.id, patch: { info: { ...n.info, notes: updated } } } });
      return { ok: true, message: `已為 ${n.name} 新增備注` };
    }

    case 'log_contact': {
      const n = fuzzyFind(input.name || '');
      if (!n) return { ok: false, error: `找不到聯繫人：${input.name}` };
      const today = new Date().toISOString().slice(0, 10);
      const entry = {
        id:     uid(),
        date:   today,
        method: input.method || '電話',
        result: input.result || '',
        note:   input.note   || '',
      };
      const history = Array.isArray(n.info?.contactHistory) ? [...n.info.contactHistory, entry] : [entry];
      dispatch({ type: 'NODE_UPDATE', payload: { id: n.id, patch: { info: { ...n.info, contactHistory: history, lastContact: today } } } });
      return { ok: true, message: `已記錄 ${n.name} 的聯繫紀錄`, entry };
    }

    case 'get_followup_list': {
      const statusFilter = input.status || 'all';
      const staleDays    = input.stale_days ?? 7;
      const today        = new Date().toISOString().slice(0, 10);
      const nodes        = getNodes().filter(n => n.parentId !== null && n.name && n.name !== '新聯繫人');

      const filtered = nodes.filter(n => {
        if (statusFilter !== 'all' && n.status !== statusFilter) return false;
        if (!n.info?.lastContact) return true;
        const days = Math.floor((new Date(today) - new Date(n.info.lastContact)) / 86400000);
        return days >= staleDays;
      });

      const list = filtered.map(n => ({
        name:        n.name,
        status:      n.status,
        lastContact: n.info?.lastContact || '從未',
        daysSince:   n.info?.lastContact
          ? Math.floor((new Date(today) - new Date(n.info.lastContact)) / 86400000)
          : null,
        notes: n.info?.notes?.slice(0, 60) || '',
      })).sort((a, b) => (b.daysSince ?? 999) - (a.daysSince ?? 999));

      return { ok: true, count: list.length, list };
    }

    case 'search_docs': {
      const docs  = getDocsData();
      const q     = (input.query || '').toLowerCase();
      const found = docs.filter(d =>
        (d.name || '').toLowerCase().includes(q) ||
        (d.description || '').toLowerCase().includes(q) ||
        (d.tags || []).some(t => t.toLowerCase().includes(q))
      );
      return { ok: true, count: found.length, docs: found.map(d => ({ name: d.name, type: d.type, url: d.url || '', description: d.description || '' })) };
    }

    case 'calculate_mortgage': {
      const price     = Number(input.price)      || 0;   // 萬
      const downPct   = Number(input.down_pct)   || 0.2;
      const rate      = Number(input.rate)        || 0.0216;
      const years     = Number(input.years)       || 30;
      const incPct    = Number(input.income_pct)  || 0.6;
      const loanAmt   = price * (1 - downPct);            // 萬
      const monthly_r = rate / 12;
      const n_months  = years * 12;
      const monthly   = loanAmt > 0
        ? Math.round(loanAmt * 10000 * monthly_r * Math.pow(1 + monthly_r, n_months) / (Math.pow(1 + monthly_r, n_months) - 1))
        : 0;
      const minSalary = Math.round(monthly / incPct);
      return {
        ok: true,
        price_wan:      price,
        down_wan:       Math.round(price * downPct * 10) / 10,
        loan_wan:       Math.round(loanAmt * 10) / 10,
        monthly_payment: monthly,
        min_monthly_salary: minSalary,
        rate_pct:       (rate * 100).toFixed(2) + '%',
        years,
      };
    }

    case 'read_calendar_events': {
      const days   = Number(input.days) || 14;
      const today  = new Date().toISOString().slice(0, 10);
      const cutoff = new Date(); cutoff.setDate(cutoff.getDate() + days);
      const endStr = cutoff.toISOString().slice(0, 10);
      const events = getEvents()
        .filter(ev => ev.date >= today && ev.date <= endStr)
        .sort((a, b) => a.date.localeCompare(b.date))
        .map(ev => ({ date: ev.date, time: ev.time || '', type: ev.type || '', location: ev.location || '', notes: ev.notes || '' }));
      return { ok: true, count: events.length, events };
    }

    case 'get_contact_detail': {
      const n = fuzzyFind(input.name || '');
      if (!n) return { ok: false, error: `找不到聯絡人：${input.name}` };
      return { ok: true, contact: n };
    }

    case 'list_contacts': {
      const statusFilter = input.status || 'all';
      const limitN       = Number(input.limit) || 100;
      let list = getNodes().filter(n => n.parentId !== null && n.name && n.name !== '新聯繫人');
      if (statusFilter !== 'all') list = list.filter(n => n.status === statusFilter);
      list = list.slice(0, limitN).map(n => ({
        id:          n.id,
        name:        n.name,
        status:      n.status,
        phone:       n.info?.phone || '',
        lastContact: n.info?.lastContact || '',
        notes:       (n.info?.notes || '').slice(0, 80),
      }));
      return { ok: true, count: list.length, list };
    }

    case 'add_event': {
      const today = new Date().toISOString().slice(0, 10);
      const event = {
        id:        uid(),
        title:     input.title,
        date:      input.date,
        time:      input.time  || '',
        notes:     input.notes || '',
        createdAt: Date.now(),
      };
      dispatch({ type: 'EVENT_ADD', payload: event });
      return { ok: true, message: `已新增活動「${event.title}」於 ${event.date}`, event };
    }

    case 'update_daily_kpi': {
      const today = new Date().toISOString().slice(0, 10);
      const patch = {};
      if (input.invite   != null) patch['act-invite']  = Number(input.invite);
      if (input.calls    != null) patch['act-calls']   = Number(input.calls);
      if (input.forms    != null) patch['act-forms']   = Number(input.forms);
      if (input.followup != null) patch['act-followup']= Number(input.followup);
      if (input.close    != null) patch['act-close']   = Number(input.close);
      dispatch({ type: 'DAILY_REPORT_PATCH', payload: { date: today, patch } });
      return { ok: true, message: '已更新今日活動量', patch };
    }

    case 'add_sale': {
      const today = new Date().toISOString().slice(0, 10);
      const sale = {
        id:        uid(),
        name:      input.name,
        product:   input.product,
        amount:    Number(input.amount) || 0,
        date:      input.date || today,
        notes:     input.notes || '',
        createdAt: Date.now(),
      };
      dispatch({ type: 'SALE_ADD', payload: sale });
      return { ok: true, message: `已記錄 ${sale.name} 的成交 $${sale.amount.toLocaleString()}`, sale };
    }

    case 'patch_daily_report': {
      const today = new Date().toISOString().slice(0, 10);
      const patch = {};
      if (input.bigThree  != null) patch.bigThree  = input.bigThree;
      if (input.optimize  != null) patch.optimize  = input.optimize;
      if (input.tomorrow  != null) patch.tomorrow  = input.tomorrow;
      if (input.gratitude != null) patch.gratitude = input.gratitude;
      dispatch({ type: 'DAILY_REPORT_PATCH', payload: { date: today, patch } });
      return { ok: true, message: '已更新今日日報', patch };
    }

    default:
      return { ok: false, error: `未知工具：${name}` };
  }
}
