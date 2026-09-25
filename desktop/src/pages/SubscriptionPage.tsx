import { openUrl } from "@tauri-apps/plugin-opener";
import { useEffect, useState, type FormEvent } from "react";
import { useAuth } from "../auth/AuthContext";
import {
  daysRemaining,
  useCancelPayPalSubscription,
  useStartPayPalCheckout,
  useSubscription,
  useSyncPayPalSubscription,
  useUpdateSubscription,
} from "../hooks/useSubscription";
import { useCreateDevice, useDeleteDevice, useDevices, useUpdateDevice } from "../hooks/useDevices";
import { Button, Card, EmptyState, ErrorNotice, Spinner, StatusBadge } from "../components/ui";
import type { Device, PlanType, Subscription, SubscriptionStatus } from "../api/types";
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
          Own Hardware runs camera tracking on this device. Vero Cloud runs it on Vero's own infrastructure instead.
        </span>
      </div>
      {updatePlan.isError && <ErrorNotice message={updatePlan.error.message} />}
    </Card>
  );
}

function DeviceRow({
  device,
  canConfigure,
  canGrow,
}: {
  device: Device;
  /** Remove — never blocked by trial/subscription status. */
  canConfigure: boolean;
  /** Rename — grows/edits usage (require_active_configurator on the backend). */
  canGrow: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(device.name);
  const updateDevice = useUpdateDevice();
  const deleteDevice = useDeleteDevice();

  if (editing) {
    return (
      <li className="account-row">
        <form
          className="account-form account-form--inline"
          onSubmit={(e) => {
            e.preventDefault();
            updateDevice.mutate({ id: device.id, body: { name: draft } }, { onSuccess: () => setEditing(false) });
          }}
        >
          <input type="text" required value={draft} onChange={(e) => setDraft(e.currentTarget.value)} />
          <Button type="submit" variant="primary" disabled={updateDevice.isPending}>
            Save
          </Button>
          <Button type="button" onClick={() => setEditing(false)} disabled={updateDevice.isPending}>
            Cancel
          </Button>
          {updateDevice.isError && <ErrorNotice message={updateDevice.error.message} />}
        </form>
      </li>
    );
  }

  return (
    <li className="account-row">
      <div className="account-row__header">
        <div>
          <strong>{device.name}</strong>
          {device.notes && <span className="account-muted"> · {device.notes}</span>}
        </div>
        {canConfigure && (
          <div className="row">
            {canGrow && (
              <Button onClick={() => { setDraft(device.name); setEditing(true); }}>Rename</Button>
            )}
            <Button
              onClick={() => {
                if (window.confirm(`Remove "${device.name}" from this organization's devices?`)) {
                  deleteDevice.mutate(device.id);
                }
              }}
              disabled={deleteDevice.isPending}
            >
              Remove
            </Button>
          </div>
        )}
      </div>
      {deleteDevice.isError && <ErrorNotice message={deleteDevice.error.message} />}
    </li>
  );
}

function DevicesSection({ canConfigure, canGrow }: { canConfigure: boolean; canGrow: boolean }) {
  const { data: devices, isLoading, isError, error } = useDevices();
  const createDevice = useCreateDevice();
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");

  return (
    <Card title="Devices">
      <p className="account-muted subscription-override-note">
        The physical machines running Vero.ai for this organization — a record you keep,
        not something Vero.ai verifies against your hardware.
      </p>
      {canGrow && (
        <div className="row">
          {!adding && <Button variant="primary" onClick={() => setAdding(true)}>Add device</Button>}
        </div>
      )}
      {adding && (
        <form
          className="account-form"
          onSubmit={(e) => {
            e.preventDefault();
            createDevice.mutate({ name }, { onSuccess: () => { setName(""); setAdding(false); } });
          }}
        >
          <div className="settings-row">
            <label htmlFor="subscription-device-name">Device name</label>
            <input
              id="subscription-device-name"
              type="text"
              required
              autoFocus
              placeholder="e.g. Warehouse PC"
              value={name}
              onChange={(e) => setName(e.currentTarget.value)}
            />
          </div>
          {createDevice.isError && <ErrorNotice message={createDevice.error.message} />}
          <div className="row">
            <Button type="submit" variant="primary" disabled={createDevice.isPending}>
              {createDevice.isPending ? "Adding..." : "Add"}
            </Button>
            <Button type="button" onClick={() => setAdding(false)} disabled={createDevice.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}

      {isLoading && <Spinner label="Loading devices" />}
      {isError && <ErrorNotice message={error.message} />}
      {devices && devices.length === 0 && !adding && (
        <EmptyState title="No devices registered">Add the machines running Vero.ai for this organization.</EmptyState>
      )}
      {devices && devices.length > 0 && (
        <ul className="account-list">
          {devices.map((device) => (
            <DeviceRow key={device.id} device={device} canConfigure={canConfigure} canGrow={canGrow} />
          ))}
        </ul>
      )}
    </Card>
  );
}

function BillingSection({ subscription, isOwner }: { subscription: Subscription; isOwner: boolean }) {
  const startCheckout = useStartPayPalCheckout();
  const syncSubscription = useSyncPayPalSubscription();
  const cancelSubscription = useCancelPayPalSubscription();
  const [awaitingApproval, setAwaitingApproval] = useState(false);

  if (!isOwner) return null;

  if (subscription.plan_type !== "own_hardware") {
    return (
      <Card title="Billing">
        <p className="account-muted">Choose the Own Hardware plan above to subscribe via PayPal.</p>
      </Card>
    );
  }

  const hasPayPalSubscription = subscription.paypal_subscription_id !== null;
  const isPayPalActive = hasPayPalSubscription && subscription.status === "active";
  const canStartFresh = !hasPayPalSubscription || subscription.status === "canceled";

  async function handleCheckout() {
    const result = await startCheckout.mutateAsync();
    await openUrl(result.approve_url);
    setAwaitingApproval(true);
  }

  return (
    <Card title="Billing">
      <p className="account-muted subscription-override-note">
        Own Hardware billing via PayPal — sandbox only, no real charges.
      </p>
      <div className="row">
        {canStartFresh && (
          <Button variant="primary" onClick={handleCheckout} disabled={startCheckout.isPending}>
            {startCheckout.isPending ? "Starting..." : "Subscribe via PayPal"}
          </Button>
        )}
        {!canStartFresh && !isPayPalActive && (
          <Button onClick={() => syncSubscription.mutate()} disabled={syncSubscription.isPending}>
            {syncSubscription.isPending ? "Checking..." : "Check status"}
          </Button>
        )}
        {isPayPalActive && (
          <Button
            onClick={() => {
              if (window.confirm("Cancel your PayPal subscription? This takes effect immediately.")) {
                cancelSubscription.mutate();
              }
            }}
            disabled={cancelSubscription.isPending}
          >
            {cancelSubscription.isPending ? "Canceling..." : "Cancel subscription"}
          </Button>
        )}
      </div>
      {awaitingApproval && !isPayPalActive && (
        <p className="account-muted">
          Approve the subscription in your browser, then come back and click "Check status".
        </p>
      )}
      {startCheckout.isError && <ErrorNotice message={startCheckout.error.message} />}
      {syncSubscription.isError && <ErrorNotice message={syncSubscription.error.message} />}
      {cancelSubscription.isError && <ErrorNotice message={cancelSubscription.error.message} />}
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
        An admin/support fallback that works alongside real PayPal billing above — sets
        the subscription state directly, for cases PayPal itself doesn't cover.
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
  const canConfigure = auth.currentRole === "owner" || auth.currentRole === "admin";
  const { data: subscription, isLoading, isError, error } = useSubscription();
  const canGrow = canConfigure && (subscription?.is_active ?? false);

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
      {subscription && <BillingSection subscription={subscription} isOwner={isOwner} />}
      <DevicesSection canConfigure={canConfigure} canGrow={canGrow} />
      {subscription && isOwner && <OwnerOverride subscription={subscription} />}
    </>
  );
}
