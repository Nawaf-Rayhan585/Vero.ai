import { useState } from "react";
import { Link } from "react-router-dom";
import { useHealth } from "../../hooks/useHealth";
import { useAuth } from "../../auth/AuthContext";
import { daysRemaining, useSubscription } from "../../hooks/useSubscription";
import type { Subscription } from "../../api/types";
import "./TopBar.css";

/** null when there's nothing worth calling out (no data yet, or an active/paid
 * subscription) — a trialing countdown while there's still time left, or a call to
 * upgrade once the trial (or subscription) is no longer active. */
function trialIndicator(subscription: Subscription | undefined): { label: string; expired: boolean } | null {
  if (!subscription || subscription.status === "active") return null;
  if (!subscription.is_active) return { label: "Trial ended — Upgrade", expired: true };
  const days = daysRemaining(subscription.trial_ends_at);
  return { label: `Trial: ${days} day${days === 1 ? "" : "s"} left`, expired: false };
}

export function TopBar() {
  const health = useHealth();
  const auth = useAuth();
  const { data: subscription } = useSubscription();
  const [signingOut, setSigningOut] = useState(false);
  // See DashboardPage.tsx: `data` alone can be stale from before the backend went offline.
  const online = health.data?.status === "ok" && !health.isError;
  const organizationName = auth.organizations.find((m) => m.organization.id === auth.currentOrganizationId)
    ?.organization.name;
  const trial = trialIndicator(subscription);

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
        {trial && (
          <Link
            to="/subscription"
            className={"vero-topbar__trial" + (trial.expired ? " vero-topbar__trial--expired" : "")}
          >
            {trial.label}
          </Link>
        )}
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
