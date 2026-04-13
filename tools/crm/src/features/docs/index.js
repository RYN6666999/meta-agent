/**
 * features/docs/index.js
 * 知識庫文件管理：CRUD + 搜尋 + 渲染
 * 依賴：core/state.js, core/toast.js, core/uid.js
 */

import { getDocsData, dispatch } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { uid } from '../../core/uid.js';

const DOC_TYPES = ['file', 'link', 'form', 'poster'];
const TYPE_LABELS = { file: '📄 文件', link: '🔗 連結', form: '📋 表單', poster: '🖼 海報' };

let _editingDocId = null;
let _searchQuery  = '';

function escHtml(s) {
  if (!s && s !== 0) return '';
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// ── Render docs list ──────────────────────────────────────────────────────────

export function renderDocsPage() {
  const docs = getDocsData();
  const q    = _searchQuery.toLowerCase();
  const filtered = q
    ? docs.filter(d =>
        (d.name || '').toLowerCase().includes(q) ||
        (d.description || '').toLowerCase().includes(q) ||
        (d.tags || []).some(t => t.toLowerCase().includes(q))
      )
    : docs;

  const el = document.getElementById('docs-list');
  if (!el) return;

  if (!filtered.length) {
    el.innerHTML = `<div class="empty-state">${q ? '沒有符合的文件' : '尚無文件，點「新增」開始建立'}</div>`;
    return;
  }

  el.innerHTML = filtered.map(d => `
    <div class="doc-card" onclick="window.__crmOpenDocModal?.('${d.id}')">
      <div class="doc-header">
        <span class="doc-type-badge">${TYPE_LABELS[d.type] || '📄'}</span>
        <span class="doc-name">${escHtml(d.name)}</span>
        <button class="btn btn-sm btn-ghost" onclick="event.stopPropagation();window.__crmDeleteDoc?.('${d.id}')">🗑</button>
      </div>
      ${d.description ? `<div class="doc-desc">${escHtml(d.description)}</div>` : ''}
      ${d.url ? `<a class="doc-link" href="${escHtml(d.url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">${escHtml(d.url).slice(0, 60)}${d.url.length > 60 ? '…' : ''}</a>` : ''}
      ${(d.tags || []).length ? `<div class="doc-tags">${d.tags.map(t => `<span class="tag">${escHtml(t)}</span>`).join('')}</div>` : ''}
    </div>`).join('');
}

export function setDocsSearch(q) {
  _searchQuery = q || '';
  renderDocsPage();
}

// ── Doc modal ─────────────────────────────────────────────────────────────────

export function openDocModal(id) {
  _editingDocId = id || null;
  const docs = getDocsData();
  const d = id ? docs.find(x => x.id === id) : null;

  const typeOpts = DOC_TYPES.map(t => `<option value="${t}"${(d?.type || 'link') === t ? ' selected' : ''}>${TYPE_LABELS[t]}</option>`).join('');

  document.getElementById('doc-modal-title').textContent = d ? '編輯文件' : '新增文件';
  document.getElementById('doc-modal-body').innerHTML = `
    <div class="field-group">
      <div class="field-label">類型</div>
      <select class="field-input" id="doc-type">${typeOpts}</select>
    </div>
    <div class="field-group">
      <div class="field-label">名稱</div>
      <input class="field-input" id="doc-name" value="${escHtml(d?.name || '')}" placeholder="文件名稱">
    </div>
    <div class="field-group">
      <div class="field-label">連結 / URL</div>
      <input class="field-input" id="doc-url" value="${escHtml(d?.url || '')}" placeholder="https://…">
    </div>
    <div class="field-group">
      <div class="field-label">說明</div>
      <textarea class="field-input field-textarea" id="doc-description" placeholder="簡短說明">${escHtml(d?.description || '')}</textarea>
    </div>
    <div class="field-group">
      <div class="field-label">標籤（逗號分隔）</div>
      <input class="field-input" id="doc-tags" value="${escHtml((d?.tags || []).join(', '))}" placeholder="話術, 表單, 房貸">
    </div>
    ${d ? `<div style="margin-top:8px"><button class="btn btn-danger btn-sm" onclick="window.__crmDeleteDoc?.('${d.id}');window.__crmCloseDocModal?.()">🗑 刪除</button></div>` : ''}`;
  document.getElementById('doc-modal')?.classList.add('open');
}

export function closeDocModal() {
  document.getElementById('doc-modal')?.classList.remove('open');
  _editingDocId = null;
}

export function saveDoc() {
  const name = document.getElementById('doc-name')?.value.trim();
  if (!name) { toast('請輸入名稱'); return; }
  const tagsRaw = document.getElementById('doc-tags')?.value || '';
  const tags = tagsRaw.split(',').map(t => t.trim()).filter(Boolean);
  const doc = {
    id:          _editingDocId || uid(),
    type:        document.getElementById('doc-type')?.value        || 'link',
    name,
    url:         document.getElementById('doc-url')?.value.trim()         || '',
    description: document.getElementById('doc-description')?.value.trim() || '',
    tags,
    updatedAt:   new Date().toISOString(),
  };
  if (_editingDocId) {
    dispatch({ type: 'DOC_UPDATE', payload: { id: _editingDocId, patch: doc } });
    toast('文件已更新');
  } else {
    dispatch({ type: 'DOC_ADD', payload: doc });
    toast('文件已新增');
  }
  closeDocModal();
  renderDocsPage();
}

export function deleteDoc(id) {
  if (!id || !confirm('確定刪除此文件？')) return;
  dispatch({ type: 'DOC_DELETE', payload: id });
  renderDocsPage();
  toast('已刪除');
}
