// Host-cold-restart browser proof: a fresh Chromium process connects to a
// newly started DSH Host and continues the PREVIOUS persisted Session.
// The authenticated URL stays in the ephemeral process environment; never log it.
import { chromium } from "playwright";

const OLD_PROMPT = "Use the TRISYNORA read-only capability list tool once. Report its catalog status.";
const FOLLOWUP = "Continue the SAME earlier conversation after the Harness Host restart. TRISYNORA_HOST_RESTART_SECOND";
const MARKER = "TRISYNORA_BROWSER_MCP_DONE";
const report = { ok: false, stage: "initial" };
let browser;
let page;
let pageErrors = 0;

async function main() {
  if (!process.env.DSH_AUTH_URL || !process.env.TRISYNORA_BROWSER_WORKSPACE) {
    throw new Error("isolated browser inputs required");
  }
  report.stage = "fresh-chromium-start";
  browser = await chromium.launch({ headless: true, args: ["--no-sandbox"] });
  page = await browser.newPage({
    viewport: { width: 1280, height: 900 }, locale: "en-US",
  });
  page.on("pageerror", () => { pageErrors++; });

  report.stage = "new-host-authenticated-boot";
  await page.goto(process.env.DSH_AUTH_URL, {
    waitUntil: "load", timeout: 45000,
  });
  await page.locator("[data-composer-input]").first()
    .waitFor({ timeout: 45000 });
  report.authenticatedAfterHostRestart = true;

  report.stage = "host-restart-preview-notice";
  const welcome = page.getByRole("dialog")
    .getByRole("button", { name: /^(继续|Continue)$/ });
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (await welcome.isVisible().catch(() => false)) {
      await welcome.click();
      await welcome.waitFor({ state: "hidden", timeout: 15000 });
    }
    if (!(await page.locator("#root")
      .evaluate(el => el.inert).catch(() => true))) break;
    await page.waitForTimeout(250);
  }
  if (await page.locator("#root").evaluate(el => el.inert).catch(() => true)) {
    throw new Error("browser cannot access restarted host UI");
  }

  report.stage = "persisted-session-list";
  const oldResponse = page.locator('[data-chat-flow-kind="assistant-step"]')
    .filter({ hasText: MARKER }).last();
  if (!(await oldResponse.isVisible().catch(() => false))) {
    const treeRows = page.getByRole("treeitem");
    const group = treeRows.first();
    await group.waitFor({ state: "visible", timeout: 20000 });
    let rowsReady = false;
    for (let attempt = 0; attempt < 6; attempt++) {
      if (await group.getAttribute("aria-expanded") === "false") {
        await group.click();
      }
      rowsReady = await treeRows.nth(1).waitFor({
        state: "visible", timeout: 5000,
      }).then(() => true, () => false);
      if (rowsReady) break;
    }
    if (!rowsReady) throw new Error("prior sessions absent after host restart");
    report.persistedSessionRowVisible = true;

    const named = treeRows.filter({ hasText: /TRISYNORA mock title/ });
    if (await named.count()) {
      await named.last().click();
    } else {
      // No private session API, no newly created replacement session.
      // Only a candidate whose transcript contains the original MCP receipt
      // can satisfy this test.
      const count = await treeRows.count();
      for (let i = 1; i < Math.min(count, 8); i++) {
        if (!(await treeRows.nth(i).isVisible().catch(() => false))) continue;
        await treeRows.nth(i).click();
        if (await oldResponse.waitFor({
          state: "visible", timeout: 3500,
        }).then(() => true, () => false)) break;
      }
    }
  }

  report.stage = "old-mcp-transcript-from-disk";
  await oldResponse.waitFor({ state: "visible", timeout: 35000 });
  const oldText = await oldResponse.innerText();
  if (!oldText.includes("catalog-only") ||
      !oldText.includes("nativeWriteToolsExposed=false")) {
    throw new Error("persisted MCP receipt not restored");
  }
  await page.getByText(OLD_PROMPT, { exact: true })
    .waitFor({ state: "visible", timeout: 20000 });
  report.originalMcpTranscriptRecovered = true;

  report.stage = "continue-cold-restored-session";
  const markerRows = page.locator('[data-chat-flow-kind="assistant-step"]')
    .filter({ hasText: MARKER });
  const priorCount = await markerRows.count();
  const composer = page.locator('[data-composer-input][contenteditable="true"]').first();
  await composer.waitFor({ state: "visible", timeout: 30000 });
  await composer.fill(FOLLOWUP);
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  report.continuationSubmitted = true;
  await markerRows.nth(priorCount)
    .waitFor({ state: "visible", timeout: 80000 });
  report.continuationRendered = true;
  report.ok = true;
  report.stage = "complete";
}

try {
  await main();
} catch {
  report.ok = false;
  if (page) {
    report.diagnostics = {
      treeItemCount: await page.getByRole("treeitem").count().catch(() => -1),
      firstTreeItemExpanded: await page.getByRole("treeitem").first()
        .getAttribute("aria-expanded").catch(() => null),
      oldResponseCount: await page.locator('[data-chat-flow-kind="assistant-step"]')
        .filter({ hasText: MARKER }).count().catch(() => -1),
      rootInert: await page.locator("#root")
        .evaluate(el => el.inert).catch(() => null),
      dialogs: await page.getByRole("dialog").count().catch(() => -1),
      pageErrors,
    };
  }
} finally {
  if (browser) await browser.close().catch(() => {});
  process.stdout.write(JSON.stringify(report) + "\n");
  if (!report.ok) process.exitCode = 2;
}
