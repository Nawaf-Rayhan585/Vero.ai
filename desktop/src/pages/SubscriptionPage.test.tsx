import { afterEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { makeAuthValue } from "../test/authFixtures";
import { makeSubscription } from "../test/subscriptionFixtures";
import { subscriptionApi } from "../api/subscription";
import { SubscriptionPage } from "./SubscriptionPage";

vi.mock("../api/subscription");
const subscriptionMock = vi.mocked(subscriptionApi);

describe("SubscriptionPage", () => {
  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows the status and a trial countdown while trialing", async () => {
    subscriptionMock.get.mockResolvedValue(
      makeSubscription({
        status: "trialing",
        is_active: true,
        trial_ends_at: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      }),
    );
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    // "Trialing" also appears as an <option> in the manual override's status select below
    // (the same word is a legitimate choice there) — scope to the status badge itself.
    expect(await screen.findByText("Trialing", { selector: ".vero-status-badge" })).toBeInTheDocument();
    expect(screen.getByText(/2 days left in your trial/)).toBeInTheDocument();
  });

  it("shows 'Trial ended' once a trialing subscription's time is up", async () => {
    subscriptionMock.get.mockResolvedValue(
      makeSubscription({ status: "trialing", is_active: false, trial_ends_at: "2020-01-01T00:00:00Z" }),
    );
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    expect(await screen.findByText("Trial ended")).toBeInTheDocument();
  });

  it("shows Active with no countdown for an active subscription", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "active", is_active: true }));
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    // "Active" also appears as an <option> in the manual override's status select below —
    // scope to the status badge itself.
    expect(await screen.findByText("Active", { selector: ".vero-status-badge" })).toBeInTheDocument();
    expect(screen.queryByText(/left in your trial/)).not.toBeInTheDocument();
    expect(screen.queryByText("Trial ended")).not.toBeInTheDocument();
  });

  it("an Owner can set the plan type", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription());
    subscriptionMock.update.mockResolvedValue(makeSubscription({ plan_type: "own_hardware" }));
    const user = userEvent.setup();
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    const select = await screen.findByLabelText("Infrastructure plan");
    await user.selectOptions(select, "own_hardware");

    expect(subscriptionMock.update).toHaveBeenCalledWith({ plan_type: "own_hardware" });
  });

  it("a non-Owner sees the plan as read-only text and no override section", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription({ plan_type: "vero_cloud" }));
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue({ currentRole: "admin" }) });

    await screen.findByText("Vero Cloud");
    expect(screen.queryByLabelText("Infrastructure plan")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Manual override (temporary)" })).not.toBeInTheDocument();
  });

  it("an Owner can activate the subscription via the manual override", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "expired", is_active: false }));
    subscriptionMock.update.mockResolvedValue(makeSubscription({ status: "active", is_active: true }));
    const user = userEvent.setup();
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    const statusSelect = await screen.findByLabelText("Status");
    await user.selectOptions(statusSelect, "active");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(subscriptionMock.update).toHaveBeenCalledWith({ status: "active" });
  });

  it("extending the trial sends a status of trialing and a later trial_ends_at", async () => {
    const trialEnd = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "trialing", trial_ends_at: trialEnd }));
    subscriptionMock.update.mockResolvedValue(makeSubscription());
    const user = userEvent.setup();
    renderWithProviders(<SubscriptionPage />, { authValue: makeAuthValue() });

    await user.click(await screen.findByRole("button", { name: /Extend trial by 3 days/ }));

    expect(subscriptionMock.update).toHaveBeenCalledTimes(1);
    const [payload] = subscriptionMock.update.mock.calls[0];
    expect(payload.status).toBe("trialing");
    expect(new Date(payload.trial_ends_at as string).getTime()).toBeGreaterThan(new Date(trialEnd).getTime());
  });
});
