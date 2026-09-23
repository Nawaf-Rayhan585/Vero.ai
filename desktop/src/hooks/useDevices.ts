import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { devicesApi } from "../api/devices";
import type { DeviceCreateRequest, DeviceUpdateRequest } from "../api/types";

export function useDevices() {
  return useQuery({
    queryKey: ["devices"],
    queryFn: devicesApi.list,
  });
}

export function useCreateDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeviceCreateRequest) => devicesApi.create(body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });
}

export function useUpdateDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: DeviceUpdateRequest }) => devicesApi.update(id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });
}

export function useDeleteDevice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => devicesApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["devices"] }),
  });
}
