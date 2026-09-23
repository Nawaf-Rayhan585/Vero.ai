import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test/renderWithProviders";
import { makeAuthValue, TEST_ORGANIZATION, TEST_USER } from "../test/authFixtures";
import { makeSubscription } from "../test/subscriptionFixtures";
import { organizationsApi } from "../api/organizations";
import { locationsApi } from "../api/locations";
import { membersApi } from "../api/members";
import { subscriptionApi } from "../api/subscription";
import { ApiError } from "../api/client";
import { AccountPage } from "./AccountPage";
import type { Location, Member } from "../api/types";

vi.mock("../api/organizations");
vi.mock("../api/locations");
vi.mock("../api/members");
vi.mock("../api/subscription");

const organizationsMock = vi.mocked(organizationsApi);
const locationsMock = vi.mocked(locationsApi);
const membersMock = vi.mocked(membersApi);
const subscriptionMock = vi.mocked(subscriptionApi);

const OTHER_ORG = { id: "org-b", name: "Org B", created_at: "2026-01-01T00:00:00Z" };

function makeLocation(overrides: Partial<Location> = {}): Location {
  return {
    id: "loc-1",
    organization_id: TEST_ORGANIZATION.id,
    name: "Main location",
    timezone: "UTC",
    camera_count: 0,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeMember(overrides: Partial<Member> = {}): Member {
  return {
    user_id: TEST_USER.id,
    email: TEST_USER.email,
    name: TEST_USER.name,
    role: "owner",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("AccountPage", () => {
  beforeEach(() => {
    locationsMock.list.mockResolvedValue([]);
    membersMock.list.mockResolvedValue([makeMember()]);
    subscriptionMock.get.mockResolvedValue(makeSubscription());
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  it("shows the signed-in user's profile and role, and signs out", async () => {
    const authValue = makeAuthValue();
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    expect(screen.getByText(TEST_USER.name)).toBeInTheDocument();
    expect(screen.getByText(TEST_USER.email)).toBeInTheDocument();
    expect(screen.getByText("Owner")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(authValue.logout).toHaveBeenCalled();
  });

  it("rejects a password change when the confirmation does not match, without calling the API", async () => {
    const authValue = makeAuthValue();
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    await user.type(screen.getByLabelText("Current password"), "old-password");
    await user.type(screen.getByLabelText("New password"), "new-password-1");
    await user.type(screen.getByLabelText("Confirm new password"), "does-not-match");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("New password and confirmation don't match.")).toBeInTheDocument();
    expect(authValue.changePassword).not.toHaveBeenCalled();
  });

  it("changes the password and shows a success message", async () => {
    const authValue = makeAuthValue();
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    await user.type(screen.getByLabelText("Current password"), "old-password");
    await user.type(screen.getByLabelText("New password"), "new-password-1");
    await user.type(screen.getByLabelText("Confirm new password"), "new-password-1");
    await user.click(screen.getByRole("button", { name: "Change password" }));

    expect(authValue.changePassword).toHaveBeenCalledWith("old-password", "new-password-1");
    expect(await screen.findByText(/Password changed/)).toBeInTheDocument();
  });

  it("switching the organization select calls auth.switchOrganization", async () => {
    const authValue = makeAuthValue({
      organizations: [
        { organization: TEST_ORGANIZATION, role: "owner" },
        { organization: OTHER_ORG, role: "member" },
      ],
    });
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    await user.selectOptions(screen.getByLabelText("Current organization"), OTHER_ORG.id);
    expect(authValue.switchOrganization).toHaveBeenCalledWith(OTHER_ORG.id);
  });

  it("renames the current organization and refreshes the organization list", async () => {
    const authValue = makeAuthValue();
    organizationsMock.rename.mockResolvedValue({ ...TEST_ORGANIZATION, name: "Renamed Org" });
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    await user.click(screen.getByRole("button", { name: "Rename this organization" }));
    const input = screen.getByLabelText("Organization name");
    await user.clear(input);
    await user.type(input, "Renamed Org");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(organizationsMock.rename).toHaveBeenCalledWith(TEST_ORGANIZATION.id, "Renamed Org");
    await vi.waitFor(() => expect(authValue.refreshOrganizations).toHaveBeenCalled());
  });

  it("creates another organization and switches to it", async () => {
    const authValue = makeAuthValue();
    organizationsMock.create.mockResolvedValue({ organization: OTHER_ORG, role: "owner" });
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    await user.click(screen.getByRole("button", { name: "Create another organization" }));
    await user.type(screen.getByLabelText("New organization name"), "Org B");
    await user.click(screen.getByRole("button", { name: "Create" }));

    expect(organizationsMock.create).toHaveBeenCalledWith("Org B");
    await vi.waitFor(() => expect(authValue.switchOrganization).toHaveBeenCalledWith(OTHER_ORG.id));
  });

  it("lists locations with their camera count and adds a new one", async () => {
    locationsMock.list.mockResolvedValue([makeLocation({ name: "Warehouse", camera_count: 3 })]);
    locationsMock.create.mockResolvedValue(makeLocation({ id: "loc-2", name: "Storefront" }));
    const authValue = makeAuthValue();
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    expect(await screen.findByText("Warehouse")).toBeInTheDocument();
    expect(screen.getByText("3 cameras")).toBeInTheDocument();

    // "Add location" additionally waits on the subscription query (canGrow), a separate
    // fetch from the locations list just awaited above.
    await user.click(await screen.findByRole("button", { name: "Add location" }));
    await user.type(screen.getByLabelText("Location name"), "Storefront");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(locationsMock.create).toHaveBeenCalledWith({ name: "Storefront" });
  });

  it("shows the backend's error when deleting a non-empty location fails", async () => {
    locationsMock.list.mockResolvedValue([makeLocation({ name: "Warehouse", camera_count: 2 })]);
    locationsMock.remove.mockRejectedValue(
      new ApiError(409, "Conflict", "This location has 2 camera(s) on it. Move or delete them first."),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue() });

    await user.click(await screen.findByRole("button", { name: "Delete" }));

    expect(await screen.findByText("This location has 2 camera(s) on it. Move or delete them first.")).toBeInTheDocument();
  });

  it("lists members and adds one by email with a role", async () => {
    membersMock.list.mockResolvedValue([makeMember()]);
    membersMock.add.mockResolvedValue(makeMember({ user_id: "u2", email: "new@example.com", role: "admin" }));
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue() });

    expect(await screen.findByText(TEST_USER.email)).toBeInTheDocument();

    // "Add member" additionally waits on the subscription query (canGrow), a separate
    // fetch from the members list just awaited above.
    await user.click(await screen.findByRole("button", { name: "Add member" }));
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.selectOptions(screen.getByLabelText("Role"), "admin");
    await user.click(screen.getByRole("button", { name: "Add" }));

    expect(membersMock.add).toHaveBeenCalledWith({ email: "new@example.com", role: "admin" });
  });

  it("an admin (not owner) cannot grant the owner role", async () => {
    membersMock.list.mockResolvedValue([makeMember()]);
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue({ currentRole: "admin" }) });

    await user.click(await screen.findByRole("button", { name: "Add member" }));
    const roleSelect = screen.getByLabelText("Role");
    expect(within(roleSelect).getByRole("option", { name: "Owner" })).toBeDisabled();
  });

  it("disables changing the role or removing the organization's sole owner", async () => {
    membersMock.list.mockResolvedValue([makeMember({ role: "owner" })]);
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue() });

    // TEST_USER.email also appears in the (synchronously rendered) Profile section, so
    // waiting on it wouldn't actually wait for the Members list's async load — wait on
    // something that only exists once that list has rendered instead.
    const roleSelect = (await screen.findByDisplayValue("Owner")) as HTMLSelectElement;
    expect(roleSelect).toBeDisabled();
    expect(screen.getByRole("button", { name: "Leave" })).toBeDisabled();
  });

  it("lets a member leave the organization themselves, refreshing organizations afterward", async () => {
    membersMock.list.mockResolvedValue([
      makeMember({ role: "owner" }),
      makeMember({ user_id: "u2", email: "member@example.com", name: "A Member", role: "member" }),
    ]);
    const authValue = makeAuthValue({ user: { ...TEST_USER, id: "u2", email: "member@example.com" }, currentRole: "member" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderWithProviders(<AccountPage />, { authValue });

    // Same premature-match trap as above: this user's email is also their own Profile
    // section's email, rendered before the Members list has loaded.
    await user.click(await screen.findByRole("button", { name: "Leave" }));

    expect(membersMock.remove).toHaveBeenCalledWith("u2");
    await vi.waitFor(() => expect(authValue.refreshOrganizations).toHaveBeenCalled());
  });

  it("hides every configuration control from a member — organization rename/create, locations, and member management", async () => {
    locationsMock.list.mockResolvedValue([makeLocation({ name: "Warehouse" })]);
    membersMock.list.mockResolvedValue([
      makeMember({ role: "member" }), // the signed-in user (TEST_USER), a plain member
      makeMember({ user_id: "u2", email: "owner2@example.com", name: "Other Owner", role: "owner" }),
    ]);
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue({ currentRole: "member" }) });

    await screen.findByText("Warehouse");

    expect(screen.queryByRole("button", { name: "Rename this organization" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add location" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add member" })).not.toBeInTheDocument();
    // A member sees roles as read-only badges, not editable per-row selects — and cannot
    // remove someone else, only (still) leave themselves.
    expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
    expect(screen.getByText("Other Owner")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Leave" })).toBeInTheDocument();
    // "Create another organization" is not a permission-gated action (anyone can start one).
    expect(screen.getByRole("button", { name: "Create another organization" })).toBeInTheDocument();
  });

  it("hides Add location/Rename and Add member/role-select once the trial has ended, for an Owner — Delete/Remove stay", async () => {
    locationsMock.list.mockResolvedValue([makeLocation({ name: "Warehouse" })]);
    membersMock.list.mockResolvedValue([
      makeMember({ role: "owner" }),
      makeMember({ user_id: "u2", email: "other@example.com", name: "Other Member", role: "member" }),
    ]);
    subscriptionMock.get.mockResolvedValue(makeSubscription({ status: "expired", is_active: false }));
    renderWithProviders(<AccountPage />, { authValue: makeAuthValue() });

    await screen.findByText("Warehouse");
    await screen.findByText("Other Member");

    expect(screen.queryByRole("button", { name: "Add location" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Rename" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add member" })).not.toBeInTheDocument();
    // A member's role becomes a read-only badge instead of an editable select once
    // update_member_role is out of reach too (it also grows/edits usage).
    expect(screen.getByText("Member")).toBeInTheDocument(); // the StatusBadge, not a <select>
    // Organization rename isn't backend-gated by trial status (see AccountPage.tsx).
    expect(screen.getByRole("button", { name: "Rename this organization" })).toBeInTheDocument();
    // Deleting a location and removing a member are never blocked by trial status.
    expect(screen.getByRole("button", { name: "Delete" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove" })).toBeInTheDocument();
  });
});
