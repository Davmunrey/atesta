import { describe, expect, it } from "vitest";
import { CLOUDFRONT_CSP_LIMIT, buildPolicy, externalize, inlineScripts, inlineStyles, sha256 } from "@atesta/ui/csp";

describe("inlineScripts", () => {
  it("returns inline script bodies and skips external ones", () => {
    const html = '<script src="/a.js"></script><script>self.x=1</script><script async="">y()</script>';
    expect(inlineScripts(html)).toEqual(["self.x=1", "y()"]);
  });
});

describe("externalize (#212)", () => {
  const html = '<head><script src="/a.js" async=""></script></head><body><p>x</p><script>self.x=1</script><script id="b">y()</script></body>';
  const { html: out, files } = externalize(html);

  it("leaves no inline script behind, so the policy needs no hashes", () => {
    expect(inlineScripts(out)).toEqual([]);
    expect(out).toContain('<script src="/a.js" async=""></script>');
  });

  it("loads each body from a same-origin file named by its SHA-256, in the same place and order", () => {
    expect(files.map((f) => f.body)).toEqual(["self.x=1", "y()"]);
    for (const f of files) expect(f.path).toMatch(/^\/_next\/static\/inline\/[0-9a-f]{64}\.js$/);
    const [first, second] = files;
    expect(out).toBe(`<head><script src="/a.js" async=""></script></head><body><p>x</p><script src="${first!.path}"></script><script id="b" src="${second!.path}"></script></body>`);
  });

  it("names identical scripts identically, so shared bootstrap code is one cached file", () => {
    const again = externalize("<script>self.x=1</script>");
    expect(again.files[0]!.path).toBe(files[0]!.path);
  });

  it("refuses a script it cannot move safely: a non-JavaScript type would lose its content", () => {
    expect(() => externalize('<script type="application/json">{}</script>')).toThrow(/application\/json/);
  });
});

describe("inlineStyles", () => {
  it("finds style tags and style attributes, which the policy would block", () => {
    expect(inlineStyles('<p style="color:red">x</p><style>p{}</style>')).toBe(2);
    expect(inlineStyles('<link rel="stylesheet" href="/a.css"><p class="x">y</p>')).toBe(0);
  });
});

it("hashes as CSP expects: base64 of SHA-256 over the exact script text", () => {
  expect(sha256("alert(1)")).toBe("'sha256-bhHHL3z2vDgxUt0W3dWQOrprscmda2Y5pLsLg4GF+pI='");
});

describe("buildPolicy", () => {
  const policy = buildPolicy(["'sha256-b'", "'sha256-a'", "'sha256-a'"]);

  it("is script-src 'self' alone when there is nothing to hash", () => {
    expect(buildPolicy([])).toContain("script-src 'self';");
  });

  it("allows only same-origin and hashed scripts, sorted and deduplicated", () => {
    expect(policy).toContain("script-src 'self' 'sha256-a' 'sha256-b';");
    expect(policy).not.toContain("unsafe-inline");
    expect(policy).not.toContain("unsafe-eval");
  });

  it.each(["default-src 'self'", "frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'", "form-action 'self'", "connect-src 'self'"])(
    "includes %s",
    (directive) => expect(policy).toContain(directive),
  );

  it("refuses a policy CloudFront cannot carry", () => {
    const many = Array.from({ length: 40 }, (_, i) => sha256(`s${i}`));
    expect(() => buildPolicy(many)).toThrow(/1783/);
    expect(CLOUDFRONT_CSP_LIMIT).toBe(1783);
  });
});
