/**
 * Seeds a realistic demo organization in the LOCAL development stack, through the public API only
 * (no database writes), for sales demos and pilot sessions. Content lives in scripts/demo/es.json.
 *
 * Needs the local stack (fake Cognito on :9000, API on :8000, web on :3000) with draft packs
 * visible. Usage: npx -y node@22 scripts/demo-seed.ts [http://localhost:3000]
 */
import { readFileSync } from "node:fs";
import { chromium, type APIRequestContext } from "@playwright/test";

const base = process.argv[2] ?? "http://localhost:3000";
if (!/^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(base)) throw new Error("demo-seed only runs against a local stack");
const demo = JSON.parse(readFileSync(new URL("./demo/es.json", import.meta.url), "utf8"));
const FRAMEWORK = "ens_rd311_2022";

async function call(api: APIRequestContext, method: "GET" | "POST", path: string, data?: unknown, expected = [200, 201]) {
  const response = await api.fetch(`${base}${path}`, { method, data, headers: { Origin: base } });
  if (!expected.includes(response.status())) throw new Error(`${method} ${path} -> ${response.status()} ${await response.text()}`);
  return response.status() === 204 ? null : response.json();
}

const browser = await chromium.launch();
const page = await (await browser.newContext()).newPage();
await page.goto(`${base}/app`);
await page.locator("input[name=email]").fill(demo.owner);
await page.locator("input[name=code]").fill("123456");
await page.getByRole("button").click();
await page.waitForURL(`${base}/app**`);
const api = page.request;

const org = (await call(api, "POST", "/api/v1/orgs", { name: demo.organization })).id as string;
const o = `/api/v1/orgs/${org}`;
const f = `${o}/frameworks/${FRAMEWORK}`;

// Scope: the middle level of every axis the pack declares.
const register = await call(api, "GET", `${f}/register`);
const axisValues: Record<string, string | Record<string, string>> = {};
for (const [axis, d] of Object.entries(register.axes as Record<string, { keys: string[]; levels: string[] }>)) {
  const level = d.levels[Math.floor(d.levels.length / 2)]!;
  axisValues[axis] = d.keys.length ? Object.fromEntries(d.keys.map((k) => [k, level])) : level;
}
await call(api, "POST", `${f}/scope`, { axis_values: axisValues });

// Self-assessment: a realistic spread over the first measures.
const today = new Date().toISOString().slice(0, 10);
const codes = (register.items as { code: string }[]).map((i) => i.code).slice(0, demo.assessed);
for (const [i, code] of codes.entries()) {
  const state = i % 10 === 9 ? "not_applicable" : i % 5 === 4 ? "not_implemented" : i % 4 === 3 ? "partially_implemented" : "implemented";
  await call(api, "POST", `${f}/register/${encodeURIComponent(code)}`, {
    applicability: state === "not_applicable" ? "not_applicable" : "applies",
    implementation: state === "not_applicable" ? "not_implemented" : state,
    regularly_reviewed: state === "implemented",
    justification: state === "not_applicable" ? demo.justification : demo.justification_applies,
    performed_by: demo.assessor, performed_on: today, notes: demo.notes,
  });
}
await call(api, "POST", `${f}/assessment-reviews`, { ...demo.review, reviewed_on: today });

for (const p of demo.policies) {
  const policy = await call(api, "POST", `${o}/policies`, { title: p.title, location_url: p.location_url, review_months: p.review_months });
  if (p.version) await call(api, "POST", `${o}/policies/${policy.id}/approvals`, { version: p.version, approver_name: p.approver_name, approved_on: today });
}

const ar = demo.access_review;
const review = await call(api, "POST", `${o}/access-reviews`, { title: ar.title, system: ar.system, accounts: ar.accounts.map(([account, detail]: string[]) => ({ account, detail })) });
for (const entry of review.entries) {
  await call(api, "POST", `${o}/access-reviews/${review.id}/decisions`, { entry_id: entry.id, decision: ar.revoke.includes(entry.account) ? "revoke" : "keep", note: "" });
}
await call(api, "POST", `${o}/access-reviews/${review.id}/close`);

const tr = demo.training;
const closes = new Date(Date.now() + 14 * 86_400_000).toISOString().slice(0, 10);
const campaign = await call(api, "POST", `${o}/training-campaigns`, { title: tr.title, material_url: tr.material_url, closes_on: closes });
const token = new URL(campaign.link).hash.replace("#token=", "");
for (const [full_name, email] of tr.people) await call(api, "POST", "/api/v1/training/acknowledge", { token, full_name, email });
await call(api, "POST", `${o}/training-campaigns/${campaign.id}/close`);

const inc = demo.incident;
const incident = await call(api, "POST", `${o}/incidents`, { title: inc.title, aware_at: new Date(Date.now() - inc.hours_ago * 3_600_000).toISOString(), significant: false, personal_data: true });
await call(api, "POST", `${o}/incidents/${incident.id}/updates`, { kind: "note", note: inc.note });

const apiToken = await call(api, "POST", `${o}/api-tokens`, demo.api_token); // a unit test checks it against TokenIn
const ingest = await api.fetch(`${base}/api/v1/ingest/evidence`, { method: "POST", headers: { Authorization: `Bearer ${apiToken.token}` }, data: { ...demo.evidence, external_id: `demo-${today}` } });
if (![200, 201, 422].includes(ingest.status())) throw new Error(`ingest -> ${ingest.status()}`);

await browser.close();
console.log(`Demo organization "${demo.organization}" ready: ${base}/app/org?org=${org} (sign in as ${demo.owner}, code 123456)`);
