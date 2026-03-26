/**
 * refresh-auth.ts — 手動登入並儲存 Playwright auth state
 *
 * 使用方式：
 *   SITE=github LOGIN_URL=https://github.com/login npm run refresh-auth
 *   SITE=cloudflare LOGIN_URL=https://dash.cloudflare.com/login npm run refresh-auth
 *   SITE=google LOGIN_URL=https://accounts.google.com npm run refresh-auth
 *
 * 輸出：
 *   ../auth/sites/<SITE>/auth-state.json   （storageState：cookies + localStorage）
 *   ../auth/sites/<SITE>/profile/          （browser user data dir）
 *
 * 環境變數：
 *   SITE        網站識別名稱（必填，例如 github / cloudflare / google）
 *   LOGIN_URL   登入頁面網址（必填）
 *   BROWSER     chromium | firefox | webkit（預設 chromium）
 *
 * Exit codes：
 *   0 = 成功儲存
 *   1 = 缺少必要環境變數
 *   2 = 儲存失敗
 */

import * as fs from "fs";
import * as path from "path";
import * as readline from "readline";
import { chromium, firefox, webkit, BrowserType } from "playwright";
import { getSiteLoginUrl } from "./config";

// ── 設定 ──────────────────────────────────────────────────────────────

const AUTH_BASE = path.resolve(__dirname, "../../auth/sites");

// ── 主程式 ────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const site     = process.env.SITE ?? "";
  const loginUrl = process.env.LOGIN_URL ?? "";

  if (!site) {
    console.error("[refresh-auth] ERROR: 請設定 SITE 環境變數");
    console.error("  範例: SITE=github LOGIN_URL=https://github.com/login npm run refresh-auth");
    process.exit(1);
  }

  // 若未指定 LOGIN_URL，自動從 runner.config.json 查詢
  const resolvedUrl = loginUrl || getSiteLoginUrl(site) || "";

  if (!resolvedUrl) {
    console.error("[refresh-auth] ERROR: 找不到 LOGIN_URL");
    console.error(`  方式 1: SITE=${site} LOGIN_URL=https://example.com/login npm run refresh-auth`);
    console.error(`  方式 2: 在 runner.config.json 的 sites.${site}.loginUrl 填入網址`);
    process.exit(1);
  }

  const siteDir    = path.join(AUTH_BASE, site);
  const authState  = path.join(siteDir, "auth-state.json");
  const profileDir = path.join(siteDir, "profile");

  fs.mkdirSync(siteDir, { recursive: true });
  fs.mkdirSync(profileDir, { recursive: true });

  // 選擇瀏覽器引擎
  const browserName = (process.env.BROWSER ?? "chromium") as string;
  const browserType: BrowserType =
    browserName === "firefox" ? firefox :
    browserName === "webkit"  ? webkit  :
    chromium;

  console.log(`[refresh-auth] Site    : ${site}`);
  console.log(`[refresh-auth] 瀏覽器  : ${browserName}`);
  console.log(`[refresh-auth] 登入頁  : ${resolvedUrl}`);
  console.log(`[refresh-auth] 儲存至  : ${authState}`);

  // 啟動 headed browser（persistent context 保留完整 profile）
  const context = await browserType.launchPersistentContext(profileDir, {
    headless: false,
    viewport: null,
    ignoreHTTPSErrors: false,
  });

  const page = context.pages()[0] ?? await context.newPage();

  try {
    await page.goto(resolvedUrl, { waitUntil: "domcontentloaded", timeout: 30_000 });
  } catch (err) {
    console.warn(`[refresh-auth] 警告: 開啟登入頁失敗 (${(err as Error).message})`);
    console.warn("[refresh-auth] 請在瀏覽器中手動導覽到登入頁面");
  }

  console.log("");
  console.log("──────────────────────────────────────────");
  console.log(`  Site: ${site}`);
  console.log("  請在瀏覽器中完成登入。");
  console.log("  登入完成後，回到此終端機按下 Enter。");
  console.log("──────────────────────────────────────────");
  console.log("");

  await waitForEnter();

  try {
    await context.storageState({ path: authState });
    console.log(`[refresh-auth] ✓ auth-state.json 已儲存: ${authState}`);
  } catch (err) {
    console.error(`[refresh-auth] ERROR: 儲存失敗: ${(err as Error).message}`);
    await context.close();
    process.exit(2);
  }

  await context.close();
  console.log(`[refresh-auth] 完成。後續 job 指定 "site": "${site}" 即可重用此登入狀態。`);
  process.exit(0);
}

// ── 輔助 ──────────────────────────────────────────────────────────────

function waitForEnter(): Promise<void> {
  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    rl.question("按 Enter 儲存登入狀態... ", () => { rl.close(); resolve(); });
  });
}

main();
