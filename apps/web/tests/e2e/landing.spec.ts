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
