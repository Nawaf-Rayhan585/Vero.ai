import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { trackingApi } from "../api/tracking";

const STATUS_POLL_INTERVAL_MS = 2000;

export function useTrackingStatus(cameraId: string | null) {
  return useQuery({
    queryKey: ["cameras", cameraId, "tracking", "status"],
    queryFn: () => trackingApi.status(cameraId as string),
    enabled: cameraId !== null,
    refetchInterval: STATUS_POLL_INTERVAL_MS,
  });
}

export function useStartTracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cameraId: string) => trackingApi.start(cameraId),
    onSuccess: (_data, cameraId) =>
      queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "tracking"] }),
  });
}

export function useStopTracking() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (cameraId: string) => trackingApi.stop(cameraId),
    onSuccess: (_data, cameraId) =>
      queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "tracking"] }),
  });
}
