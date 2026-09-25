import { TEST_ORGANIZATION } from "./authFixtures";
import type { Subscription } from "../api/types";

/** A ready-to-use active subscription — the common case most tests should render against,
 * so canGrow-gated buttons (Add camera, Edit, Add location, Rename, Add member, role
 * selects) show up by default. Tests that specifically exercise trial/expiry behavior pass
 * overrides (e.g. `{ status: "expired", is_active: false }`). */
export function makeSubscription(overrides: Partial<Subscription> = {}): Subscription {
  return {
    id: "33333333-3333-3333-3333-333333333333",
    organization_id: TEST_ORGANIZATION.id,
    status: "active",
    plan_type: null,
    trial_started_at: "2026-01-01T00:00:00Z",
    trial_ends_at: "2026-01-04T00:00:00Z",
    max_cameras: null,
    max_devices: null,
    activated_at: "2026-01-01T00:00:00Z",
    is_active: true,
    paypal_subscription_id: null,
    paypal_plan_id: null,
    canceled_at: null,
    ...overrides,
  };
}
