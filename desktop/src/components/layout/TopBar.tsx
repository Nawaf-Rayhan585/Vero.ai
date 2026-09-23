import { useState } from "react";
import { useHealth } from "../../hooks/useHealth";
import { useAuth } from "../../auth/AuthContext";
import "./TopBar.css";

export function TopBar() {
  const health = useHealth();
  const auth = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  // See DashboardPage.tsx: `data` alone can be stale from before the backend went offline.
  const online = health.data?.status === "ok" && !health.isError;
  const organizationName = auth.organizations.find((m) => m.organization.id === auth.currentOrganizationId)
    ?.organization.name;

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await auth.logout();
    } finally {
      setSigningOut(false);
    }
  }

  return (
    <header className="vero-topbar">
      {organizationName ? <span className="vero-topbar__organization">{organizationName}</span> : <span />}
      <div className="vero-topbar__actions">
        <span
          className={"vero-topbar__indicator" + (online ? " vero-topbar__indicator--online" : "")}
          role="status"
        >
          <span className="vero-topbar__dot" aria-hidden="true" />
          {online ? "Backend connected" : "Backend offline"}
        </span>
        {auth.status === "signedIn" && (
          <button className="vero-topbar__signout" onClick={handleSignOut} disabled={signingOut}>
            {signingOut ? "Signing out..." : "Sign out"}
          </button>
        )}
      </div>
    </header>
  );
}
