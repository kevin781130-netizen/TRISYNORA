// Browser-side proof. Uses the official packaged DSH Web UI unchanged.
// Auth bearer URL is passed only via ephemeral process environment.
// Do not log URL, cookie, screenshot, page HTML, or provider messages.
import { chromium } from "playwright";

const MARKER = "TRISYNORA_BROWSER_MCP_DONE";
const report = { ok: false, stage: "initial", authenticated: false, submitted: false };
let browser;

async function main() {
  if (!process.env.DSH_AUTH_URL || !process.env.TRISYNORA_BROWSER_WORKSPACE) {
    throw new Error("missing isolated browser inputs");
  }
  report.stage = "chromium-launch";
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  const page = await browser.newPage({
    viewport: { width: 1280, height: 900 }, locale: "en-US",
  });

  report.stage = "browser-authenticated-boot";
  await page.goto(process.env.DSH_AUTH_URL, { waitUntil: "load", timeout: 45000 });
  await page.locator("[data-composer-input]").first().waitFor({ timeout: 45000 });
  report.authenticated = true;

  const input = page.locator('[data-composer-input][contenteditable="true"]').first();
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
  // A stable stage string is sufficient for public CI; error objects may
  // contain bearer URLs and must NEVER be echoed into GitHub Actions.
  report.ok = false;
} finally {
  if (browser) await browser.close().catch(() => {});
  process.stdout.write(JSON.stringify(report) + "\n");
  if (!report.ok) process.exitCode = 2;
}
