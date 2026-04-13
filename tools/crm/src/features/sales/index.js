/**
 * features/sales/index.js
 * 業績頁：CRUD + 月份導覽 + 成交表單
 * 依賴：core/state.js, core/toast.js, core/calc.js, core/store.js, core/uid.js
 */

import { getSalesData, getNodes, dispatch } from '../../core/state.js';
import { STORE } from '../../core/store.js';
import { CALC } from '../../core/calc.js';
import { toast } from '../../core/toast.js';
import { uid } from '../../core/uid.js';

// ── Products ──────────────────────────────────────────────────────────────────

const PRODUCTS = {
  student:     { label: '學員',         price: 79800 },
  member:      { label: '會員服務',     price: 200000 },
  vip:         { label: 'VIP買房服務', price: 300000 },
  asst_mgr_pkg:{ label: '襄理批貨',    price: 478800 },
  manager_pkg: { label: '經理批貨',    price: 1197000 },
  consult:     { label: '協談+',       price: 2394 },
};

// ── State ─────────────────────────────────────────────────────────────────────

let _salesYear  = new Date().getFullYear();
let _salesMonth = new Date().getMonth(); // 0-based
let _editingSaleId = null;

// ── Render ────────────────────────────────────────────────────────────────────

export function renderSalesPage() {
  const MONTHS = ['1月','2月','3月','4月','5月','6月','7月','8月','9月','10月','11月','12月'];
  const label = document.getElementById('sales-month-label');
  if (label) label.textContent = `${_salesYear} 年 ${MONTHS[_salesMonth]}`;

  const monthPrefix = `${_salesYear}-${String(_salesMonth + 1).padStart(2, '0')}`;
  const salesData = getSalesData();
  const myRate    = STORE.getMyRate();
  const summary   = CALC.monthSummary(salesData, myRate, monthPrefix);
  const body      = document.getElementById('sales-body');
  if (!body) return;

  const rows = summary.sorted.map(s => {
    const prod = PRODUCTS[s.product] || { label: s.product || '—' };
    const income = CALC.saleIncome(s, myRate);
    const tax    = income * 0.1211;
    const net    = income - tax;
    return `<div class="sale-row">
      <div class="sale-row-left">
        <span class="sale-date">${s.date || ''}</span>
        <span class="sale-product">${prod.label}</span>
        ${s.notes ? `<span class="sale-notes">${_esc(s.notes)}</span>` : ''}
      </div>
      <div class="sale-row-right">
        <span class="sale-amount">NT$ ${s.amount.toLocaleString()}</span>
        <span class="sale-income" style="color:var(--accent)">+$${income.toLocaleString()}</span>
        <button class="btn btn-sm btn-ghost" onclick="window.__crmOpenSaleModal?.('${s.id}')">✏</button>
        <button class="btn btn-sm btn-ghost" onclick="window.__crmDeleteSale?.('${s.id}')">🗑</button>
      </div>
    </div>`;
  }).join('');

  body.innerHTML = `
    <div class="sales-summary-bar">
      <div class="sum-item"><span>業績</span><strong>$${summary.gross.toLocaleString()}</strong></div>
      <div class="sum-item"><span>佣金</span><strong style="color:var(--accent)">$${summary.income.toLocaleString()}</strong></div>
      <div class="sum-item"><span>稅後</span><strong style="color:var(--green)">$${summary.net.toLocaleString()}</strong></div>
      <div class="sum-item"><span>件數</span><strong>${summary.newCount}</strong></div>
    </div>
    ${rows || '<div class="empty-state">本月尚無業績，點右上角新增</div>'}`;
}

// ── Navigation ────────────────────────────────────────────────────────────────

export function salesPrevMonth() {
  _salesMonth--;
  if (_salesMonth < 0) { _salesMonth = 11; _salesYear--; }
  renderSalesPage();
}

export function salesNextMonth() {
  _salesMonth++;
  if (_salesMonth > 11) { _salesMonth = 0; _salesYear++; }
  renderSalesPage();
}

export function salesGoToday() {
  const d = new Date();
  _salesYear  = d.getFullYear();
  _salesMonth = d.getMonth();
  renderSalesPage();
}

// ── Modal ─────────────────────────────────────────────────────────────────────

export function openSaleModal(id) {
  _editingSaleId = id || null;
  const salesData = getSalesData();
  const s = id ? salesData.find(x => x.id === id) : null;
  const today = new Date().toISOString().slice(0, 10);

  // Participant tags
  const contactNodes = getNodes().filter(n => n.parentId !== null && n.name && n.name !== '新聯繫人');
  const selPax = s?.participants || [];
  const paxTags = contactNodes.map(n =>
    `<div class="ev-pax${selPax.includes(n.id) ? ' selected' : ''}" data-nid="${n.id}" onclick="this.classList.toggle('selected')">
      <span class="sdot ${n.status || 'gray'}"></span>${_esc(n.name)}
    </div>`
  ).join('') || '<span style="color:var(--text-muted);font-size:12px">尚無人脈節點</span>';

  document.getElementById('sale-modal-title-text').textContent = s ? '編輯成交' : '新增成交';
  const saleType = s?.saleType || 'new';
  document.querySelectorAll('input[name="sale-type"]').forEach(r => r.checked = r.value === saleType);
  document.getElementById('sale-product').value = s?.product || 'student';
  document.getElementById('sale-date').value    = s?.date    || today;
  document.getElementById('sale-notes').value   = s?.notes   || '';
  document.getElementById('sale-pax').innerHTML = paxTags;
  _syncSaleAmount(s?.amount || null);
  _onSaleTypeChange();
  _onSaleProductChange();
  document.getElementById('sale-modal')?.classList.add('open');
}

export function closeSaleModal() {
  document.getElementById('sale-modal')?.classList.remove('open');
  _editingSaleId = null;
}

export function saveSale() {
  const saleType = document.querySelector('input[name="sale-type"]:checked')?.value || 'new';
  const product  = document.getElementById('sale-product')?.value || 'student';
  const date     = document.getElementById('sale-date')?.value   || '';
  const notes    = document.getElementById('sale-notes')?.value  || '';
  const qty      = parseInt(document.getElementById('sale-qty')?.value) || 1;
  const batchby  = document.querySelector('input[name="sale-batchby"]:checked')?.value || 'self';
  const samerank = document.querySelector('input[name="sale-samerank"]:checked')?.value || 'self';
  const participants = [...document.querySelectorAll('#sale-pax .ev-pax.selected')].map(el => el.dataset.nid);

  let amount;
  if (saleType === 'transfer') {
    amount = _parseAmount();
  } else {
    const prod = PRODUCTS[product];
    if (!prod) { toast('請選擇產品'); return; }
    amount = product === 'consult' ? prod.price * qty : prod.price;
  }

  if (!date) { toast('請選擇日期'); return; }

  const sale = {
    id: _editingSaleId || uid(),
    saleType, product, amount, date, notes, qty, batchby, samerank, participants,
    createdAt: _editingSaleId ? undefined : Date.now(),
  };
  if (!sale.createdAt) delete sale.createdAt;

  if (_editingSaleId) {
    dispatch({ type: 'SALE_UPDATE', payload: { id: _editingSaleId, patch: sale } });
    toast('已更新業績');
  } else {
    dispatch({ type: 'SALE_ADD', payload: sale });
    toast('已新增業績');
  }
  closeSaleModal();
  renderSalesPage();
}

export function deleteSale(id) {
  if (!id || !confirm('確定刪除此筆業績？')) return;
  dispatch({ type: 'SALE_DELETE', payload: id });
  renderSalesPage();
  toast('已刪除');
}

// ── Sale modal helpers ────────────────────────────────────────────────────────

export function onSaleTypeChange() { _onSaleTypeChange(); }
export function onSaleProductChange() { _onSaleProductChange(); }
export function onSaleAmountFocus() {
  const el = document.getElementById('sale-amount-display');
  if (el) el.value = _parseAmount() || '';
}
export function onSaleAmountBlur() {
  const el = document.getElementById('sale-amount-display');
  if (!el) return;
  const v = _parseAmount();
  el.value = v ? v.toLocaleString() : '';
  _updateIncomePreview();
}
export function onSaleAmountInput() { _updateIncomePreview(); }

function _onSaleTypeChange() {
  const t = document.querySelector('input[name="sale-type"]:checked')?.value;
  const prodGroup = document.getElementById('sale-product-group');
  if (prodGroup) prodGroup.style.display = t === 'transfer' ? 'none' : '';
  _onSaleProductChange();
}

function _onSaleProductChange() {
  const t = document.querySelector('input[name="sale-type"]:checked')?.value;
  if (t === 'transfer') { _updateIncomePreview(); return; }
  const p = document.getElementById('sale-product')?.value;
  const prod = PRODUCTS[p] || {};
  const badge = document.getElementById('sale-modal-product-badge');
  if (badge) badge.textContent = prod.label || '—';
  document.getElementById('sale-qty-group')    && (document.getElementById('sale-qty-group').style.display = p === 'consult' ? '' : 'none');
  document.getElementById('sale-batchby-group') && (document.getElementById('sale-batchby-group').style.display = ['asst_mgr_pkg','manager_pkg'].includes(p) ? '' : 'none');
  document.getElementById('sale-samerank-group') && (document.getElementById('sale-samerank-group').style.display = ['member','vip','student'].includes(p) ? '' : 'none');
  if (p !== 'consult' && prod.price) _syncSaleAmount(prod.price);
  _updateIncomePreview();
}

function _syncSaleAmount(val) {
  const el = document.getElementById('sale-amount-display');
  if (el) el.value = val ? val.toLocaleString() : '';
}

function _parseAmount() {
  const el = document.getElementById('sale-amount-display');
  return parseInt((el?.value || '').replace(/[^\d]/g, '')) || 0;
}

function _updateIncomePreview() {
  const t       = document.querySelector('input[name="sale-type"]:checked')?.value || 'new';
  const product = document.getElementById('sale-product')?.value || 'student';
  const batchby = document.querySelector('input[name="sale-batchby"]:checked')?.value || 'self';
  const samerank= document.querySelector('input[name="sale-samerank"]:checked')?.value || 'self';
  const amount  = _parseAmount();
  const myRate  = STORE.getMyRate();
  const income  = CALC.saleIncome({ saleType: t, product, amount, batchby, samerank }, myRate);
  const tax     = income * 0.1211;
  const net     = income - tax;
  const set = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
  set('sale-income-preview', `$${income.toLocaleString()}`);
  set('sale-tax-preview',    `$${Math.round(tax).toLocaleString()}`);
  set('sale-net-preview',    `$${Math.round(net).toLocaleString()}`);
}

function _esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
