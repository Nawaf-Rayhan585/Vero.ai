import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { camerasApi } from "../api/cameras";
import type { CameraCreateRequest, CameraUpdateRequest } from "../api/types";

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: camerasApi.list,
  });
}

export function useCreateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CameraCreateRequest) => camerasApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });
}

export function useUpdateCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: CameraUpdateRequest }) => camerasApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });
}

export function useDeleteCamera() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => camerasApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });
}
