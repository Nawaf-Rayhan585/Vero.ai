import type { ReactNode } from "react";
import "./Card.css";

export function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="vero-card">
      {title && <h2 className="vero-card__title">{title}</h2>}
      {children}
    </section>
  );
}
