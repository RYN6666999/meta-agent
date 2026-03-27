/**
 * run-job.ts — Job Runner 進入點
 *
 * 使用方式：
 *   npm run run-job -- jobs/incoming/job-001.json
 *
 * Job 生命週期：
 *   jobs/incoming/<id>.json
 *     → jobs/running/<id>.json        （執行中）
 *     → jobs/done/<id>.json           （成功，job 定義）
 *     → jobs/done/<id>.result.json    （成功，執行結果）
 *     → jobs/failed/<id>.json         （失敗，job 定義）
 *     → jobs/failed/<id>.result.json  （失敗，執行結果含錯誤）
 *
 * Exit codes：
 *   0 = job 完成（done）
 *   1 = 參數錯誤（缺少檔案路徑 / 找不到檔案）
 *   2 = job 格式錯誤（schema 驗證失敗 / type-kind 不一致）
 *   3 = 執行失敗（failed）
 *   4 = AUTH_EXPIRED
 */

import * as fs   from "fs";
import * as path from "path";
import { WorkerSession }  from "./playwright-worker";
import { runSshCommand }  from "./ssh-worker";
import { loadConfig }     from "./config";

// ── P5.1 Runner structured log ────────────────────────────────────────
//
// 每次執行寫入 logs/runner.log（JSON Lines 格式）。
// 只用 fs.appendFileSync，不引入任何 logging framework。

const RUNNER_LOG_DIR  = path.resolve(__dirname, "../../logs");
const RUNNER_LOG_FILE = path.join(RUNNER_LOG_DIR, "runner.log");

interface LogEntry {
  ts:       string;
  level:    "INFO" | "WARN" | "ERROR";
  job_id?:  string;
  step?:    number;
  kind?:    string;
  status?:  string;
  msg:      string;
}

function rlog(entry: Omit<LogEntry, "ts">): void {
  const line = JSON.stringify({ ts: new Date().toISOString(), ...entry });
  try {
    fs.mkdirSync(RUNNER_LOG_DIR, { recursive: true });
    fs.appendFileSync(RUNNER_LOG_FILE, line + "\n", "utf-8");
  } catch {
    // log 寫入失敗不應中斷主流程
  }
}

// ── AUTH_EXPIRED 語義 ─────────────────────────────────────────────────
//
// 使用自定義 Error class，讓 main() 以 instanceof 判斷，
// 避免依賴字串前綴（"AUTH_EXPIRED:..."）這種脆弱的判別方式。

export class AuthExpiredError extends Error {
  readonly site: string;
  constructor(site: string) {
    super(`AUTH_EXPIRED: site="${site}"，請重新執行 SITE=${site} npm run refresh-auth`);
    this.name = "AuthExpiredError";
    this.site = site;
  }
}

// ── 型別定義 ──────────────────────────────────────────────────────────

export type JobType = "web" | "ssh" | "hybrid";

export interface WebStep {
  kind:      "web";
  site:      string;   // 對應 auth/sites/<site>/auth-state.json
  action:    string;   // open_page | click | fill | get_text | wait_for
  url?:      string;
  selector?: string;
  value?:    string;
}

export interface SshStep {
  kind:    "ssh";
  command: string;
}

export type Step = WebStep | SshStep;

export interface Job {
  job_id: string;
  type:   JobType;
  steps:  Step[];
  // id?: 唯一保留的過渡欄位。
  //      若 JSON 內只有舊欄位 "id" 而無 "job_id"，入口會將 id 複製到 job_id。
  //      確認所有 job 檔案都已改用 "job_id" 後可移除此欄位與對應邏輯。
  id?: string;
}

export interface StepResult {
  kind:    "web" | "ssh";
  status:  "ok" | "error" | "AUTH_EXPIRED";
  output?: unknown;
  error?:  string;
}

export interface JobResult {
  job_id:      string;
  status:      "done" | "failed" | "auth_expired";
  started_at:  string;
  finished_at: string;
  steps:       StepResult[];
  error?:      string;
}

// ── 目錄設定 ──────────────────────────────────────────────────────────

const JOBS_ROOT = path.resolve(__dirname, "../../jobs");
const DIR = {
  incoming: path.join(JOBS_ROOT, "incoming"),
  running:  path.join(JOBS_ROOT, "running"),
  done:     path.join(JOBS_ROOT, "done"),
  failed:   path.join(JOBS_ROOT, "failed"),
};

// ── Schema 驗證 ───────────────────────────────────────────────────────

const VALID_JOB_TYPES  = new Set(["web", "ssh", "hybrid"]);
const VALID_STEP_KINDS = new Set(["web", "ssh"]);
const WEB_ACTIONS_NEED_SELECTOR = new Set(["click", "get_text", "wait_for"]);

/** job JSON raw object → 錯誤訊息陣列（空陣列 = 合法） */
function validateJobSchema(raw: Record<string, unknown>): string[] {
  const errors: string[] = [];

  // job_id（允許舊欄位 id 過渡）
  const jobId = raw.job_id ?? raw.id;
  if (typeof jobId !== "string" || jobId.trim() === "") {
    errors.push('job_id: 必須是非空字串');
  }

  // type
  if (!VALID_JOB_TYPES.has(raw.type as string)) {
    errors.push(`type: 必須是 "web" | "ssh" | "hybrid"，收到 ${JSON.stringify(raw.type)}`);
  }

  // steps
  if (!Array.isArray(raw.steps) || raw.steps.length === 0) {
    errors.push("steps: 必須是非空陣列");
    return errors; // 無 steps 無法繼續驗證
  }

  (raw.steps as unknown[]).forEach((step, i) => {
    const s   = step as Record<string, unknown>;
    const loc = `steps[${i}]`;

    if (!VALID_STEP_KINDS.has(s.kind as string)) {
      errors.push(`${loc}.kind: 必須是 "web" | "ssh"，收到 ${JSON.stringify(s.kind)}`);
      return;
    }

    if (s.kind === "web") {
      if (typeof s.site !== "string" || (s.site as string).trim() === "") {
        errors.push(`${loc}.site: 必須是非空字串`);
      }
      if (typeof s.action !== "string" || (s.action as string).trim() === "") {
        errors.push(`${loc}.action: 必須是非空字串`);
      } else {
        const action = s.action as string;
        if (action === "open_page" && !s.url) {
          errors.push(`${loc}.url: action="open_page" 時必須提供 url`);
        }
        if (WEB_ACTIONS_NEED_SELECTOR.has(action) && !s.selector) {
          errors.push(`${loc}.selector: action="${action}" 時必須提供 selector`);
        }
        if (action === "fill") {
          if (!s.selector) errors.push(`${loc}.selector: action="fill" 時必須提供 selector`);
          if (!s.value)    errors.push(`${loc}.value: action="fill" 時必須提供 value`);
        }
      }
    }

    if (s.kind === "ssh") {
      if (typeof s.command !== "string" || (s.command as string).trim() === "") {
        errors.push(`${loc}.command: 必須是非空字串`);
      }
    }
  });

  return errors;
}

/** job.type 與 steps.kind 一致性檢查 */
function validateTypeKindConsistency(job: Job): string[] {
  if (job.type === "hybrid") return []; // hybrid 允許混合

  const errors: string[] = [];
  job.steps.forEach((step, i) => {
    if (step.kind !== job.type) {
      errors.push(
        `steps[${i}].kind="${step.kind}" 與 job.type="${job.type}" 不一致` +
        `（type="${job.type}" 的 job，所有 steps 必須是 kind="${job.type}"）`
      );
    }
  });
  return errors;
}

// ── 主程式 ────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const jobFile = process.argv[2];

  if (!jobFile) {
    console.error("[run-job] ERROR: 請提供 job 檔案路徑");
    console.error("  用法: npm run run-job -- <job-file.json>");
    process.exit(1);
  }

  const jobPath = path.resolve(jobFile);
  if (!fs.existsSync(jobPath)) {
    console.error(`[run-job] ERROR: 找不到 job 檔案: ${jobPath}`);
    process.exit(1);
  }

  // 解析 JSON
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(fs.readFileSync(jobPath, "utf-8")) as Record<string, unknown>;
  } catch {
    console.error("[run-job] ERROR: job 檔案不是合法 JSON");
    process.exit(2);
  }

  // Schema 驗證（入口攔截，不讓格式錯誤的 job 進入執行）
  const schemaErrors = validateJobSchema(raw);
  if (schemaErrors.length > 0) {
    console.error("[run-job] ERROR: job schema 驗證失敗");
    schemaErrors.forEach((e) => console.error(`  • ${e}`));
    process.exit(2);
  }

  // id → job_id 過渡（見 Job 介面說明）
  if (!raw.job_id && raw.id) raw.job_id = raw.id;

  const job = raw as unknown as Job;

  // type / kind 一致性檢查
  const consistencyErrors = validateTypeKindConsistency(job);
  if (consistencyErrors.length > 0) {
    console.error("[run-job] ERROR: job.type 與 steps.kind 不一致");
    consistencyErrors.forEach((e) => console.error(`  • ${e}`));
    process.exit(2);
  }

  const jobId    = job.job_id;
  const filename = path.basename(jobPath);

  Object.values(DIR).forEach((d) => fs.mkdirSync(d, { recursive: true }));

  // incoming → running
  const runningPath = path.join(DIR.running, filename);
  fs.copyFileSync(jobPath, runningPath);
  if (jobPath.startsWith(DIR.incoming)) fs.unlinkSync(jobPath);

  console.log(`[run-job] 開始執行: ${jobId} (type=${job.type}, steps=${job.steps.length})`);
  rlog({ level: "INFO", job_id: jobId, msg: `job start type=${job.type} steps=${job.steps.length}` });

  const startedAt  = new Date().toISOString();
  const stepResults: StepResult[] = [];
  const sessions   = new Map<string, WorkerSession>();
  const timeoutMs  = loadConfig().runner.jobTimeoutMs;

  let jobStatus: JobResult["status"] = "done";
  let jobError: string | undefined;
  let authExpiredSite: string | undefined;

  let timeoutHandle: ReturnType<typeof setTimeout> | undefined;
  const timeoutPromise = new Promise<never>((_, reject) => {
    timeoutHandle = setTimeout(
      () => reject(new Error(`Job timeout after ${timeoutMs}ms`)),
      timeoutMs
    );
  });

  try {
    await Promise.race([
      executeSteps(job.steps, sessions, stepResults),
      timeoutPromise,
    ]);
  } catch (err) {
    if (err instanceof AuthExpiredError) {
      jobStatus       = "auth_expired";
      authExpiredSite = err.site;
    } else {
      jobStatus = "failed";
    }
    jobError = (err as Error).message;
  } finally {
    clearTimeout(timeoutHandle);
    for (const [, session] of sessions) {
      await session.close().catch(() => {});
    }
  }

  const finishedAt = new Date().toISOString();

  const result: JobResult = {
    job_id:      jobId,
    status:      jobStatus,
    started_at:  startedAt,
    finished_at: finishedAt,
    steps:       stepResults,
    ...(jobError ? { error: jobError } : {}),
  };

  // job 定義與 result 分開寫入（<id>.json + <id>.result.json）
  const targetDir      = jobStatus === "done" ? DIR.done : DIR.failed;
  const resultFilename = filename.replace(/\.json$/, ".result.json");
  fs.writeFileSync(path.join(targetDir, filename),        JSON.stringify(job,    null, 2), "utf-8");
  fs.writeFileSync(path.join(targetDir, resultFilename),  JSON.stringify(result, null, 2), "utf-8");
  fs.unlinkSync(runningPath);

  console.log(`[run-job] ${jobStatus.toUpperCase()}: ${jobId} → jobs/${jobStatus === "done" ? "done" : "failed"}/${filename}`);
  rlog({ level: jobStatus === "done" ? "INFO" : "ERROR", job_id: jobId, status: jobStatus, msg: jobError ?? "ok" });

  // P5.3 AUTH_EXPIRED retry hint
  if (jobStatus === "auth_expired" && authExpiredSite) {
    console.error(`\n[run-job] AUTH_EXPIRED: site="${authExpiredSite}" session 已過期`);
    console.error(`  1. 重新登入: SITE=${authExpiredSite} npm run refresh-auth`);
    console.error(`  2. 登入完成後重新執行: npm run run-job -- ${jobFile}`);
  }

  if (jobStatus === "done")         process.exit(0);
  if (jobStatus === "auth_expired") process.exit(4);
  process.exit(3);
}

// ── Step 迴圈 ─────────────────────────────────────────────────────────

async function executeSteps(
  steps: Step[],
  sessions: Map<string, WorkerSession>,
  results: StepResult[]
): Promise<void> {
  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    console.log(`[run-job] step[${i}] kind=${step.kind}`);

    if (step.kind === "web") {
      const r = await runWebStep(step, sessions);
      results.push(r);
      rlog({ level: r.status === "ok" ? "INFO" : "ERROR", step: i, kind: "web", status: r.status, msg: r.error ?? "ok" });
      if (r.status === "AUTH_EXPIRED") throw new AuthExpiredError(step.site);
      if (r.status === "error")        throw new Error(r.error ?? "web step failed");

    } else if (step.kind === "ssh") {
      const r = await runSshStep(step);
      results.push(r);
      rlog({ level: r.status === "ok" ? "INFO" : "ERROR", step: i, kind: "ssh", status: r.status, msg: r.error ?? "ok" });
      if (r.status === "error") throw new Error(r.error ?? "ssh step failed");
    }
  }
}

// ── Web Step 執行 ─────────────────────────────────────────────────────

async function runWebStep(
  step: WebStep,
  sessions: Map<string, WorkerSession>
): Promise<StepResult> {
  if (!sessions.has(step.site)) {
    const session = new WorkerSession(step.site);
    try {
      await session.init();
    } catch (err) {
      return { kind: "web", status: "error", error: (err as Error).message };
    }
    sessions.set(step.site, session);
  }

  const session = sessions.get(step.site)!;

  // action 名稱正規化（job schema 用底線命名，playwright-worker 用 camelCase）
  const actionMap: Record<string, unknown> = { type: step.action };
  if (step.url)      actionMap.url      = step.url;
  if (step.selector) actionMap.selector = step.selector;
  if (step.value)    actionMap.value    = step.value;

  if (actionMap.type === "open_page") actionMap.type = "goto";
  if (actionMap.type === "get_text")  actionMap.type = "getText";
  if (actionMap.type === "wait_for")  actionMap.type = "waitForSelector";

  const r = await session.runStep(actionMap);
  return { kind: "web", status: r.status, output: r.output, error: (r as { message?: string }).message };
}

// ── SSH Step 執行 ─────────────────────────────────────────────────────

async function runSshStep(step: SshStep): Promise<StepResult> {
  const r = await runSshCommand(step.command);
  if (r.exitCode === 0) {
    return { kind: "ssh", status: "ok", output: { stdout: r.stdout, stderr: r.stderr } };
  }
  return {
    kind:   "ssh",
    status: "error",
    output: { stdout: r.stdout, stderr: r.stderr, exitCode: r.exitCode },
    error:  r.error ?? `exit code ${r.exitCode}`,
  };
}

main();
