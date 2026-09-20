import { useMutation, useQueryClient } from "@tanstack/react-query";
import { camerasApi } from "../api/cameras";

export function useTestCameraConnection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => camerasApi.testConnection(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });
}
