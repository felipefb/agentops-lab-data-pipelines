import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const SHOTS = "E:/AgentOpsLab/artifacts/screenshots";
const ROUTES = ["", "ops", "war-room", "collab", "approval", "observatory", "arena", "value", "use-cases", "present"];
const VIEWPORTS = [{ w: 375, h: 812 }, { w: 768, h: 1024 }, { w: 1440, h: 900 }];

for (const vp of VIEWPORTS) {
  test(`all screens render at ${vp.w}px`, async ({ page }) => {
    await page.setViewportSize({ width: vp.w, height: vp.h });
    for (const r of ROUTES) {
      await page.goto(`/#/${r}`);
      await expect(page.locator("main h1").first()).toBeVisible();
      await page.waitForLoadState("networkidle");
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow, `horizontal overflow on /${r} at ${vp.w}px`).toBeLessThanOrEqual(1);
      await page.waitForTimeout(1200);
      await page.screenshot({ path: `${SHOTS}/${vp.w}/${r || "hero"}.png`, fullPage: r !== "present" });
    }
  });
}

test("accessibility: no serious/critical axe violations (dark and light)", async ({ page }) => {
  for (const theme of ["dark", "light"]) {
    await page.goto("/#/");
    await page.evaluate((t) => localStorage.setItem("theme", t), theme);
    for (const r of ROUTES) {
      await page.goto(`/#/${r}`);
      await page.waitForLoadState("networkidle");
      const res = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"]).analyze();
      const bad = res.violations.filter((v) => ["serious", "critical"].includes(v.impact ?? ""));
      expect(bad.map((v) => `${theme}/${r}: ${v.id} ${v.nodes.map((n) => n.target.join(" ")).join(" | ").slice(0, 300)}`)).toEqual([]);
    }
  }
});

test("keyboard: skip link and nav reachable", async ({ page }) => {
  await page.goto("/#/");
  await page.keyboard.press("Tab");
  await expect(page.getByText("Pular para o conteúdo")).toBeFocused();
  await page.goto("/#/present");
  await page.keyboard.press("ArrowRight");
  await expect(page.getByText("Cena 2/6")).toBeVisible();
});

test("benchmark arena: every strategy card is MEDIDO with sample size, no BLOCKED placeholder", async ({ page }) => {
  await page.goto("/#/arena");
  for (const name of ["Baseline sem IA", "Agente assistido", "Agente supervisionado"]) {
    const card = page.locator("article", { hasText: name }).first();
    await expect(card.getByText("MEDIDO")).toBeVisible();
    await expect(card).toContainText("n=");
  }
});

test("arena: a run without agents shows BLOCKED, never fake numbers", async ({ page }) => {
  await page.goto("/#/arena");
  await page.getByLabel("Run").selectOption("holdout-baseline-v1");
  const card = page.locator("article", { hasText: "Agente assistido" });
  await expect(card.getByText("BLOCKED")).toBeVisible();
  await expect(card).not.toContainText("%");
});

test("demo flow: inject -> investigate -> human approval -> validated recovery", async ({ page }) => {
  await page.goto("/#/ops");
  await page.getByLabel("Classe de falha").selectOption("duplicates");
  await page.getByRole("button", { name: /Injetar falha/ }).click();
  await expect(page.getByText(/duplicates-L1-s1/)).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${SHOTS}/flow/1-injected.png`, fullPage: true });
  await page.getByRole("link", { name: /Abrir War Room/ }).click();
  await page.getByRole("button", { name: /Investigar e planejar/ }).click();
  await expect(page.getByText("dedupe_table").first()).toBeVisible({ timeout: 30_000 });
  await page.screenshot({ path: `${SHOTS}/flow/2-war-room.png`, fullPage: true });
  await page.getByRole("link", { name: /Approval Center/ }).click();
  await page.getByLabel("Seu nome").fill("Felipe (e2e)");
  await page.screenshot({ path: `${SHOTS}/flow/3-approval.png`, fullPage: true });
  await page.getByRole("button", { name: /Aprovar e executar/ }).click();
  await expect(page.getByText("RESOLVED").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText("validated_recovery")).toBeVisible();
  await page.screenshot({ path: `${SHOTS}/flow/4-resolved.png`, fullPage: true });
  await page.goto("/#/collab");
  await page.screenshot({ path: `${SHOTS}/flow/5-collab.png`, fullPage: true });
});

test("approval by unauthorized role executes nothing and escalates", async ({ page }) => {
  await page.goto("/#/ops");
  await page.getByLabel("Classe de falha").selectOption("null_keys");
  await page.getByRole("button", { name: /Injetar falha/ }).click();
  await expect(page.getByText(/null_keys-L1-s1/)).toBeVisible({ timeout: 30_000 });
  await page.goto("/#/war-room");
  await page.getByRole("button", { name: /Investigar e planejar/ }).click();
  await page.getByRole("link", { name: /Approval Center/ }).click();
  await page.getByLabel("Seu nome").fill("intruso");
  await page.getByLabel("Papel (RBAC)").selectOption("analyst");
  await page.getByRole("button", { name: /Aprovar e executar/ }).click();
  await expect(page.getByText("ESCALATED").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/not authorized/)).toBeVisible();
});

test("API error state is shown when backend fails", async ({ page }) => {
  await page.route("**/api/runs", (r) => r.fulfill({ status: 500, body: "{}" }));
  await page.goto("/#/arena");
  await expect(page.getByRole("alert")).toBeVisible();
});
