import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { locationsApi } from "../api/locations";
import type { LocationCreateRequest, LocationUpdateRequest } from "../api/types";

export function useLocations() {
  return useQuery({
    queryKey: ["locations"],
    queryFn: locationsApi.list,
  });
}

export function useCreateLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LocationCreateRequest) => locationsApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["locations"] }),
  });
}

export function useUpdateLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: LocationUpdateRequest }) => locationsApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["locations"] }),
  });
}

export function useDeleteLocation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => locationsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["locations"] }),
  });
}
