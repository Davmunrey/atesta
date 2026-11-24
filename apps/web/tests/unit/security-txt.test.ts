import { describe, expect, it } from "vitest";
import { MAX_AGE_DAYS, parse, problems, securityTxt } from "../../scripts/security-txt";

const NOW = new Date("2026-11-24T10:00:00Z");
const text = securityTxt(NOW);
const fields = parse(text);
const values = (name: string) => fields.filter(([field]) => field === name).map(([, value]) => value);

describe("security.txt (RFC 9116, issue 416)", () => {
  it("lists the security mailbox first and GitHub private reporting second", () => {
    expect(values("Contact")).toEqual([
      "mailto:security@atesta.cloud",
      "https://github.com/Davmunrey/atesta/security/advisories/new",
    ]);
  });

  it("expires once, in RFC 3339, less than a year after the build", () => {
    const [expires, ...more] = values("Expires");
    expect(more).toEqual([]);
    expect(expires).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    const days = (new Date(expires!).getTime() - NOW.getTime()) / 86_400_000;
    expect(days).toBe(MAX_AGE_DAYS);
    expect(days).toBeGreaterThanOrEqual(90);
    expect(days).toBeLessThan(365);
  });

  it("names both hosts as canonical, the languages and the policy", () => {
    expect(values("Canonical")).toEqual([
      "https://atesta.cloud/.well-known/security.txt",
      "https://app.atesta.cloud/.well-known/security.txt",
    ]);
    expect(values("Preferred-Languages")).toEqual(["es, en"]);
    expect(values("Policy")).toEqual(["https://github.com/Davmunrey/atesta/blob/main/SECURITY.md"]);
  });

  it("uses LF line endings, comments with # and no unknown field", () => {
    expect(text.endsWith("\n")).toBe(true);
    expect(text).not.toContain("\r");
    const known = ["Contact", "Expires", "Preferred-Languages", "Canonical", "Policy"];
    expect(fields.every(([field]) => known.includes(field))).toBe(true);
    expect(problems(text, NOW)).toEqual([]);
  });
});

describe("problems: what the build refuses", () => {
  const without = (name: string) => text.split("\n").filter((line) => !line.startsWith(`${name}:`)).join("\n");

  it.each([
    ["no Contact", without("Contact"), "Contact is required"],
    ["no Expires", without("Expires"), "Expires must appear exactly once"],
    ["two Expires", `${text}Expires: 2027-01-01T00:00:00Z\n`, "Expires must appear exactly once"],
    ["an http link", text.replace("https://github.com/Davmunrey/atesta/blob", "http://github.com/Davmunrey/atesta/blob"), "Policy must be https"],
    ["a bare email", text.replace("mailto:security@", "security@"), "Contact must be a mailto:, tel: or https: URI"],
    ["already expired", text.replace(/Expires: .*/, "Expires: 2026-11-23T00:00:00Z"), "Expires is in the past"],
    ["a year or more ahead", text.replace(/Expires: .*/, "Expires: 2027-11-24T10:00:00Z"), "Expires is a year or more ahead"],
    ["a malformed date", text.replace(/Expires: .*/, "Expires: next spring"), "Expires is not RFC 3339"],
    ["two language lines", `${text}Preferred-Languages: fr\n`, "Preferred-Languages must not appear more than once"],
  ])("%s", (_, broken, problem) => expect(problems(broken, NOW)).toContain(problem));
});
