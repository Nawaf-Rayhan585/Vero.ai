import { vi } from "vitest";
import type { AuthContextValue } from "../auth/AuthContext";
import type { Organization, OrganizationMembership, User } from "../api/types";

export const TEST_USER: User = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@example.com",
  name: "Test Owner",
  created_at: "2026-01-01T00:00:00Z",
};

export const TEST_ORGANIZATION: Organization = {
  id: "22222222-2222-2222-2222-222222222222",
  name: "Test Organization",
  created_at: "2026-01-01T00:00:00Z",
};

export const TEST_MEMBERSHIP: OrganizationMembership = { organization: TEST_ORGANIZATION, role: "owner" };

/** A ready-to-use, signed-in-as-owner AuthContextValue for tests that don't care about auth
 * specifics but render a component that calls useAuth() — see renderWithProviders' default.
 * Pass overrides (e.g. `{ currentRole: "member" }`) for tests that do care. */
export function makeAuthValue(overrides: Partial<AuthContextValue> = {}): AuthContextValue {
  return {
    status: "signedIn",
    user: TEST_USER,
    organizations: [TEST_MEMBERSHIP],
    currentOrganizationId: TEST_ORGANIZATION.id,
    currentRole: "owner",
    login: vi.fn().mockResolvedValue(undefined),
    register: vi.fn().mockResolvedValue(undefined),
    logout: vi.fn().mockResolvedValue(undefined),
    changePassword: vi.fn().mockResolvedValue(undefined),
    switchOrganization: vi.fn(),
    refreshOrganizations: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}
