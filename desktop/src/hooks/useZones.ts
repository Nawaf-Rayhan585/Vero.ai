import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { zonesApi } from "../api/zones";
import type { ZoneCreateRequest } from "../api/types";

export function useZones(cameraId: string | null) {
  return useQuery({
    queryKey: ["cameras", cameraId, "zones"],
    queryFn: () => zonesApi.list(cameraId as string),
    enabled: cameraId !== null,
  });
}

export function useCreateZone(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ZoneCreateRequest) => zonesApi.create(cameraId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "zones"] }),
  });
}

export function useDeleteZone(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (zoneId: string) => zonesApi.remove(zoneId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "zones"] }),
  });
}
