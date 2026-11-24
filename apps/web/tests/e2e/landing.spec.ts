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
  // Scroll timelines move only with the reader (A2); A4 removed the marquee, so nothing is exempt.
  const running = await page.evaluate(() => document.getAnimations().filter((a) => a.playState === "running"
    && a.timeline === document.timeline).map((a) => (a as CSSAnimation).animationName));
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

test("the hero is one ENS measure beside its self-assessment, with the headline at most 5rem", async ({ page }) => {
  for (const width of [1024, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    const size = await page.getByRole("heading", { level: 1 }).evaluate((h) => parseFloat(getComputedStyle(h).fontSize));
    expect(size, `${width}px headline size`).toBeLessThanOrEqual(80);
    const doc = page.locator(".landing-hero .measure-sheet");
    await expect(doc).toBeVisible();
    await expect(doc.locator("mark")).toContainText("[op.acc.6.r8.1]");
    // The document starts above the fold, so the first screen shows the law, not only a headline.
    expect(await doc.evaluate((el) => el.getBoundingClientRect().top), `${width}px document top`).toBeLessThan(900);
  }
});

test("the proof strip appears once on the landing, in the footer", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".proof-strip")).toHaveCount(1);
  await expect(page.locator("footer .proof-strip")).toHaveCount(1);
});

test("the pinned steps show each stage at its scroll position, with no counter", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto("/");
  const pinned = page.locator(".landing-pinned");
  await expect(page.locator(".landing-stage-counter")).toHaveCount(0);
  for (const step of [1, 2, 3, 4, 5]) {
    await page.locator(`.landing-steps > li[data-step="${step}"]`).evaluate((el) => el.scrollIntoView({ block: "center" }));
    await expect(pinned).toHaveAttribute("data-stage", String(step));
    // The connect step (5) is coming soon and has no product view.
    await expect(page.locator(".landing-stage[data-active='true']")).toHaveCount(step === 5 ? 0 : 1);
  }
});

test("phones and reduced motion get one step per row, each with its own frame, and no break inside a word", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await page.goto("/");
  await expect(page.locator(".landing-stage-frame")).toBeHidden();
  await expect(page.locator(".landing-step-stage").first()).toBeVisible();
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const width of [1064, 1280, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/");
    await expect(page.locator(".landing-stage-frame")).toBeHidden();
    await expect(page.locator(".landing-step-stage").nth(3)).toBeVisible();
    const columns = await page.locator(".landing-steps > li").evaluateAll((els) => new Set(els.map((el) => Math.round(el.getBoundingClientRect().left))).size);
    expect(columns, `${width}px: one step per row`).toBe(1);
    const wraps = await page.locator(".landing-step-title, .landing-step-body, .landing-sub, .landing-statement").evaluateAll((els) => els.map((el) => getComputedStyle(el).overflowWrap));
    expect(wraps.filter((w) => w === "anywhere"), `${width}px`).toEqual([]);
  }
});

test("the assistant launcher stays clear of the hero on a phone and shows on ink", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const launcher = page.locator(".assistant-launcher");
  const covers = await launcher.evaluate((el) => {
    if (getComputedStyle(el).visibility === "hidden") return false;
    const box = el.getBoundingClientRect();
    const hero = document.querySelector(".landing-hero")!.getBoundingClientRect();
    return box.top < hero.bottom && box.bottom > hero.top;
  });
  expect(covers).toBe(false);
  await page.locator(".landing-close").scrollIntoViewIfNeeded();
  await expect(launcher).toBeVisible();
  // On ink it keeps a paper keyline, so it does not disappear into the band.
  expect(await launcher.evaluate((el) => getComputedStyle(el).boxShadow)).toContain("244, 241, 234");
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
