// Browser-side proof. Uses the official packaged DSH Web UI unchanged.
// Auth bearer URL is passed only via ephemeral process environment.
// Do not log URL, cookie, screenshot, page HTML, or provider messages.
import { chromium } from "playwright";

const MARKER = "TRISYNORA_BROWSER_MCP_DONE";
const report = { ok: false, stage: "initial", authenticated: false, submitted: false };
let browser;
let observedPage;
let pageErrors = 0;

async function main() {
  if (!process.env.DSH_AUTH_URL || !process.env.TRISYNORA_BROWSER_WORKSPACE) {
    throw new Error("missing isolated browser inputs");
  }
  report.stage = "chromium-launch";
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 }, locale: "en-US",
  });

  observedPage = page;
  page.on("pageerror", () => { pageErrors++; });
  report.stage = "browser-authenticated-boot";
  await page.goto(process.env.DSH_AUTH_URL, { waitUntil: "load", timeout: 45000 });
  await page.locator("[data-composer-input]").first().waitFor({ timeout: 45000 });
  report.authenticated = true;

  // The official first-run Web composition displays its preview notice over
  // an inert root. Acknowledge only that notice in the disposable CI profile;
  // never bypass a permission, product approval or credential dialog.
  report.stage = "browser-preview-notice";
  const welcomeAction = page.getByRole("dialog")
    .getByRole("button", { name: /^(继续|Continue)$/ });
  const input = page.locator('[data-composer-input][contenteditable="true"]').first();
  // First-use notice and initial workspace are asynchronous. Never decide
  // no notice exists from an immediate count(): it can mount after boot.
  const readyBy = Date.now() + 30000;
  while (Date.now() < readyBy) {
    if (await welcomeAction.isVisible().catch(() => false)) {
      await welcomeAction.click();
      await welcomeAction.waitFor({ state: "hidden", timeout: 15000 });
    }
    const blocked = await page.locator("#root")
      .evaluate(el => el.inert).catch(() => true);
    if (!blocked) break;
    await page.waitForTimeout(250);
  }
  if (await page.locator("#root").evaluate(el => el.inert).catch(() => true)) {
    throw new Error("first-run notice still blocking browser UI");
  }

  report.stage = "browser-default-workspace-initialization";
  // Shipped first-use Web prepares a default Workspace asynchronously.
  // Do not mistake the initial read-only composer for absent Workspace.
  await input.waitFor({ state: "visible", timeout: 20000 }).catch(() => {});
  if (!(await input.isVisible().catch(() => false))) {
    report.stage = "browser-workspace-picker-trigger";
    const choose = page.getByRole("textbox", { name: "Choose workspace" })
      .or(page.getByRole("button", { name: "Choose workspace" })).first();
    await choose.click({ timeout: 10000 });
    report.stage = "browser-workspace-picker-dialog";
    const dialog = page.getByRole("dialog", { name: "Select Workspace Directory" });
    await dialog.waitFor({ timeout: 15000 });
    report.stage = "browser-workspace-picker-path";
    await dialog.getByRole("button", { name: "Edit path" }).click();
    const pathField = dialog.getByRole("textbox", { name: "Edit path" });
    await pathField.fill(process.env.TRISYNORA_BROWSER_WORKSPACE);
    await pathField.press("Enter");
    await dialog.getByRole("button", { name: "Open", exact: true }).click();
  }

  // Verify the shipped Web model picker, not a synthetic model settings
  // mutation or a direct provider call. CI runs this as an independent
  // disposable session after the baseline catalog-only smoke.
  const targetModel = process.env.TRISYNORA_MODEL_SWITCH_EXPECT;
  if (targetModel) {
    if (targetModel !== "deepseek-v4-pro") throw new Error("model allowlist");
    report.stage = "browser-model-menu";
    const selector = page.getByRole("button", { name: /^Select model/ }).first();
    await selector.waitFor({ state: "visible", timeout: 15000 });
    await selector.click();
    await page.getByRole("menuitem", { name: /^Model/ }).click();
    report.stage = "browser-model-select";
    await page.getByRole("menuitemradio", { name: /DeepSeek-V4-Pro/i }).click();
    await page.locator('[data-composer-input][contenteditable="true"]').first()
      .waitFor({ state: "visible", timeout: 15000 });
    report.modelSwitchSelected = true;
  }

  report.stage = "browser-compose";
  await input.waitFor({ state: "visible", timeout: 30000 });
  await input.fill("Use the TRISYNORA read-only capability list tool once. Report its catalog status.");
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  report.submitted = true;

  report.stage = "browser-result-visible";
  const response = page.locator('[data-chat-flow-kind="assistant-step"]')
    .filter({ hasText: MARKER }).last();
  await response.waitFor({ state: "visible", timeout: 80000 });
  const rendered = await response.innerText();
  if (!rendered.includes("catalog-only") ||
      !rendered.includes("nativeWriteToolsExposed=false")) {
    throw new Error("model did not display validated read-only catalog");
  }
  report.ok = true;
  report.stage = "complete";
}

try {
  await main();
} catch (error) {
  // Never echo page HTML, bearer URLs, credentials, or exception messages.
  // Only fixed boolean checks and counts to diagnose a boot gate.
  report.ok = false;
  if (observedPage) {
    const body = await observedPage.locator("body").innerText().catch(() => "");
    report.diagnostics = {
      composerCount: await observedPage.locator("[data-composer-input]").count().catch(() => -1),
      editableCount: await observedPage.locator('[data-composer-input][contenteditable="true"]').count().catch(() => -1),
      chooseWorkspaceButton: await observedPage.getByRole("button", { name: "Choose workspace" }).count().catch(() => -1),
      chooseWorkspaceTextbox: await observedPage.getByRole("textbox", { name: "Choose workspace" }).count().catch(() => -1),
      dialogCount: await observedPage.getByRole("dialog").count().catch(() => -1),
      rootInert: await observedPage.locator("#root").evaluate(el => el.inert).catch(() => null),
      pageErrors,
      uiKeywords: ["API Key", "key", "Welcome", "Settings", "Choose workspace", "Default workspace", "Unable to create", "Error", "Connect"].filter(x => body.includes(x)),
    };
  }
} finally {
  if (browser) await browser.close().catch(() => {});
  process.stdout.write(JSON.stringify(report) + "\n");
  if (!report.ok) process.exitCode = 2;
}
