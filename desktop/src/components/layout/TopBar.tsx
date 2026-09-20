import { useHealth } from "../../hooks/useHealth";
import "./TopBar.css";

export function TopBar() {
  const health = useHealth();
  // See DashboardPage.tsx: `data` alone can be stale from before the backend went offline.
  const online = health.data?.status === "ok" && !health.isError;

  return (
    <header className="vero-topbar">
      <span
        className={"vero-topbar__indicator" + (online ? " vero-topbar__indicator--online" : "")}
        role="status"
      >
        <span className="vero-topbar__dot" aria-hidden="true" />
        {online ? "Backend connected" : "Backend offline"}
      </span>
    </header>
  );
}
