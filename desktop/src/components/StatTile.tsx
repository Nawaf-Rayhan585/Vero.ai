import type { ReactNode } from "react";
import "./StatTile.css";

/** A single headline number. The number is the chart: a one-bar bar chart would only add ink. */
export function StatTile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="stat-tile">
      <span className="stat-tile__label">{label}</span>
      <span className="stat-tile__value">{value}</span>
      {hint && <span className="stat-tile__hint">{hint}</span>}
    </div>
  );
}

/** `stale`: these are the previous slice's numbers while a new one loads, so they are dimmed
 * rather than left looking current (or replaced by a skeleton that makes the layout jump). */
export function StatTiles({ children, stale = false }: { children: ReactNode; stale?: boolean }) {
  return <div className={`stat-tiles${stale ? " stat-tiles--stale" : ""}`}>{children}</div>;
}
