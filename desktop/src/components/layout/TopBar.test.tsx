import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/renderWithProviders";
import { makeAuthValue, TEST_ORGANIZATION } from "../../test/authFixtures";
import { makeSubscription } from "../../test/subscriptionFixtures";
import { healthApi } from "../../api/health";
import { subscriptionApi } from "../../api/subscription";
import { TopBar } from "./TopBar";

vi.mock("../../api/health");
vi.mock("../../api/subscription");

const healthMock = vi.mocked(healthApi);
const subscriptionMock = vi.mocked(subscriptionApi);

describe("TopBar", () => {
  beforeEach(() => {
    subscriptionMock.get.mockResolvedValue(makeSubscription());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows connected once the health check succeeds", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    renderWithProviders(<TopBar />);
    expect(await screen.findByText("Backend connected")).toBeInTheDocument();
  });

  it("shows offline once a health check fails, even though earlier data was 'ok'", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    const { queryClient } = renderWithProviders(<TopBar />);
    await screen.findByText("Backend connected");

    healthMock.health.mockRejectedValue(new Error("down"));
    await queryClient.refetchQueries({ queryKey: ["health"] });

    expect(await screen.findByText("Backend offline")).toBeInTheDocument();
  });

  it("shows the current organization's name", () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    renderWithProviders(<TopBar />, { authValue: makeAuthValue() });
    expect(screen.getByText(TEST_ORGANIZATION.name)).toBeInTheDocument();
  });

  it("signs out when Sign out is clicked", async () => {
    healthMock.health.mockResolvedValue({ status: "ok" });
    const authValue = makeAuthValue();
    const user = userEvent.setup();
    renderWithProviders(<TopBar />, { authValue });

    await user.click(screen.getByRole("button", { name: "Sign out" }));

    expect(authValue.logout).toHaveBeenCalled();
  });

  it("shows a trial countdown while trialing", async () => {
    subscriptionMock.get.mockResolvedValue(
      makeSubscription({
        status: "trialing",
        is_active: true,
        trial_ends_at: new Date(Date.now() + 2 * 24 * 60 * 60 * 1000).toISOString(),
      }),
    );
    renderWithProviders(<TopBar />, { authValue: makeAuthValue() });

    expect(await screen.findByRole("link", { name: /Trial: 2 days left/ })).toHaveAttribute(
      "href",
      expect.stringContaining("subscription"),
    );
  });

  it("shows an upgrade link once the trial has ended", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "expired", is_active: false }));
    renderWithProviders(<TopBar />, { authValue: makeAuthValue() });

    expect(await screen.findByRole("link", { name: "Trial ended — Upgrade" })).toBeInTheDocument();
  });

  it("shows no trial indicator for an active (paid) subscription", async () => {
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "active", is_active: true }));
    renderWithProviders(<TopBar />, { authValue: makeAuthValue() });

    await screen.findByText(TEST_ORGANIZATION.name);
    expect(screen.queryByText(/Trial/)).not.toBeInTheDocument();
  });
});
