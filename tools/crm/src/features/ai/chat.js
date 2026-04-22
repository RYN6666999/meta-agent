/**
 * features/ai/chat.js
 * AI 對話：sendChat, renderChat, clearChat, 記憶萃取 UI
 * 依賴：core/state.js, core/toast.js,
 *       features/ai/providers.js, features/ai/personas.js, features/ai/tools.js
 */

import { getChatHistory, dispatch } from '../../core/state.js';
import { toast } from '../../core/toast.js';
import { getAiSettings } from './providers.js';
import { getCurrentPersona, buildSystemPrompt, memoryService } from './personas.js';
import { CRM_TOOLS, executeToolCall } from './tools.js';

// ── Markdown → HTML (minimal) ─────────────────────────────────────────────────

function mdToHtml(text) {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,     '<em>$1</em>')
    .replace(/`([^`]+)`/g,     '<code>$1</code>')
    .replace(/^#{1,3} (.+)$/gm, '<strong>$1</strong>')
    .replace(/^[-•] (.+)$/gm,  '<li>$1</li>')
    .replace(/<\/li>\n<li>/g,  '</li><li>')
    .replace(/(<li>[\s\S]+?<\/li>)/g, '<ul>$1</ul>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/👉 (https?:\/\/\S+)/g, '👉 <a href="$1" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/\n/g, '<br>');
}

// ── Render chat history ───────────────────────────────────────────────────────

export function renderChat() {
  const box = document.getElementById('chat-area');
  if (!box) return;
  const history = getChatHistory();
  if (!history.length) {
    box.innerHTML = '<div class="chat-empty">選擇上方 Persona，輸入問題開始對話 👆</div>';
    return;
  }
  box.innerHTML = history.map(m => {
    if (m.role === 'user') {
      return `<div class="chat-msg user"><div class="chat-bubble user">${mdToHtml(m.content)}</div></div>`;
    }
    if (m.role === 'assistant') {
      return `<div class="chat-msg assistant">
        <div class="chat-bubble assistant">${mdToHtml(m.content)}</div>
        <div class="chat-actions">
          <button class="chat-action-btn" onclick="window.__crmExtractMemories?.(${JSON.stringify(m.content).replace(/'/g, '&#39;')})">💾 存入記憶</button>
        </div>
      </div>`;
    }
    return '';
  }).join('');
  box.scrollTop = box.scrollHeight;
}

// ── Clear chat ────────────────────────────────────────────────────────────────

export function clearChat() {
  dispatch({ type: 'CHAT_CLEAR' });
  renderChat();
}

// ── Token / cost estimate (rough) ────────────────────────────────────────────

function roughTokens(text) { return Math.ceil((text || '').length / 3.5); }

// ── Build API request body ────────────────────────────────────────────────────

function supportsStreaming(provider) {
  return provider === 'openai' || provider === 'openrouter' || provider === 'grok' || provider === 'custom';
}

function buildRequestBody(provider, model, systemPrompt, messages, stream = false) {
  if (provider === 'openai' || provider === 'openrouter' || provider === 'custom' || provider === 'grok') {
    return {
      model,
      messages: [{ role: 'system', content: systemPrompt }, ...messages],
      max_tokens: 2048,
      temperature: 0.7,
      ...(stream ? { stream: true } : {}),
    };
  }
  if (provider === 'gemini') {
    return {
      system_instruction: { parts: [{ text: systemPrompt }] },
      contents: messages.map(m => ({ role: m.role === 'assistant' ? 'model' : 'user', parts: [{ text: m.content }] })),
      generationConfig: { maxOutputTokens: 2048, temperature: 0.7 },
    };
  }
  // claude (default)
  return {
    model,
    system: systemPrompt,
    messages,
    max_tokens: 2048,
    tools: CRM_TOOLS,
  };
}

function getEndpoint(provider, model, customEndpoint) {
  if (provider === 'openai') return 'https://api.openai.com/v1/chat/completions';
  if (provider === 'grok')   return 'https://api.x.ai/v1/chat/completions';
  if (provider === 'gemini') return `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
  if (provider === 'openrouter') return customEndpoint || 'https://openrouter.ai/api/v1/chat/completions';
  if (provider === 'custom')     return customEndpoint || '';
  // claude
  return '/api/claude';
}

function getHeaders(provider, apiKey) {
  const h = { 'Content-Type': 'application/json' };
  if (provider === 'claude') return h;   // backend proxy handles auth
  if (provider === 'gemini') return { ...h, 'x-goog-api-key': apiKey };
  if (provider === 'openrouter') return { ...h, Authorization: `Bearer ${apiKey}`, 'HTTP-Referer': 'https://fdd-crm.pages.dev', 'X-Title': 'FDD CRM' };
  return { ...h, Authorization: `Bearer ${apiKey}` };
}

function extractContent(provider, data) {
  if (provider === 'gemini') return data.candidates?.[0]?.content?.parts?.[0]?.text || '';
  if (provider === 'claude') {
    const block = (data.content || []).find(b => b.type === 'text');
    return block?.text || '';
  }
  return data.choices?.[0]?.message?.content || '';
}

function extractToolUses(provider, data) {
  if (provider !== 'claude') return [];
  return (data.content || []).filter(b => b.type === 'tool_use');
}

// ── sendChat ──────────────────────────────────────────────────────────────────

export async function sendChat() {
  const inp = document.getElementById('chat-input');
  if (!inp) return;
  const userMsg = inp.value.trim();
  if (!userMsg) return;

  inp.value = '';
  inp.style.height = 'auto';

  const { provider, model, apiKey, endpoint: customEndpoint } = getAiSettings();
  if (!apiKey && provider !== 'claude') { toast('請先設定 API Key'); return; }

  // Append user message to state
  dispatch({ type: 'CHAT_PUSH', payload: { role: 'user', content: userMsg } });
  renderChat();

  // Show loading
  const box = document.getElementById('chat-area');
  const loading = document.createElement('div');
  loading.className = 'chat-msg assistant loading';
  loading.innerHTML = '<div class="chat-bubble assistant chat-thinking"><span></span><span></span><span></span></div>';
  box?.appendChild(loading);
  box && (box.scrollTop = box.scrollHeight);

  const sendBtn = document.getElementById('chat-send-btn');
  if (sendBtn) sendBtn.disabled = true;

  try {
    const personaKey  = getCurrentPersona();
    const { memories: _m, promptSnippet } = await memoryService.retrieve(userMsg, { persona: personaKey });
    const systemPrompt = await buildSystemPrompt(personaKey, promptSnippet);

    // Build messages array (trim to last 20 to stay under context)
    const history = getChatHistory().slice(-20);
    const messages = history.map(m => ({ role: m.role, content: m.content }));

    const url      = getEndpoint(provider, model, customEndpoint);
    const headers  = getHeaders(provider, apiKey);
    const useStream = supportsStreaming(provider);
    const body     = buildRequestBody(provider, model, systemPrompt, messages, useStream);

    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok) {
      const errText = await res.text().catch(() => res.statusText);
      throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
    }

    let assistantContent = '';

    if (useStream && res.body) {
      // ── Streaming path ──────────────────────────────────────────────────────
      loading.remove();
      // Create live bubble
      const liveBubble = document.createElement('div');
      liveBubble.className = 'chat-msg assistant';
      liveBubble.innerHTML = '<div class="chat-bubble assistant" id="chat-stream-bubble"></div>';
      box?.appendChild(liveBubble);

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      const bubbleEl = () => document.getElementById('chat-stream-bubble');
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop(); // keep incomplete line
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (raw === '[DONE]') break;
          try {
            const chunk = JSON.parse(raw);
            const delta = chunk.choices?.[0]?.delta?.content || '';
            if (delta) {
              assistantContent += delta;
              const el = bubbleEl();
              if (el) { el.innerHTML = mdToHtml(assistantContent); box && (box.scrollTop = box.scrollHeight); }
            }
          } catch { /* ignore malformed chunk */ }
        }
      }
      liveBubble.id = '';
      const el = bubbleEl();
      if (el) el.removeAttribute('id');
    } else {
      // ── Non-streaming path (Claude / Gemini) ───────────────────────────────
      const data     = await res.json();
      const toolUses = extractToolUses(provider, data);
      assistantContent = extractContent(provider, data);
      for (const tu of toolUses) {
        const result = await executeToolCall(tu.name, tu.input || {});
        if (result.message) assistantContent += (assistantContent ? '\n\n' : '') + `✅ ${result.message}`;
      }
    }

    if (!assistantContent) assistantContent = '（無回應）';
    dispatch({ type: 'CHAT_PUSH', payload: { role: 'assistant', content: assistantContent } });

  } catch (e) {
    const errMsg = `❌ 錯誤：${e.message}`;
    dispatch({ type: 'CHAT_PUSH', payload: { role: 'assistant', content: errMsg } });
    toast(e.message.slice(0, 80));
  } finally {
    loading.remove();
    if (sendBtn) sendBtn.disabled = false;
    renderChat();
  }
}

// ── Extract memories from AI response ────────────────────────────────────────

export async function extractAndSaveMemories(content) {
  if (!content) return;
  const { provider, model, apiKey } = getAiSettings();
  if (!apiKey && provider !== 'claude') { toast('需要 API Key 才能萃取記憶'); return; }

  toast('正在萃取記憶…');
  const extractPrompt = `從以下 AI 回應中，找出值得長期記住的客戶資訊或業務洞察（最多3條）。
每條格式：{"subject":"對象","type":"insight|preference|fact","content":"內容"}
只輸出 JSON array，無其他文字。

回應內容：
${content.slice(0, 2000)}`;

  try {
    const url     = getEndpoint(provider, model, '');
    const headers = getHeaders(provider, apiKey);
    const body    = provider === 'claude'
      ? { model, system: '你是記憶萃取助理', messages: [{ role: 'user', content: extractPrompt }], max_tokens: 512 }
      : { model, messages: [{ role: 'system', content: '你是記憶萃取助理' }, { role: 'user', content: extractPrompt }], max_tokens: 512 };

    const res  = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    const data = await res.json();
    const raw  = extractContent(provider, data).trim();
    const arr  = JSON.parse(raw.replace(/^```json\n?/, '').replace(/\n?```$/, ''));
    if (!Array.isArray(arr)) throw new Error('格式錯誤');

    let saved = 0;
    for (const m of arr.slice(0, 3)) {
      if (m.subject && m.content) {
        await memoryService.create({ subject: m.subject, type: m.type || 'insight', content: m.content });
        saved++;
      }
    }
    toast(`已儲存 ${saved} 條記憶`);
  } catch (e) {
    toast('記憶萃取失敗：' + e.message.slice(0, 60));
  }
}

// ── Memory UI ─────────────────────────────────────────────────────────────────

export async function renderMemoryList(subjectFilter = '') {
  const box = document.getElementById('memory-list');
  if (!box) return;
  box.innerHTML = '<div style="color:var(--text-muted);font-size:12px">載入中…</div>';
  const memories = await memoryService.list(subjectFilter ? { subject: subjectFilter } : {});
  if (!memories.length) { box.innerHTML = '<div style="color:var(--text-muted);font-size:12px">尚無記憶</div>'; return; }
  box.innerHTML = memories.map(m => `
    <div class="memory-item" data-id="${m.id}">
      <div class="memory-header">
        <span class="memory-subject">${m.subject || '—'}</span>
        <span class="memory-type">${m.type || ''}</span>
        <button class="memory-del-btn" onclick="window.__crmDeleteMemory?.('${m.id}')">✕</button>
      </div>
      <div class="memory-content">${m.content || ''}</div>
    </div>`).join('');
}

export async function deleteMemory(id) {
  if (!id) return;
  const ok = await memoryService.delete(id);
  if (ok) { toast('已刪除記憶'); renderMemPanel(); }
  else    toast('刪除失敗');
}

// ── Memory panel (HTML-facing) ────────────────────────────────────────────────

let _memPanelOpen = false;
let _memType      = '';

export function toggleMemPanel() {
  _memPanelOpen = !_memPanelOpen;
  const panel = document.getElementById('mem-panel');
  const btn   = document.getElementById('mem-toggle-btn');
  if (panel) panel.style.display = _memPanelOpen ? '' : 'none';
  if (btn)   btn.classList.toggle('active', _memPanelOpen);
  if (_memPanelOpen) renderMemPanel();
}

export function switchMemTab(type, el) {
  _memType = type;
  document.querySelectorAll('.mem-tab').forEach(b => b.classList.remove('active'));
  if (el) el.classList.add('active');
  renderMemPanel();
}

export async function renderMemPanel() {
  const box = document.getElementById('mem-list');
  if (!box) return;
  box.innerHTML = '<div class="mem-empty">載入中…</div>';
  const q = document.getElementById('mem-search')?.value.trim() || '';
  const params = {};
  if (_memType) params.type = _memType;
  if (q)        params.subject = q;
  const memories = await memoryService.list(params);
  if (!memories.length) {
    box.innerHTML = '<div class="mem-empty">尚無記憶</div>';
    return;
  }
  box.innerHTML = memories.map(m => `
    <div class="mem-item">
      <div class="mem-item-header">
        <span class="mem-subject">${m.subject || '—'}</span>
        <span class="mem-type-badge">${m.type || ''}</span>
        <button class="mem-del" onclick="window.__crmDeleteMemory?.('${m.id}')">✕</button>
      </div>
      <div class="mem-content">${m.content || ''}</div>
    </div>`).join('');
}

export async function addManualMemory() {
  const inp = document.getElementById('mem-add-input');
  const txt = inp?.value.trim();
  if (!txt) return;
  const ok = await memoryService.create({ subject: '手動', type: 'fact', content: txt });
  if (ok) { toast('已新增記憶'); if (inp) inp.value = ''; renderMemPanel(); }
  else toast('新增失敗');
}

// ── Daily briefing ────────────────────────────────────────────────────────────

export async function generateDailyBriefing() {
  const inp = document.getElementById('chat-input');
  if (inp) {
    inp.value = '幫我生成今日工作簡報：列出今天需要跟進的人脈、近期活動、以及業績進度摘要。';
    inp.dispatchEvent(new Event('input'));
  }
  await sendChat();
}

// ── AI Diagnostic ─────────────────────────────────────────────────────────────

export function toggleAiDiag() {
  const panel = document.getElementById('ai-diag-panel');
  if (!panel) return;
  const visible = panel.style.display !== 'none';
  panel.style.display = visible ? 'none' : '';
  if (!visible) _renderDiagConfig();
}

function _renderDiagConfig() {
  const { provider, model, apiKey, endpoint } = getAiSettings();
  const keyMask = apiKey
    ? apiKey.slice(0, 8) + '…' + apiKey.slice(-4)
    : '⚠ 未設定';
  const ep = endpoint || (provider === 'openrouter' ? 'https://openrouter.ai/api/v1/chat/completions' : '（預設）');
  document.getElementById('ai-diag-config').innerHTML = `
    <div class="diag-row"><span class="diag-label">Provider</span><span class="diag-val">${provider}</span></div>
    <div class="diag-row"><span class="diag-label">Model</span><span class="diag-val">${model || '⚠ 未選擇'}</span></div>
    <div class="diag-row"><span class="diag-label">API Key</span><span class="diag-val">${keyMask}</span></div>
    <div class="diag-row"><span class="diag-label">Endpoint</span><span class="diag-val diag-ep">${ep}</span></div>
  `;
  document.getElementById('ai-diag-log').innerHTML = '';
}

function _diagLog(html) {
  const box = document.getElementById('ai-diag-log');
  if (box) box.innerHTML += html + '\n';
}

export async function runAiDiagnostic() {
  const btn = document.getElementById('ai-diag-run-btn');
  if (btn) { btn.disabled = true; btn.textContent = '⏳ 測試中…'; }
  const box = document.getElementById('ai-diag-log');
  if (box) box.innerHTML = '';

  const { provider, model, apiKey, endpoint: customEndpoint } = getAiSettings();

  // Step 1: key
  if (!apiKey && provider !== 'claude') {
    _diagLog('❌ <b>API Key 未設定</b> — 請到設定填入 Key');
    if (btn) { btn.disabled = false; btn.textContent = '🚀 測試連線'; }
    return;
  }
  _diagLog('✅ API Key 已填入');

  // Step 2: model
  if (!model) {
    _diagLog('❌ <b>未選擇模型</b> — 請到設定選擇模型（OpenRouter 需先點「載入模型」）');
    if (btn) { btn.disabled = false; btn.textContent = '🚀 測試連線'; }
    return;
  }
  _diagLog(`✅ 模型：${model}`);

  // Step 3: send minimal request
  const url     = getEndpoint(provider, model, customEndpoint);
  const headers = getHeaders(provider, apiKey);
  const body    = buildRequestBody(provider, model, '你是測試助理，只需回覆「OK」。', [{ role: 'user', content: 'hi' }]);
  // override max_tokens for speed
  if (body.max_tokens) body.max_tokens = 30;
  if (body.generationConfig) body.generationConfig.maxOutputTokens = 30;

  _diagLog(`⏳ 呼叫 <code>${url.replace('https://', '')}</code>…`);
  const t0 = Date.now();
  try {
    const res = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    if (!res.ok) {
      const errText = await res.text().catch(() => res.statusText);
      _diagLog(`❌ HTTP ${res.status} (${elapsed}s)<br><code>${errText.slice(0, 300)}</code>`);
    } else {
      const data = await res.json();
      const reply = extractContent(provider, data) || '（空回應）';
      _diagLog(`✅ <b>連線成功</b>（${elapsed}s）<br>回應：「${reply.slice(0, 80)}」`);
    }
  } catch (e) {
    const elapsed = ((Date.now() - t0) / 1000).toFixed(1);
    _diagLog(`❌ 網路錯誤（${elapsed}s）：${e.message}`);
  }

  if (btn) { btn.disabled = false; btn.textContent = '🚀 測試連線'; }
}

// ── Today reminders ───────────────────────────────────────────────────────────

export function showTodayReminders() {
  // Dynamic import to avoid circular dep with state
  import('../../core/state.js').then(({ getNodes, getStudentsData }) => {
    const today = new Date().toISOString().slice(0, 10);
    const nodes = getNodes().filter(n => n.parentId && n.info?.nextFollowUp === today);
    const students = getStudentsData().filter(s => s.nextFollowUp === today);
    const count = nodes.length + students.length;
    if (!count) { toast('今日沒有待跟進聯繫人'); return; }
    const names = [
      ...nodes.map(n => n.name),
      ...students.map(s => s.name),
    ].slice(0, 10).join('、');
    alert(`📅 今日待跟進（${count} 人）：\n${names}`);
  });
}
