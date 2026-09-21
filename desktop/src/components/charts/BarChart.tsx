import { useId, useState } from "react";
import { formatNumber } from "../../lib/format";
import "./BarChart.css";

export interface BarSeries {
  key: string;
  label: string;
  /** One value per bucket. */
  values: number[];
  /** Which categorical colour: 1 (blue) or 2 (orange). Fixed by the series, never by rank. */
  colorSlot: 1 | 2;
}

export interface BarBucket {
  /** Short x-axis label. */
  label: string;
  /** Full label for the tooltip and the table. */
  fullLabel: string;
  /** A note shown in the tooltip and the table, e.g. how long tracking ran. */
  note?: string;
  /** Nothing was being tracked: drawn hatched, not as an empty bar. */
  notRunning?: boolean;
}

export interface BarChartProps {
  title: string;
  buckets: BarBucket[];
  series: BarSeries[];
  /** Previous data still on screen while a new slice loads: drawn dimmed, not replaced by a skeleton. */
  stale?: boolean;
}

const VIEW_W = 720;
const VIEW_H = 260;
const MARGIN = { left: 44, right: 8, top: 12, bottom: 30 };
const MAX_BAR_WIDTH = 24;
const BAR_GAP = 2; // the surface-coloured gap between touching bars
const CORNER = 4;
const MAX_X_LABELS = 8;

/** A y-axis with clean, whole-number ticks (counts are whole numbers). */
export function niceScale(max: number, targetTicks = 4): { max: number; ticks: number[] } {
  if (!(max > 0)) return { max: targetTicks, ticks: Array.from({ length: targetTicks + 1 }, (_, i) => i) };
  const rawStep = max / targetTicks;
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const residual = rawStep / magnitude;
  const niceStep = (residual <= 1 ? 1 : residual <= 2 ? 2 : residual <= 5 ? 5 : 10) * magnitude;
  const step = Math.max(1, niceStep);
  const top = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  for (let value = 0; value <= top; value += step) ticks.push(value);
  return { max: top, ticks };
}

/** A column with a rounded top and a square base, growing from the baseline. */
export function barPath(x: number, y: number, width: number, height: number, radius = CORNER): string {
  const r = Math.min(radius, height, width / 2);
  return `M${x},${y + height} V${y + r} Q${x},${y} ${x + r},${y} H${x + width - r} Q${x + width},${y} ${x + width},${y + r} V${y + height} Z`;
}

export function BarChart({ title, buckets, series, stale = false }: BarChartProps) {
  const [active, setActive] = useState<number | null>(null);
  const [showTable, setShowTable] = useState(false);
  const hatchId = `hatch-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  const count = buckets.length;
  const anyNotRunning = buckets.some((b) => b.notRunning);
  const dataMax = Math.max(0, ...series.flatMap((s) => s.values));
  const scale = niceScale(dataMax);

  const plotW = VIEW_W - MARGIN.left - MARGIN.right;
  const plotH = VIEW_H - MARGIN.top - MARGIN.bottom;
  const slotW = count > 0 ? plotW / count : plotW;
  const barW = Math.max(1, Math.min(MAX_BAR_WIDTH, (slotW * 0.72 - (series.length - 1) * BAR_GAP) / series.length));
  const groupW = series.length * barW + (series.length - 1) * BAR_GAP;
  const labelEvery = Math.max(1, Math.ceil(count / MAX_X_LABELS));
  const baselineY = MARGIN.top + plotH;
  const yFor = (value: number) => baselineY - (value / scale.max) * plotH;

  function summaryFor(index: number): string {
    const parts = series.map((s) => `${formatNumber(s.values[index] ?? 0)} ${s.label.toLowerCase()}`);
    const bucket = buckets[index];
    return `${bucket.fullLabel}: ${parts.join(", ")}${bucket.note ? `. ${bucket.note}` : ""}`;
  }

  if (count === 0) return <p className="chart__empty">No data for this range.</p>;

  const activeBucket = active !== null ? buckets[active] : null;
  const tooltipLeft = active !== null ? MARGIN.left + slotW * (active + 0.5) : 0;

  return (
    <div className={`chart${stale ? " chart--stale" : ""}`} role="group" aria-label={title}>
      <div className="chart__legend">
        {series.length > 1 &&
          series.map((s) => (
            <span key={s.key} className="chart__legend-item">
              <span className="chart__swatch" style={{ background: `var(--chart-series-${s.colorSlot})` }} />
              {s.label}
            </span>
          ))}
        {anyNotRunning && (
          <span className="chart__legend-item">
            <span className="chart__swatch chart__swatch--hatched" />
            Not running
          </span>
        )}
      </div>

      <div className="chart__plot">
        <svg viewBox={`0 0 ${VIEW_W} ${VIEW_H}`} className="chart__svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <pattern id={hatchId} patternUnits="userSpaceOnUse" width="7" height="7" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="7" className="chart__hatch-line" />
            </pattern>
          </defs>

          {scale.ticks.map((tick) => (
            <g key={tick}>
              <line
                x1={MARGIN.left}
                x2={VIEW_W - MARGIN.right}
                y1={yFor(tick)}
                y2={yFor(tick)}
                className={tick === 0 ? "chart__axis" : "chart__grid"}
              />
              <text x={MARGIN.left - 8} y={yFor(tick)} className="chart__tick" textAnchor="end" dominantBaseline="middle">
                {formatNumber(tick)}
              </text>
            </g>
          ))}

          {buckets.map((bucket, i) => {
            const slotStart = MARGIN.left + slotW * i;
            const groupX = slotStart + (slotW - groupW) / 2;
            return (
              <g key={i}>
                {active === i && (
                  <rect x={slotStart} y={MARGIN.top} width={slotW} height={plotH} className="chart__hover" />
                )}
                {bucket.notRunning && (
                  <rect x={slotStart} y={MARGIN.top} width={slotW} height={plotH} fill={`url(#${hatchId})`} />
                )}
                {series.map((s, k) => {
                  const value = s.values[i] ?? 0;
                  if (value <= 0) return null;
                  const height = Math.max(2, baselineY - yFor(value));
                  return (
                    <path
                      key={s.key}
                      d={barPath(groupX + k * (barW + BAR_GAP), baselineY - height, barW, height)}
                      style={{ fill: `var(--chart-series-${s.colorSlot})` }}
                    />
                  );
                })}
                {i % labelEvery === 0 && (
                  <text x={slotStart + slotW / 2} y={baselineY + 18} className="chart__tick" textAnchor="middle">
                    {bucket.label}
                  </text>
                )}
                {/* The hit target is the whole slot, taller than any bar, and keyboard-focusable. */}
                <rect
                  x={slotStart}
                  y={MARGIN.top}
                  width={slotW}
                  height={plotH + MARGIN.bottom}
                  className="chart__hit"
                  tabIndex={0}
                  role="img"
                  aria-label={summaryFor(i)}
                  onPointerEnter={() => setActive(i)}
                  onPointerMove={() => setActive(i)}
                  onPointerLeave={() => setActive((current) => (current === i ? null : current))}
                  onFocus={() => setActive(i)}
                  onBlur={() => setActive((current) => (current === i ? null : current))}
                />
              </g>
            );
          })}
        </svg>

        {activeBucket && active !== null && (
          <div
            className="chart__tooltip"
            role="status"
            style={{ left: `${Math.min(88, Math.max(12, (tooltipLeft / VIEW_W) * 100))}%` }}
          >
            <div className="chart__tooltip-title">{activeBucket.fullLabel}</div>
            {series.map((s) => (
              <div key={s.key} className="chart__tooltip-row">
                <span className="chart__key" style={{ background: `var(--chart-series-${s.colorSlot})` }} />
                <strong>{formatNumber(s.values[active] ?? 0)}</strong>
                <span>{s.label}</span>
              </div>
            ))}
            {activeBucket.note && <div className="chart__tooltip-note">{activeBucket.note}</div>}
          </div>
        )}
      </div>

      <button type="button" className="chart__table-toggle" aria-pressed={showTable} onClick={() => setShowTable((v) => !v)}>
        {showTable ? "Hide table" : "Show table"}
      </button>

      {showTable && (
        <table className="chart__table">
          <caption>{title}</caption>
          <thead>
            <tr>
              <th scope="col">Period</th>
              {series.map((s) => (
                <th key={s.key} scope="col">
                  {s.label}
                </th>
              ))}
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {buckets.map((bucket, i) => (
              <tr key={i}>
                <th scope="row">{bucket.fullLabel}</th>
                {series.map((s) => (
                  <td key={s.key}>{formatNumber(s.values[i] ?? 0)}</td>
                ))}
                <td>{bucket.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
