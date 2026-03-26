/**
 * playwright-worker.ts — 帶入已登入狀態執行網頁任務
 *
 * 核心流程：
 *   1. 從 job.site 決定載入哪個 auth profile（auth/sites/<site>/auth-state.json）
 *   2. 建立帶登入狀態的 browser context
 *   3. 提供 openPage / checkAuthenticated / runStep 三個基本函式
 *   4. 偵測 session 過期（導回登入頁）→ 回傳 AUTH_EXPIRED
 *
 * 此模組由 run-job.ts 呼叫，不直接執行。
 */

import * as fs from "fs";
import * as path from "path";
import { chromium, BrowserContext, Page } from "playwright";

// ── 設定 ──────────────────────────────────────────────────────────────

const AUTH_BASE = path.resolve(__dirname, "../../auth/sites");

// 登入頁特徵：URL 包含這些字串時視為被導回登入頁
const LOGIN_PAGE_PATTERNS = [
  "/login",
  "/signin",
  "/auth",
  "/sso",
  "login.html",
  "accounts.google.com",
  "login.microsoftonline.com",
];

// ── 型別 ──────────────────────────────────────────────────────────────

export type StepResult =
  | { status: "ok";           output: unknown }
  | { status: "AUTH_EXPIRED"; output: null }
  | { status: "error";        output: null; message: string };

// ── WorkerSession ─────────────────────────────────────────────────────

export class WorkerSession {
  private context: BrowserContext | null = null;
  private page: Page | null = null;
  private site: string;

  constructor(site: string) {
    this.site = site;
  }

  /** 初始化：載入指定 site 的 auth state */
  async init(): Promise<void> {
    const authState = path.join(AUTH_BASE, this.site, "auth-state.json");

    if (!fs.existsSync(authState)) {
      throw new Error(
        `找不到 ${this.site} 的 auth state，請先執行：\n` +
        `  SITE=${this.site} LOGIN_URL=<登入頁網址> npm run refresh-auth\n` +
        `  期望路徑: ${authState}`
      );
    }

    const browser = await chromium.launch({ headless: true });
    this.context = await browser.newContext({ storageState: authState });
    this.page = await this.context.newPage();
  }

  /** 開啟頁面，自動偵測是否被導回登入頁 */
  async openPage(url: string): Promise<StepResult> {
    if (!this.page) throw new Error("WorkerSession 尚未初始化");

    await this.page.goto(url, { waitUntil: "domcontentloaded", timeout: 30_000 });

    if (this.isLoginPage(this.page.url())) {
      return { status: "AUTH_EXPIRED", output: null };
    }

    return { status: "ok", output: { url: this.page.url() } };
  }

  /** 確認目前頁面是否為已登入狀態 */
  async checkAuthenticated(): Promise<boolean> {
    if (!this.page) return false;
    return !this.isLoginPage(this.page.url());
  }

  /**
   * 執行單一步驟
   * 支援：goto / click / fill / getText / waitForSelector
   */
  async runStep(action: Record<string, unknown>): Promise<StepResult> {
    if (!this.page) throw new Error("WorkerSession 尚未初始化");

    try {
      const type = action.type as string;

      switch (type) {
        case "goto": {
          return await this.openPage(action.url as string);
        }
        case "click": {
          await this.page.click(action.selector as string, { timeout: 10_000 });
          return { status: "ok", output: null };
        }
        case "fill": {
          await this.page.fill(action.selector as string, action.value as string);
          return { status: "ok", output: null };
        }
        case "getText": {
          const text = await this.page.textContent(action.selector as string, { timeout: 10_000 });
          return { status: "ok", output: { text } };
        }
        case "waitForSelector": {
          await this.page.waitForSelector(action.selector as string, { timeout: 15_000 });
          return { status: "ok", output: null };
        }
        default:
          return { status: "error", output: null, message: `未知 action type: ${type}` };
      }
    } catch (err) {
      if (this.isLoginPage(this.page.url())) {
        return { status: "AUTH_EXPIRED", output: null };
      }
      return { status: "error", output: null, message: (err as Error).message };
    }
  }

  async close(): Promise<void> {
    if (this.context) {
      await this.context.close();
      this.context = null;
      this.page = null;
    }
  }

  private isLoginPage(url: string): boolean {
    return LOGIN_PAGE_PATTERNS.some((p) => url.toLowerCase().includes(p));
  }
}

