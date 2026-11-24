import { describe, expect, it } from "vitest";
import { DEFAULT_LOCALE, LOCALE_COOKIE, localeCookie, localeFromCookie } from "@atesta/ui/i18n/locale";

describe("localeFromCookie", () => {
  it("defaults to Spanish", () => {
    expect(DEFAULT_LOCALE).toBe("es");
    expect(localeFromCookie("")).toBe("es");
  });

  it("reads the stored choice among other cookies", () => {
    expect(localeFromCookie(`a=1; ${LOCALE_COOKIE}=en; b=2`)).toBe("en");
  });

  it("ignores unknown values and look-alike names", () => {
    expect(localeFromCookie(`${LOCALE_COOKIE}=fr`)).toBe("es");
    expect(localeFromCookie(`x${LOCALE_COOKIE}=en`)).toBe("es");
  });
});

describe("localeCookie", () => {
  it("is site-wide, long-lived, Lax and Secure", () => {
    const parts = localeCookie("en").split("; ");
    expect(parts[0]).toBe(`${LOCALE_COOKIE}=en`);
    expect(parts).toEqual(
      expect.arrayContaining(["Path=/", "Max-Age=31536000", "SameSite=Lax", "Secure"]),
    );
  });
});
