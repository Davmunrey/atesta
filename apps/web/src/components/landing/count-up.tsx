"use client";

import { useFormatter } from "next-intl";
import { useEffect, useState } from "react";

/** A hero figure that counts up once and settles on its real value (amendment A2). The document and
 *  assistive technology get the final number; the moving copy is decorative. Reduced motion: none. */
export function CountUp({ value }: { value: number }) {
  const format = useFormatter();
  const [shown, setShown] = useState(value);
  useEffect(() => {
    if (typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const start = performance.now();
    let frame = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900);
      setShown(Math.round(value * (1 - (1 - t) ** 3)));
      if (t < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return <><span aria-hidden="true">{format.number(shown)}</span><span className="sr-only">{format.number(value)}</span></>;
}
