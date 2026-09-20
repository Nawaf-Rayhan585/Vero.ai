import type { ReactNode } from "react";
import "./EmptyState.css";

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="vero-empty-state">
      <p className="vero-empty-state__title">{title}</p>
      {children}
    </div>
  );
}
