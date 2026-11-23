import AxeBuilder from "@axe-core/playwright";
import { type Page, expect } from "@playwright/test";

/**
 * The polish bar shared by the console and public e2e specs (ui-polish spec): no axe violation of
 * any impact, nothing scrolls sideways (inside table regions too), no interface text under 13 px,
 * standalone targets 44 px on a phone.
 */
/** Waits until no animation or transition runs: a control fading in (180ms opacity) is not its final contrast. */
export async function settled(page: Page) {
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== "running"));
}

export async function expectPolished(page: Page, where: string) {
  await settled(page);
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`), where).toEqual([]);
  const found = await page.evaluate(() => {
    const issues: string[] = [];
    const width = document.documentElement.clientWidth;
    if (document.documentElement.scrollWidth > width) issues.push(`page ${document.documentElement.scrollWidth} > ${width}`);
    for (const region of document.querySelectorAll<HTMLElement>("main .table-region")) {
      if (region.scrollWidth > region.clientWidth + 1) issues.push(`table region ${region.getAttribute("aria-label")} scrolls sideways`);
    }
    const visible = (el: Element) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
    for (const el of document.querySelectorAll("body *")) {
      const own = [...el.childNodes].some((n) => n.nodeType === Node.TEXT_NODE && n.textContent!.trim() !== "");
      if (own && visible(el) && el.closest("svg") === null && parseFloat(getComputedStyle(el).fontSize) < 13) {
        issues.push(`text under 13px: ${el.tagName.toLowerCase()} "${el.textContent!.trim().slice(0, 30)}"`);
      }
    }
    if (width < 600) {
      const standalone = "main a:not(p a):not(li > span a):not(td a), main button, main summary, main select, main input:not([type=checkbox]):not([type=radio]), header button";
      for (const el of document.querySelectorAll<HTMLElement>(standalone)) {
        const r = el.getBoundingClientRect();
        if (visible(el) && getComputedStyle(el).display !== "inline" && r.height < 43.5) issues.push(`target under 44px: ${el.tagName.toLowerCase()} "${(el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 30)}" ${Math.round(r.height)}px`);
      }
    }
    return issues;
  });
  expect(found, where).toEqual([]);
}
