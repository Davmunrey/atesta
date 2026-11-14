import { describe, expect, it } from "vitest";
import { isAllowed, violations } from "../../scripts/check-licenses";

describe("isAllowed", () => {
  it.each(["MIT", "Apache-2.0", "ISC", "BSD-3-Clause", "MPL-2.0", "LGPL-3.0-or-later", "Apache-2.0 AND MIT", "(MIT OR GPL-3.0)"])(
    "allows %s",
    (license) => expect(isAllowed(license)).toBe(true),
  );

  it.each(["GPL-3.0-only", "GPL-2.0", "AGPL-3.0", "MIT AND GPL-3.0", "UNKNOWN", ""])("rejects %s", (license) =>
    expect(isAllowed(license)).toBe(false),
  );

  // Free-text license fields are not SPDX: the id may carry a version suffix or a GNU prefix.
  it.each([
    "GPLv3",
    "GPL3",
    "AGPLv3",
    "GNU GPL v3",
    "GNU AGPL",
    "MIT, GPL-3.0",
    "GNU General Public License v3.0",
    "GNU Affero General Public License v3.0",
  ])("rejects the non-SPDX spelling %s", (license) => expect(isAllowed(license)).toBe(false));

  it.each(["LGPLv3", "GNU LGPL", "GNU Lesser General Public License v3.0", "GNU Library General Public License v2"])(
    "allows the non-SPDX LGPL spelling %s",
    (license) => expect(isAllowed(license)).toBe(true),
  );
});

it("lists each rejected package with its versions", () => {
  const report = {
    MIT: [{ name: "ok", versions: ["1.0.0"] }],
    "AGPL-3.0": [{ name: "bad", versions: ["2.0.0", "2.1.0"] }],
  };
  expect(violations(report)).toEqual(["bad@2.0.0, 2.1.0 (AGPL-3.0)"]);
});
