import type { ReactNode } from "react";
import { Sidebar } from "./Sidebar";
import { TopBar } from "./TopBar";
import "./AppShell.css";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="vero-app-shell">
      <Sidebar />
      <div className="vero-app-shell__main">
        <TopBar />
        <main className="vero-app-shell__content">{children}</main>
      </div>
    </div>
  );
}
