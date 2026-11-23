import { expect, test } from "@playwright/test";

/**
 * Landing, part 1 (landing-legal spec, #308): no third party and no cookie before the visitor acts,
 * motion that rests on its final state, stops under reduced motion and never loops, and a stable
 * layout. Accessibility, overflow, text size and targets are in public-pages.spec.ts.
 */
test("the landing calls no third party and sets no cookie before the visitor acts", async ({ page, context }) => {
  const hosts = new Set<string>();
  page.on("request", (request) => hosts.add(new URL(request.url()).host));
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Prepara el ENS sin un consultor a tiempo completo");
  await page.waitForLoadState("networkidle");
  expect([...hosts]).toEqual(["localhost:3000"]);
  expect(await context.cookies()).toEqual([]);
});

test("motion stops under reduced motion and nothing runs after five seconds", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByRole("figure").first()).toBeVisible();
  expect(await page.evaluate(() => document.getAnimations().length)).toBe(0);
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await page.goto("/");
  await page.waitForTimeout(5_000);
  expect(await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running").length)).toBe(0);
});

test("the layout stays put while the landing loads", async ({ page }) => {
  await page.goto("/");
  await page.waitForTimeout(3_000);
  const cls = await page.evaluate(() => new Promise<number>((resolve) => {
    let total = 0;
    new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) if (!entry.hadRecentInput) total += entry.value;
    }).observe({ type: "layout-shift", buffered: true });
    setTimeout(() => resolve(total), 200);
  }));
  expect(cls).toBeLessThan(0.1);
});

test("the hero's four figures stay on one row at every desktop width, with no empty cell", async ({ page }) => {
  for (const width of [1024, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const tiles = page.locator(".landing-hero .lv-kpis > div");
    await expect(tiles).toHaveCount(4);
    const tops = await tiles.evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
    expect(new Set(tops).size, `${width}px: ${tops.join(",")}`).toBe(1);
    const grid = await page.locator(".landing-hero .lv-kpis").evaluate((el) => {
      const box = el.getBoundingClientRect();
      const last = el.lastElementChild!.getBoundingClientRect();
      return { gap: Math.round(box.right - last.right) };
    });
    expect(grid.gap, `${width}px: the last tile reaches the grid's edge`).toBeLessThanOrEqual(2);
    // The headline stays a headline: at most three lines beside the frame.
    const lines = await page.getByRole("heading", { level: 1 }).evaluate((h) => Math.round(h.getBoundingClientRect().height / parseFloat(getComputedStyle(h).lineHeight)));
    expect(lines, `${width}px headline lines`).toBeLessThanOrEqual(width >= 1280 ? 3 : 4);
  }
});
