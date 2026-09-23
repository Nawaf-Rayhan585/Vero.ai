import { useMutation } from "@tanstack/react-query";
import { organizationsApi } from "../api/organizations";

// No list query here: AuthContext already holds the caller's organizations (it needs them
// for the org switcher and to resolve the X-Organization-Id header) and exposes
// `refreshOrganizations()` to re-fetch them after a create/rename below succeeds.

export function useCreateOrganization() {
  return useMutation({
    mutationFn: (name: string) => organizationsApi.create(name),
  });
}

export function useRenameOrganization() {
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) => organizationsApi.rename(id, name),
  });
}
