/**
 * run-job.ts — Job Runner 進入點
 *
 * 使用方式：
 *   npm run run-job -- jobs/incoming/job-001.json
 *
 * Job 生命週期：
 *   jobs/incoming/<id>.json
 *     → jobs/running/<id>.json   （執行中）
 *     → jobs/done/<id>.json      （成功）
 *     → jobs/failed/<id>.json    （失敗 / AUTH_EXPIRED）
 *
 * Result JSON 寫入同一份檔案（附加 result 欄位）
 *
 * Exit codes：
 *   0 = job 完成（done）
 *   1 = 參數錯誤
 *   2 = job 格式錯誤
 *   3 = 執行失敗（failed）
 *   4 = AUTH_EXPIRED
 */

import * as fs   from "fs";
import * as path from "path";
import { WorkerSession }  from "./playwright-worker";
import { runSshCommand }  from "./ssh-worker";
import { loadConfig }     from "./config";

// ── 型別定義 ──────────────────────────────────────────────────────────

export type JobType = "web" | "ssh" | "hybrid";

export interface WebStep {
  kind:   "web";
  site:   string;   // 對應 auth/sites/<site>/auth-state.json
  action: string;   // open_page | click | fill | get_text | wait_for
  url?:       string;
  selector?:  string;
  value?:     string;
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
  // 向下相容舊欄位（Phase 2 格式）
  id?:      string;
  site?:    string;
  target?:  string;
  actions?: unknown[];
}

export interface StepResult {
  kind:     "web" | "ssh";
  status:   "ok" | "error" | "AUTH_EXPIRED";
  output?:  unknown;
  error?:   string;
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

  // 解析 job JSON
  let job: Job;
  try {
    const raw = fs.readFileSync(jobPath, "utf-8");
    job = JSON.parse(raw) as Job;
  } catch {
    console.error("[run-job] ERROR: job JSON 格式錯誤");
    process.exit(2);
  }

  // 向下相容：舊格式 id → job_id
  if (!job.job_id && job.id) job.job_id = job.id;

  if (!job.job_id || !job.type || !Array.isArray(job.steps)) {
    console.error("[run-job] ERROR: job 缺少必要欄位 (job_id, type, steps)");
    process.exit(2);
  }

  const jobId    = job.job_id;
  const filename = path.basename(jobPath);

  // 確保目錄存在
  Object.values(DIR).forEach((d) => fs.mkdirSync(d, { recursive: true }));

  // incoming → running
  const runningPath = path.join(DIR.running, filename);
  fs.copyFileSync(jobPath, runningPath);
  if (jobPath.startsWith(DIR.incoming)) {
    fs.unlinkSync(jobPath);
  }

  console.log(`[run-job] 開始執行: ${jobId} (type=${job.type}, steps=${job.steps.length})`);

  const startedAt   = new Date().toISOString();
  const stepResults: StepResult[] = [];
  const sessions    = new Map<string, WorkerSession>();
  const timeoutMs   = loadConfig().runner.jobTimeoutMs;

  let jobStatus: JobResult["status"] = "done";
  let jobError: string | undefined;

  // Job 整體逾時保護
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
    const msg = (err as Error).message;
    if (msg.startsWith("AUTH_EXPIRED:")) {
      jobStatus = "auth_expired";
    } else {
      jobStatus = "failed";
    }
    jobError = msg;
  } finally {
    clearTimeout(timeoutHandle);
    // 關閉所有 web session
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

  // job 定義與 result 分開寫入
  const targetDir      = jobStatus === "done" ? DIR.done : DIR.failed;
  const jobOutPath     = path.join(targetDir, filename);
  const resultFilename = filename.replace(/\.json$/, ".result.json");
  const resultPath     = path.join(targetDir, resultFilename);

  fs.writeFileSync(jobOutPath, JSON.stringify(job, null, 2), "utf-8");
  fs.writeFileSync(resultPath, JSON.stringify(result, null, 2), "utf-8");
  fs.unlinkSync(runningPath);

  console.log(`[run-job] ${jobStatus.toUpperCase()}: ${jobId} → jobs/${jobStatus === "done" ? "done" : "failed"}/${filename}`);

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
      if (r.status === "AUTH_EXPIRED") {
        throw new Error(`AUTH_EXPIRED: site="${step.site}"，請重新執行 refresh-auth`);
      }
      if (r.status === "error") throw new Error(r.error ?? "web step failed");

    } else if (step.kind === "ssh") {
      const r = await runSshStep(step);
      results.push(r);
      if (r.status === "error") throw new Error(r.error ?? "ssh step failed");
    }
  }
}

// ── Web Step 執行 ─────────────────────────────────────────────────────

async function runWebStep(
  step: WebStep,
  sessions: Map<string, WorkerSession>
): Promise<StepResult> {
  // 初始化 session（同 site 重用）
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

  // 將 WebStep action 轉換為 runStep 格式
  const actionMap: Record<string, unknown> = { type: step.action };
  if (step.url)      actionMap.url      = step.url;
  if (step.selector) actionMap.selector = step.selector;
  if (step.value)    actionMap.value    = step.value;

  // action 名稱正規化：open_page → goto
  if (actionMap.type === "open_page") actionMap.type = "goto";
  if (actionMap.type === "get_text")  actionMap.type = "getText";
  if (actionMap.type === "wait_for")  actionMap.type = "waitForSelector";

  const r = await session.runStep(actionMap as Record<string, unknown>);
  return { kind: "web", status: r.status, output: r.output, error: (r as {message?: string}).message };
}

// ── SSH Step 執行 ─────────────────────────────────────────────────────

async function runSshStep(step: SshStep): Promise<StepResult> {
  const r = await runSshCommand(step.command);
  if (r.exitCode === 0) {
    return { kind: "ssh", status: "ok", output: { stdout: r.stdout, stderr: r.stderr } };
  }
  return {
    kind: "ssh",
    status: "error",
    output: { stdout: r.stdout, stderr: r.stderr, exitCode: r.exitCode },
    error: r.error ?? `exit code ${r.exitCode}`,
  };
}

main();
