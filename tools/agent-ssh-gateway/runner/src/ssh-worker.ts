/**
 * ssh-worker.ts — 透過 SSH Gateway 執行單次命令
 *
 * 設定來源（優先順序：env var > runner.config.json）：
 *   SSH_HOST / SSH_USER / SSH_KEY_PATH / SSH_PORT
 *
 * 此模組由 run-job.ts 呼叫，不直接執行。
 */

import { spawn } from "child_process";
import { getSshConfig } from "./config";

// ── 型別 ──────────────────────────────────────────────────────────────

export interface SshCommandResult {
  stdout:   string;
  stderr:   string;
  exitCode: number;
  error?:   string;
}

// ── 主函式 ────────────────────────────────────────────────────────────

export function runSshCommand(command: string): Promise<SshCommandResult> {
  return new Promise((resolve) => {
    const cfg = getSshConfig();

    if (!cfg.host) {
      resolve({ stdout: "", stderr: "", exitCode: 1,
        error: "SSH host 未設定，請在 runner.config.json 填入 ssh.host 或設定 SSH_HOST 環境變數" });
      return;
    }

    const args = [
      "-i", cfg.keyPath,
      "-p", String(cfg.port),
      "-o", "BatchMode=yes",
      "-o", `StrictHostKeyChecking=${cfg.strictHostKeyChecking}`,
      "-o", `ConnectTimeout=${cfg.connectTimeoutSec}`,
      `${cfg.user}@${cfg.host}`,
      command,
    ];

    console.log(`[ssh-worker] ${cfg.user}@${cfg.host} $ ${command}`);

    const proc = spawn("ssh", args, { stdio: ["ignore", "pipe", "pipe"] });

    let stdout = "";
    let stderr = "";

    proc.stdout.on("data", (chunk: Buffer) => { stdout += chunk.toString(); });
    proc.stderr.on("data", (chunk: Buffer) => { stderr += chunk.toString(); });

    proc.on("error", (err) => {
      resolve({ stdout, stderr, exitCode: 1, error: err.message });
    });

    proc.on("close", (code) => {
      resolve({ stdout, stderr, exitCode: code ?? 1 });
    });
  });
}
