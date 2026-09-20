import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { linesApi } from "../api/lines";
import type { LineCreateRequest } from "../api/types";

export function useLines(cameraId: string | null) {
  return useQuery({
    queryKey: ["cameras", cameraId, "lines"],
    queryFn: () => linesApi.list(cameraId as string),
    enabled: cameraId !== null,
  });
}

export function useCreateLine(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: LineCreateRequest) => linesApi.create(cameraId, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "lines"] }),
  });
}

export function useDeleteLine(cameraId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (lineId: string) => linesApi.remove(lineId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras", cameraId, "lines"] }),
  });
}
