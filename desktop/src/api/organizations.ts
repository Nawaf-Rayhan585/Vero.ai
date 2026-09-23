import { apiClient } from "./client";
import type { Organization, OrganizationMembership } from "./types";

export const organizationsApi = {
  list: () => apiClient.get<OrganizationMembership[]>("/organizations"),
  create: (name: string) => apiClient.post<OrganizationMembership>("/organizations", { name }),
  rename: (id: string, name: string) => apiClient.patch<Organization>(`/organizations/${id}`, { name }),
};
