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
  const box = document.getElementById('chat-messages');
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

function buildRequestBody(provider, model, systemPrompt, messages) {
  if (provider === 'openai' || provider === 'openrouter' || provider === 'custom' || provider === 'grok') {
    return {
      model,
      messages: [{ role: 'system', content: systemPrompt }, ...messages],
      max_tokens: 2048,
      temperature: 0.7,
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
  const box = document.getElementById('chat-messages');
  const loading = document.createElement('div');
  loading.className = 'chat-msg assistant loading';
  loading.innerHTML = '<div class="chat-bubble assistant">⏳ 思考中…</div>';
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

    const url     = getEndpoint(provider, model, customEndpoint);
    const headers = getHeaders(provider, apiKey);
    const body    = buildRequestBody(provider, model, systemPrompt, messages);

    const res  = await fetch(url, { method: 'POST', headers, body: JSON.stringify(body) });
    if (!res.ok) {
      const errText = await res.text().catch(() => res.statusText);
      throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
    }
    const data = await res.json();

    // Handle tool calls (Claude only)
    const toolUses = extractToolUses(provider, data);
    let assistantContent = extractContent(provider, data);

    if (toolUses.length) {
      const toolResults = [];
      for (const tu of toolUses) {
        const result = await executeToolCall(tu.name, tu.input || {});
        toolResults.push({ type: 'tool_result', tool_use_id: tu.id, content: JSON.stringify(result) });
        if (result.message) assistantContent += (assistantContent ? '\n\n' : '') + `✅ ${result.message}`;
      }
      // If tool calls produced a follow-up response, we could do a second round-trip here.
      // For now, append the tool action descriptions inline.
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
  if (ok) { toast('已刪除記憶'); renderMemoryList(); }
  else    toast('刪除失敗');
}
