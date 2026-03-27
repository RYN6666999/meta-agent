/**
 * config.ts — runner.config.json 載入器
 *
 * 優先順序（SSH 設定）：環境變數 > runner.config.json
 */

import * as fs   from "fs";
import * as os   from "os";
import * as path from "path";

// ── 型別 ──────────────────────────────────────────────────────────────

export interface SshConfig {
  host:                 string;
  user:                 string;
  keyPath:              string;
  port:                 number;
  strictHostKeyChecking: "yes" | "no" | "accept-new";
  connectTimeoutSec:    number;
}

export interface SiteConfig {
  loginUrl: string;
}

export interface AuthNotifyConfig {
  webhookUrl: string;   // n8n webhook URL（POST target）
  timeoutMs?: number;   // HTTP timeout，預設 5000ms
}

export interface RunnerConfig {
  ssh:         SshConfig;
  sites:       Record<string, SiteConfig>;
  runner:      { jobTimeoutMs: number };
  authNotify?: AuthNotifyConfig;  // 未設定時靜默，不影響 job 流程
}

// ── 載入 ──────────────────────────────────────────────────────────────

const CONFIG_PATH = path.resolve(__dirname, "../runner.config.json");

let _cache: RunnerConfig | null = null;

export function loadConfig(): RunnerConfig {
  if (_cache) return _cache;
  if (!fs.existsSync(CONFIG_PATH)) {
    throw new Error(`找不到 runner.config.json\n  期望路徑: ${CONFIG_PATH}`);
  }
  _cache = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf-8")) as RunnerConfig;
  return _cache;
}

/** 取得合併後的 SSH 設定（env var 優先） */
export function getSshConfig(): SshConfig {
  const cfg = loadConfig().ssh;
  return {
    host:                 process.env.SSH_HOST      ?? cfg.host,
    user:                 process.env.SSH_USER      ?? cfg.user,
    keyPath:              expandHome(process.env.SSH_KEY_PATH ?? cfg.keyPath),
    port:                 cfg.port,
    strictHostKeyChecking: cfg.strictHostKeyChecking,
    connectTimeoutSec:    cfg.connectTimeoutSec,
  };
}

/** 取得指定 site 的 loginUrl */
export function getSiteLoginUrl(site: string): string | undefined {
  return loadConfig().sites[site]?.loginUrl;
}

/** 取得 authNotify 設定，未設定時回傳 null */
export function getAuthNotifyConfig(): AuthNotifyConfig | null {
  return loadConfig().authNotify ?? null;
}

/** ~ 展開 */
export function expandHome(p: string): string {
  return p.startsWith("~/") ? path.join(os.homedir(), p.slice(2)) : p;
}
