import { expect, test } from "@playwright/test";
import { expectPolished } from "./polish";

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
  // Amendment A2: scroll timelines move only with the reader, and the marquee has its own pause button.
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running"
    && a.timeline === document.timeline && !(a as CSSAnimation).animationName?.startsWith("landing-marquee")).map((a) => (a as CSSAnimation).animationName));
  expect(running).toEqual([]);
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

test("the pinned steps show each stage at its scroll position, with the counter", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  const pinned = page.locator(".landing-pinned");
  for (const step of [1, 2, 3, 4]) {
    await page.locator(`.landing-steps > li[data-step="${step}"]`).evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect(pinned).toHaveAttribute("data-stage", String(step));
    await expect(page.locator(".landing-stage-counter")).toHaveText(`0${step} / 04`);
    await expect(page.locator(".landing-stage[data-active='true']")).toHaveCount(1);
  }
});

test("phones and reduced motion get the unpinned steps, each with its own frame", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.locator(".landing-stage-frame")).toBeHidden();
  await expect(page.locator(".landing-step-stage").first()).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.locator(".landing-stage-frame")).toBeHidden();
  await expect(page.locator(".landing-step-stage").nth(3)).toBeVisible();
});

test("the frameworks marquee pauses from its button", async ({ page }) => {
  await page.goto("/");
  const button = page.getByRole("button", { name: "Pausar la animación" });
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  expect(await page.locator(".landing-marquee-track").evaluate((el) => getComputedStyle(el).animationPlayState)).toBe("paused");
});

test("the landing is polished at 1440 px, light and dark, and its LCP stays fast", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  for (const colorScheme of ["light", "dark"] as const) {
    await page.emulateMedia({ colorScheme });
    await page.goto("/");
    await expectPolished(page, `landing 1440 ${colorScheme}`);
  }
  const lcp = await page.evaluate(() => new Promise<number>((resolve) => {
    new PerformanceObserver((list) => { const entries = list.getEntries(); resolve(entries.at(-1)!.startTime); }).observe({ type: "largest-contentful-paint", buffered: true });
  }));
  expect(lcp).toBeLessThan(2500);
});
