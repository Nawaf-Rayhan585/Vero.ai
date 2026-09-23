import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import { daysRemaining, useSubscription, useUpdateSubscription } from "../hooks/useSubscription";
import { Button, Card, ErrorNotice, Spinner, StatusBadge } from "../components/ui";
import type { PlanType, Subscription, SubscriptionStatus } from "../api/types";
// Reuses .account-form/.account-form--inline/.account-muted and .auth-hint rather than
// redefining them — an explicit import, not relying on another page having loaded them.
import "./AccountPage.css";
import "./AuthPages.css";
import "./SubscriptionPage.css";

const STATUS_LABEL: Record<SubscriptionStatus, string> = {
  trialing: "Trialing",
  active: "Active",
  expired: "Expired",
  canceled: "Canceled",
};
const STATUS_TONE: Record<SubscriptionStatus, "success" | "danger" | "neutral"> = {
  trialing: "neutral",
  active: "success",
  expired: "danger",
  canceled: "danger",
};
const PLAN_LABEL: Record<PlanType, string> = {
  own_hardware: "Own Hardware",
  vero_cloud: "Vero Cloud",
};
export const EXTEND_TRIAL_DAYS = 3;

function TrialCountdown({ subscription }: { subscription: Subscription }) {
  if (subscription.status !== "trialing") return null;
  if (!subscription.is_active) {
    return <p className="subscription-countdown subscription-countdown--expired">Trial ended</p>;
  }
  const days = daysRemaining(subscription.trial_ends_at);
  return (
    <p className="subscription-countdown">
      {days} day{days === 1 ? "" : "s"} left in your trial
    </p>
  );
}

function PlanSection({ subscription, canEdit }: { subscription: Subscription; canEdit: boolean }) {
  const updatePlan = useUpdateSubscription();

  return (
    <Card title="Plan">
      <div className="settings-row">
        <label htmlFor="subscription-plan-type">Infrastructure plan</label>
        {canEdit ? (
          <select
            id="subscription-plan-type"
            value={subscription.plan_type ?? ""}
            disabled={updatePlan.isPending}
            onChange={(e) => {
              const value = e.currentTarget.value;
              updatePlan.mutate({ plan_type: value === "" ? null : (value as PlanType) });
            }}
          >
            <option value="">Not chosen yet</option>
            <option value="own_hardware">Own Hardware</option>
            <option value="vero_cloud">Vero Cloud</option>
          </select>
        ) : (
          <p>{subscription.plan_type ? PLAN_LABEL[subscription.plan_type] : "Not chosen yet"}</p>
        )}
        <span className="auth-hint">
          Own Hardware and Vero Cloud behave the same today — the plans themselves are built in later phases.
        </span>
      </div>
      {updatePlan.isError && <ErrorNotice message={updatePlan.error.message} />}
    </Card>
  );
}

function OwnerOverride({ subscription }: { subscription: Subscription }) {
  const updateSubscription = useUpdateSubscription();
  const [status, setStatus] = useState<SubscriptionStatus>(subscription.status);

  // Keep the draft in sync if the subscription changes from elsewhere (another device,
  // or this page's own extend-trial action below).
  useEffect(() => {
    setStatus(subscription.status);
  }, [subscription.status]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    updateSubscription.mutate({ status });
  }

  function extendTrial() {
    // Extend from whichever is later: an already-future trial end, or now — so this
    // always results in a genuinely-not-expired trial, never a shorter one.
    const currentEnd = new Date(subscription.trial_ends_at);
    const base = currentEnd > new Date() ? currentEnd : new Date();
    base.setDate(base.getDate() + EXTEND_TRIAL_DAYS);
    updateSubscription.mutate({ status: "trialing", trial_ends_at: base.toISOString() });
  }

  return (
    <Card title="Manual override (temporary)">
      <p className="account-muted subscription-override-note">
        There is no billing system yet — PayPal arrives in a later phase. Until then, this
        sets the subscription state directly.
      </p>
      <form className="account-form account-form--inline" onSubmit={handleSubmit}>
        <label htmlFor="subscription-status-override" className="subscription-override-label">
          Status
        </label>
        <select
          id="subscription-status-override"
          value={status}
          onChange={(e) => setStatus(e.currentTarget.value as SubscriptionStatus)}
        >
          <option value="trialing">Trialing</option>
          <option value="active">Active</option>
          <option value="expired">Expired</option>
          <option value="canceled">Canceled</option>
        </select>
        <Button type="submit" variant="primary" disabled={updateSubscription.isPending}>
          {updateSubscription.isPending ? "Saving..." : "Save"}
        </Button>
      </form>
      <div className="row">
        <Button onClick={extendTrial} disabled={updateSubscription.isPending}>
          Extend trial by {EXTEND_TRIAL_DAYS} days
        </Button>
      </div>
      {updateSubscription.isError && <ErrorNotice message={updateSubscription.error.message} />}
    </Card>
  );
}

export function SubscriptionPage() {
  const auth = useAuth();
  const isOwner = auth.currentRole === "owner";
  const { data: subscription, isLoading, isError, error } = useSubscription();

  return (
    <>
      <Card title="Subscription">
        {isLoading && <Spinner label="Loading subscription" />}
        {isError && <ErrorNotice message={error.message} />}
        {subscription && (
          <div className="subscription-status-row">
            <StatusBadge label={STATUS_LABEL[subscription.status]} tone={STATUS_TONE[subscription.status]} />
            <TrialCountdown subscription={subscription} />
          </div>
        )}
      </Card>

      {subscription && <PlanSection subscription={subscription} canEdit={isOwner} />}
      {subscription && isOwner && <OwnerOverride subscription={subscription} />}
    </>
  );
}
