/**
 * Genspark ↔ Claude Code Relay Server v0.1
 *
 * 零依賴 HTTP relay，提供協作協議 §4 所定義的端點。
 * 啟動：ts-node src/relay.ts
 * 預設監聽：http://localhost:9300
 *
 * 端點：
 *   POST   /events      — 寫入事件（Claude Code / Genspark / Ryan 均可用）
 *   GET    /events      — polling 取事件（?task_id= &since_turn= &sender=）
 *   GET    /interrupt   — 查詢 Ryan 是否有待處理 interrupt
 *   DELETE /interrupt   — 清除 interrupt（已處理後呼叫）
 *   GET    /transcript  — Ryan 可讀 transcript（?task_id= &format=text|json &last=N）
 *   GET    /status      — relay 健康狀態
 *   POST   /artifacts   — 上傳大型內容（log tail / diff）取得可引用 URL
 *   GET    /artifacts/* — 取得已上傳 artifact
 */

import http from 'http';
import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

// ─── 路徑設定 ────────────────────────────────────────────────────────────────

const PORT = 9300;
const BASE_DIR = path.join(__dirname, '../../relay');
const TRANSCRIPT_FILE = path.join(BASE_DIR, 'transcript.jsonl');
const ARTIFACTS_DIR = path.join(BASE_DIR, 'artifacts');
const INTERRUPT_FILE = path.join(BASE_DIR, 'pending-interrupt.json');

// ─── 型別 ─────────────────────────────────────────────────────────────────────

interface RelayEvent {
  protocol_version?: string;
  session_id?: string;
  turn_id?: string;
  timestamp: string;
  sender: 'claude_code' | 'genspark' | 'ryan';
  message_type: string;
  task_id?: string;
  visibility?: string;
  payload?: Record<string, unknown>;
}

interface InterruptPayload {
  action: 'approve' | 'pause' | 'stop' | 'revise' | 'clarify';
  instruction?: string;
  priority?: 'high' | 'normal' | 'low';
  ts: string;
}

// ─── 工具函式 ─────────────────────────────────────────────────────────────────

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => resolve(body));
    req.on('error', reject);
  });
}

function json(res: http.ServerResponse, status: number, data: unknown): void {
  const body = JSON.stringify(data, null, 2);
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
  });
  res.end(body);
}

function appendEvent(event: RelayEvent): void {
  fs.appendFileSync(TRANSCRIPT_FILE, JSON.stringify(event) + '\n');
}

function readTranscript(): RelayEvent[] {
  if (!fs.existsSync(TRANSCRIPT_FILE)) return [];
  return fs.readFileSync(TRANSCRIPT_FILE, 'utf8')
    .split('\n')
    .filter(Boolean)
    .map(line => {
      try { return JSON.parse(line) as RelayEvent; }
      catch { return null; }
    })
    .filter((e): e is RelayEvent => e !== null);
}

/** text 格式：Ryan 可讀的 transcript */
function formatAsText(events: RelayEvent[]): string {
  return events.map(e => {
    const ts = e.timestamp?.slice(11, 19) ?? '??:??:??';
    const interrupt = e.message_type === 'human.interrupt' ? '  ⚠️ INTERRUPT' : '';
    const lines: string[] = [`[${ts}] ${e.sender} → ${e.message_type}${interrupt}`];

    const p = e.payload ?? {};
    if (p.goal)        lines.push(`  Goal: ${p.goal}`);
    if (p.question)    lines.push(`  Question: ${p.question}`);
    if (p.decision)    lines.push(`  Decision: ${p.decision}`);
    if (p.next_actions && Array.isArray(p.next_actions)) {
      lines.push(`  Next: ${(p.next_actions as string[]).join(' → ')}`);
    }
    if (p.action)      lines.push(`  Action: ${p.action}`);
    if (p.instruction) lines.push(`  Instruction: ${p.instruction}`);
    if (p.summary)     lines.push(`  Summary: ${p.summary}`);
    if (p.status)      lines.push(`  Status: ${p.status}`);

    return lines.join('\n');
  }).join('\n\n');
}

// ─── 啟動前確保目錄存在 ───────────────────────────────────────────────────────

fs.mkdirSync(ARTIFACTS_DIR, { recursive: true });

// ─── HTTP Server ──────────────────────────────────────────────────────────────

const startTime = Date.now();

const server = http.createServer(async (req, res) => {
  const urlStr = req.url ?? '/';
  const url = new URL(urlStr, `http://localhost:${PORT}`);
  const method = req.method ?? 'GET';

  // CORS preflight
  if (method === 'OPTIONS') {
    res.writeHead(204, { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Methods': 'GET,POST,DELETE' });
    res.end();
    return;
  }

  try {
    // ── POST /events ─────────────────────────────────────────────────────────
    if (method === 'POST' && url.pathname === '/events') {
      const body = await readBody(req);
      const incoming = JSON.parse(body) as Partial<RelayEvent>;

      const event: RelayEvent = {
        protocol_version: incoming.protocol_version ?? '0.1',
        session_id: incoming.session_id,
        turn_id: incoming.turn_id ?? `turn_${Date.now()}`,
        timestamp: new Date().toISOString(),
        sender: incoming.sender ?? 'claude_code',
        message_type: incoming.message_type ?? 'state.update',
        task_id: incoming.task_id,
        visibility: incoming.visibility ?? 'shared',
        payload: incoming.payload,
      };

      appendEvent(event);

      // human.interrupt → 同時寫 pending-interrupt.json
      if (event.message_type === 'human.interrupt' && event.payload) {
        const interrupt: InterruptPayload = {
          action: (event.payload.action as InterruptPayload['action']) ?? 'clarify',
          instruction: event.payload.instruction as string | undefined,
          priority: (event.payload.priority as InterruptPayload['priority']) ?? 'normal',
          ts: event.timestamp,
        };
        fs.writeFileSync(INTERRUPT_FILE, JSON.stringify(interrupt, null, 2));
      }

      json(res, 200, { ok: true, turn_id: event.turn_id, ts: event.timestamp });
      return;
    }

    // ── GET /events ──────────────────────────────────────────────────────────
    if (method === 'GET' && url.pathname === '/events') {
      const taskId   = url.searchParams.get('task_id');
      const sinceTurn = url.searchParams.get('since_turn');
      const sender   = url.searchParams.get('sender');
      const lastN    = parseInt(url.searchParams.get('last') ?? '0', 10);

      let events = readTranscript();
      if (taskId)   events = events.filter(e => e.task_id === taskId);
      if (sender)   events = events.filter(e => e.sender === sender);
      if (sinceTurn) {
        const idx = events.findIndex(e => e.turn_id === sinceTurn);
        if (idx !== -1) events = events.slice(idx + 1);
      }
      if (lastN > 0) events = events.slice(-lastN);

      json(res, 200, { events, count: events.length });
      return;
    }

    // ── GET /interrupt ───────────────────────────────────────────────────────
    if (method === 'GET' && url.pathname === '/interrupt') {
      if (!fs.existsSync(INTERRUPT_FILE)) {
        json(res, 200, { pending: false });
        return;
      }
      const payload = JSON.parse(fs.readFileSync(INTERRUPT_FILE, 'utf8')) as InterruptPayload;
      json(res, 200, { pending: true, ...payload });
      return;
    }

    // ── DELETE /interrupt ────────────────────────────────────────────────────
    if (method === 'DELETE' && url.pathname === '/interrupt') {
      const existed = fs.existsSync(INTERRUPT_FILE);
      if (existed) fs.unlinkSync(INTERRUPT_FILE);
      json(res, 200, { ok: true, cleared: existed });
      return;
    }

    // ── GET /transcript ──────────────────────────────────────────────────────
    if (method === 'GET' && url.pathname === '/transcript') {
      const taskId = url.searchParams.get('task_id');
      const format = url.searchParams.get('format') ?? 'json';
      const lastN  = parseInt(url.searchParams.get('last') ?? '50', 10);

      let events = readTranscript();
      if (taskId) events = events.filter(e => e.task_id === taskId);
      if (lastN > 0) events = events.slice(-lastN);

      if (format === 'text') {
        res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
        res.end(formatAsText(events));
      } else {
        json(res, 200, { events, count: events.length });
      }
      return;
    }

    // ── GET /status ──────────────────────────────────────────────────────────
    if (method === 'GET' && url.pathname === '/status') {
      const events = readTranscript();
      const tasks = [...new Set(events.map(e => e.task_id).filter(Boolean))] as string[];
      const senders = { claude_code: 0, genspark: 0, ryan: 0 } as Record<string, number>;
      events.forEach(e => { if (e.sender) senders[e.sender] = (senders[e.sender] ?? 0) + 1; });

      json(res, 200, {
        relay: 'running',
        port: PORT,
        uptime_s: Math.floor((Date.now() - startTime) / 1000),
        transcript_events: events.length,
        events_by_sender: senders,
        active_tasks: tasks.slice(-5),
        pending_interrupt: fs.existsSync(INTERRUPT_FILE),
        transcript_file: TRANSCRIPT_FILE,
        artifacts_dir: ARTIFACTS_DIR,
      });
      return;
    }

    // ── POST /artifacts ──────────────────────────────────────────────────────
    if (method === 'POST' && url.pathname === '/artifacts') {
      const body = await readBody(req);
      const { label, content } = JSON.parse(body) as { label?: string; content: string };

      const id = crypto.randomBytes(8).toString('hex');
      const filename = `${id}.txt`;
      const filepath = path.join(ARTIFACTS_DIR, filename);
      fs.writeFileSync(filepath, content, 'utf8');

      const artifactUrl = `http://localhost:${PORT}/artifacts/${filename}`;
      json(res, 200, { ok: true, url: artifactUrl, label: label ?? filename, id });
      return;
    }

    // ── GET /artifacts/:filename ─────────────────────────────────────────────
    if (method === 'GET' && url.pathname.startsWith('/artifacts/')) {
      const filename = path.basename(url.pathname);
      const filepath = path.join(ARTIFACTS_DIR, filename);

      if (!fs.existsSync(filepath)) {
        json(res, 404, { error: 'artifact not found', filename });
        return;
      }

      const content = fs.readFileSync(filepath, 'utf8');
      res.writeHead(200, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end(content);
      return;
    }

    // ── 404 ──────────────────────────────────────────────────────────────────
    json(res, 404, { error: 'not found', path: url.pathname });

  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    json(res, 500, { error: 'internal server error', message });
  }
});

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[relay] listening on http://localhost:${PORT}`);
  console.log(`[relay] transcript  → ${TRANSCRIPT_FILE}`);
  console.log(`[relay] artifacts   → ${ARTIFACTS_DIR}`);
  console.log(`[relay] interrupt   → ${INTERRUPT_FILE}`);
});

process.on('SIGINT', () => {
  console.log('\n[relay] shutting down');
  server.close(() => process.exit(0));
});
