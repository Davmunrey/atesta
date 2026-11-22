"use client";

/**
 * Single-series charts in plain SVG (insights spec): no chart library, nothing for the CSP to load.
 * Dataviz method: one hue (--color-chart, validated on both surfaces), 2px lines with a 10% wash,
 * >= 8px end marker with a 2px surface ring, a direct label at the end only, solid hairline axes,
 * a crosshair and tooltip on hover and keyboard focus, and a table view with every value. Labels
 * and values use text tokens, never the series colour. Text goes in as React text (never HTML).
 */

import { useId, useState, type KeyboardEvent, type PointerEvent } from "react";

export type Point = { label: string; value: number };

const W = 640;
const H = 220;
const PAD = { top: 16, right: 56, bottom: 28, left: 40 };

/** Clean, round upper bound and ticks (0 / step / 2*step …), at most five. Counts never get a
 *  fractional step: half an action does not exist. */
export function ticks(max: number, integer = false): number[] {
  if (max <= 0) return [0, 1];
  const raw = integer ? Math.max(1, max / 4) : max / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => Math.round(i * step * 1000) / 1000);
}

function Table({ caption, points, valueLabel, id }: { caption: string; points: Point[]; valueLabel: string; id: string }) {
  return <details className="chart-table"><summary>{caption}</summary>
    <table id={id}><thead><tr><th scope="col">{valueLabel === "" ? "" : ""}</th><th scope="col">{valueLabel}</th></tr></thead>
      <tbody>{points.map((p) => <tr key={p.label}><th scope="row">{p.label}</th><td>{p.value}</td></tr>)}</tbody></table>
  </details>;
}

/** Trend over time: one line, area wash, crosshair readout, end label. */
export function LineChart({ title, points, valueLabel, tableLabel, format = String, integer = false }: {
  title: string; points: Point[]; valueLabel: string; tableLabel: string; format?: (v: number) => string; integer?: boolean;
}) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const yTicks = ticks(Math.max(...points.map((p) => p.value)), integer);
  const yMax = yTicks.at(-1) ?? 1;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (points.length === 1 ? plotW : (i / (points.length - 1)) * plotW);
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH;
  const line = points.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join(" ");
  const area = `${line} L${x(points.length - 1).toFixed(1)},${y(0)} L${x(0).toFixed(1)},${y(0)} Z`;
  const last = points.length - 1;
  const nearest = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    setActive(Math.max(0, Math.min(last, Math.round(((px - PAD.left) / plotW) * last))));
  };
  const keys = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      setActive((a) => Math.max(0, Math.min(last, (a ?? last) + (e.key === "ArrowRight" ? 1 : -1))));
    } else if (e.key === "Home" || e.key === "End") { e.preventDefault(); setActive(e.key === "Home" ? 0 : last); }
  };
  const shown = active ?? null;
  return <figure className="chart">
    <figcaption className="chart-title">{title}</figcaption>
    <div className="chart-frame">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${title}. ${points[0]?.label ?? ""} – ${points[last]?.label ?? ""}: ${format(points[last]?.value ?? 0)}`}
        tabIndex={0} onPointerMove={nearest} onPointerLeave={() => setActive(null)} onKeyDown={keys} onBlur={() => setActive(null)}
        aria-describedby={`${id}-table`}>
        {yTicks.map((t) => <g key={t}><line className="chart-grid" x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)} />
          <text className="chart-tick" x={PAD.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">{format(t)}</text></g>)}
        <text className="chart-tick" x={PAD.left} y={H - 6}>{points[0]?.label}</text>
        <text className="chart-tick" x={W - PAD.right} y={H - 6} textAnchor="end">{points[last]?.label}</text>
        <path className="chart-area" d={area} />
        <path className="chart-line" d={line} />
        <circle className="chart-dot" cx={x(last)} cy={y(points[last]?.value ?? 0)} r={4} />
        <text className="chart-end-label" x={x(last) + 10} y={y(points[last]?.value ?? 0)} dominantBaseline="middle">{format(points[last]?.value ?? 0)}</text>
        {shown !== null ? <g aria-hidden="true">
          <line className="chart-crosshair" x1={x(shown)} x2={x(shown)} y1={PAD.top} y2={PAD.top + plotH} />
          <circle className="chart-dot" cx={x(shown)} cy={y(points[shown]!.value)} r={4} />
        </g> : null}
      </svg>
      {shown !== null ? <div className="chart-tooltip" role="status" style={{ left: `${(x(shown) / W) * 100}%` }}>
        <strong>{format(points[shown]!.value)}</strong><span>{points[shown]!.label}</span>
      </div> : null}
    </div>
    <Table caption={tableLabel} points={points} valueLabel={valueLabel} id={`${id}-table`} />
  </figure>;
}

/** Counts per period: columns <= 24px, 4px rounded tops, 2px surface gap; each column is a hit target. */
export function ColumnChart({ title, points, valueLabel, tableLabel }: { title: string; points: Point[]; valueLabel: string; tableLabel: string }) {
  const id = useId();
  const [active, setActive] = useState<number | null>(null);
  const yTicks = ticks(Math.max(...points.map((p) => p.value)), true);
  const yMax = yTicks.at(-1) ?? 1;
  const plotW = W - PAD.left - 16;
  const plotH = H - PAD.top - PAD.bottom;
  const slot = plotW / Math.max(points.length, 1);
  const barW = Math.min(24, Math.max(2, slot - 2));
  const y = (v: number) => PAD.top + plotH - (v / yMax) * plotH;
  return <figure className="chart">
    <figcaption className="chart-title">{title}</figcaption>
    <div className="chart-frame">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title} aria-describedby={`${id}-table`} onPointerLeave={() => setActive(null)}>
        {yTicks.map((t) => <g key={t}><line className="chart-grid" x1={PAD.left} x2={W - 16} y1={y(t)} y2={y(t)} />
          <text className="chart-tick" x={PAD.left - 8} y={y(t)} textAnchor="end" dominantBaseline="middle">{t}</text></g>)}
        <text className="chart-tick" x={PAD.left} y={H - 6}>{points[0]?.label}</text>
        <text className="chart-tick" x={W - 16} y={H - 6} textAnchor="end">{points.at(-1)?.label}</text>
        {points.map((p, i) => {
          const cx = PAD.left + i * slot + slot / 2;
          const h = Math.max(0, y(0) - y(p.value));
          const r = Math.min(4, h / 2, barW / 2);
          const top = y(p.value);
          const left = cx - barW / 2;
          const path = h === 0 ? "" : `M${left},${y(0)} V${top + r} Q${left},${top} ${left + r},${top} H${left + barW - r} Q${left + barW},${top} ${left + barW},${top + r} V${y(0)} Z`;
          return <g key={p.label} onPointerEnter={() => setActive(i)}>
            <rect className="chart-hit" x={PAD.left + i * slot} y={PAD.top} width={slot} height={plotH} />
            {path ? <path className="chart-bar" data-active={active === i ? "true" : undefined} d={path} /> : null}
          </g>;
        })}
      </svg>
      {active !== null ? <div className="chart-tooltip" role="status" style={{ left: `${((PAD.left + active * slot + slot / 2) / W) * 100}%` }}>
        <strong>{points[active]!.value}</strong><span>{points[active]!.label}</span>
      </div> : null}
    </div>
    <Table caption={tableLabel} points={points} valueLabel={valueLabel} id={`${id}-table`} />
  </figure>;
}

/** Part of a whole, compared: ranked horizontal bars, one hue, largest first, value at the tip. */
export function RankedBars({ title, rows, empty }: { title: string; rows: (Point & { id?: string })[]; empty: string }) {
  const sorted = [...rows].sort((a, b) => b.value - a.value || a.label.localeCompare(b.label));
  const max = Math.max(1, ...sorted.map((r) => r.value));
  return <figure className="chart">
    <figcaption className="chart-title">{title}</figcaption>
    {sorted.length === 0 ? <p className="text-sm text-muted">{empty}</p> : <ul className="ranked-bars">
      {sorted.map((r) => <li key={r.id ?? r.label}>
        <span className="ranked-label" title={r.label}>{r.label}</span>
        <span className="ranked-track"><span className="ranked-bar" style={{ inlineSize: `${(r.value / max) * 100}%` }} /></span>
        <span className="ranked-value">{r.value}</span>
      </li>)}
    </ul>}
  </figure>;
}

/** Headline figures: label, value; proportional numerals (dataviz: no tabular-nums on big values). */
export function StatTiles({ tiles }: { tiles: { label: string; value: number | string }[] }) {
  return <dl className="stat-tiles">{tiles.map((t) => <div key={t.label}><dt>{t.label}</dt><dd>{t.value}</dd></div>)}</dl>;
}
